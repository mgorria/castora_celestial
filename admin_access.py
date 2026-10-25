"""Additional password lock for the owner-only web Centralita.

The private Sites gateway still establishes the owner identity. This service
adds a password and a short session, with hashes persisted in PostgreSQL.
No browser-supplied actor, password, or raw session is stored or logged.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

import database
from account_service import AccountService, SECRET


SESSION_LIFETIME = timedelta(minutes=30)
RATE_WINDOW = timedelta(minutes=15)
RATE_LIMIT = 10


class AdminAccessError(RuntimeError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def _storage_errors(method):
    @wraps(method)
    async def wrapped(*args, **kwargs):
        try:
            return await method(*args, **kwargs)
        except AdminAccessError:
            raise
        except Exception:
            # Database errors can include SQL parameters: never expose them.
            raise AdminAccessError("admin_auth_unavailable", 503) from None
    return wrapped


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AdminAccessService:
    def __init__(self, resolve_actor, *, get_pool=database.require_pool, pool=None, clock=None, passwords=None):
        self.resolve_actor = resolve_actor
        self.get_pool = (lambda: pool) if pool is not None else get_pool
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.passwords = passwords or AccountService(resolve_actor, get_pool=self.get_pool, clock=self.clock)

    def _now(self):
        now = self.clock()
        if now.tzinfo is None:
            raise AdminAccessError("admin_auth_unavailable", 503)
        return now.astimezone(timezone.utc)

    def _scope(self, owner_identity):
        chat_id = self.resolve_actor("owner")
        if (not isinstance(chat_id, int) or isinstance(chat_id, bool) or not 0 < chat_id <= 2**63 - 1
                or chat_id == self.resolve_actor("sandra")):
            raise AdminAccessError("admin_auth_unavailable", 503)
        if (not isinstance(owner_identity, str) or not 1 <= len(owner_identity) <= 256
                or owner_identity.strip() != owner_identity or any(ord(c) < 33 or ord(c) > 126 for c in owner_identity)):
            raise AdminAccessError("owner_identity_required", 403)
        return chat_id, _digest(owner_identity)

    @staticmethod
    def _password(value):
        if not isinstance(value, str) or not 1 <= len(value) <= 128:
            raise AdminAccessError("invalid_password")
        return value

    @_storage_errors
    async def initialize(self):
        async with self.get_pool().acquire() as conn:
            await conn.execute("""
                create table if not exists centralita_passwords (
                    chat_id bigint primary key check (chat_id > 0),
                    password_hash text not null,
                    created_at timestamptz not null
                );
                create table if not exists centralita_sessions (
                    token_hash char(64) primary key,
                    chat_id bigint not null references centralita_passwords(chat_id),
                    owner_identity_hash char(64) not null,
                    created_at timestamptz not null,
                    expires_at timestamptz not null,
                    revoked_at timestamptz
                );
                create index if not exists centralita_sessions_owner_idx on centralita_sessions (chat_id);
                create table if not exists centralita_auth_limits (
                    chat_id bigint primary key,
                    window_start timestamptz not null,
                    attempts integer not null
                );
            """)
        await self.passwords._dummy()

    async def _rate_limit(self, chat_id):
        now = self._now()
        async with self.get_pool().acquire() as conn:
            # Every attempt commits independently of password validation or setup.
            attempts = await conn.fetchval("""insert into centralita_auth_limits (chat_id, window_start, attempts)
                values ($1, $2, 1) on conflict (chat_id) do update set
                attempts = case when centralita_auth_limits.window_start <= $3 then 1
                    else least(centralita_auth_limits.attempts + 1, 1000000) end,
                window_start = case when centralita_auth_limits.window_start <= $3 then $2
                    else centralita_auth_limits.window_start end returning attempts""", chat_id, now, now - RATE_WINDOW)
        if attempts > RATE_LIMIT:
            raise AdminAccessError("rate_limited", 429)

    async def _new_session(self, conn, chat_id, identity_hash, now):
        token = secrets.token_urlsafe(32)
        expires = now + SESSION_LIFETIME
        await conn.execute("""insert into centralita_sessions
            (token_hash, chat_id, owner_identity_hash, created_at, expires_at) values ($1, $2, $3, $4, $5)""",
            _digest(token), chat_id, identity_hash, now, expires)
        await conn.execute("delete from centralita_sessions where chat_id = $1 and expires_at <= $2", chat_id, now)
        return {"configured": True, "unlocked": True, "expires_at": expires.isoformat(), "session_token": token}

    @_storage_errors
    async def setup(self, owner_identity, password):
        chat_id, identity_hash = self._scope(owner_identity)
        await self._rate_limit(chat_id)
        password = self._password(password)
        # Hash outside the transaction; a transaction-scoped owner lock then makes
        # simultaneous first setup atomic, without replacing an existing password.
        password_hash = await self.passwords._hash(password)
        now = self._now()
        async with self.get_pool().acquire() as conn:
            async with conn.transaction():
                await conn.execute("select pg_advisory_xact_lock($1::bigint)", chat_id)
                if await conn.fetchval("select exists(select 1 from centralita_passwords where chat_id = $1)", chat_id):
                    raise AdminAccessError("admin_already_configured", 409)
                if self._scope(owner_identity) != (chat_id, identity_hash):
                    raise AdminAccessError("admin_auth_unavailable", 503)
                await conn.execute("insert into centralita_passwords (chat_id, password_hash, created_at) values ($1, $2, $3)",
                                   chat_id, password_hash, now)
                return await self._new_session(conn, chat_id, identity_hash, now)

    @_storage_errors
    async def unlock(self, owner_identity, password):
        chat_id, identity_hash = self._scope(owner_identity)
        await self._rate_limit(chat_id)
        password = self._password(password)
        async with self.get_pool().acquire() as conn:
            password_hash = await conn.fetchval("select password_hash from centralita_passwords where chat_id = $1", chat_id)
        if password_hash is None:
            raise AdminAccessError("admin_setup_required", 409)
        if not await self.passwords._verify(password_hash, password):
            raise AdminAccessError("invalid_admin_password", 401)
        async with self.get_pool().acquire() as conn:
            async with conn.transaction():
                # Recheck after asynchronous hashing, so a changed owner/config
                # cannot receive a session for credentials checked before change.
                if self._scope(owner_identity) != (chat_id, identity_hash):
                    raise AdminAccessError("admin_auth_unavailable", 503)
                current = await conn.fetchval("select password_hash from centralita_passwords where chat_id = $1", chat_id)
                if current != password_hash:
                    raise AdminAccessError("admin_locked", 423)
                return await self._new_session(conn, chat_id, identity_hash, self._now())

    @_storage_errors
    async def status(self, owner_identity, token=None):
        chat_id, identity_hash = self._scope(owner_identity)
        now = self._now()
        async with self.get_pool().acquire() as conn:
            configured = await conn.fetchval("select exists(select 1 from centralita_passwords where chat_id = $1)", chat_id)
            expires = None
            if configured and isinstance(token, str) and SECRET.fullmatch(token):
                expires = await conn.fetchval("""select expires_at from centralita_sessions
                    where token_hash = $1 and chat_id = $2 and owner_identity_hash = $3
                    and revoked_at is null and expires_at > $4""", _digest(token), chat_id, identity_hash, now)
        return {"configured": bool(configured), "unlocked": expires is not None,
                "expires_at": expires.isoformat() if expires else None}

    @_storage_errors
    async def lock(self, owner_identity, token=None):
        chat_id, identity_hash = self._scope(owner_identity)
        if isinstance(token, str) and SECRET.fullmatch(token):
            async with self.get_pool().acquire() as conn:
                await conn.execute("""update centralita_sessions set revoked_at = $4
                    where token_hash = $1 and chat_id = $2 and owner_identity_hash = $3 and revoked_at is null""",
                    _digest(token), chat_id, identity_hash, self._now())
        result = await self.status(owner_identity)
        return result
