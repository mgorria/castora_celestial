"""Invitation-only Sandra and owner accounts, using the existing PostgreSQL pool.

This module never reads an actor or Telegram ID from a browser. Owner-only
invitation methods must be protected by the calling transport. Raw invitation
codes and session tokens are returned once and are never stored or logged.
The transport owns HTTPS, trusted client-IP extraction, CSRF and Secure cookies.
"""

import asyncio
import hashlib
import ipaddress
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from functools import wraps
from uuid import uuid4

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type

import database


INVITATION_LIFETIME = timedelta(hours=48)
SESSION_LIFETIME = timedelta(days=7)
RATE_WINDOW = timedelta(minutes=15)
USERNAME = re.compile(r"^[a-z0-9_][a-z0-9_.-]{2,31}$")
SECRET = re.compile(r"^[A-Za-z0-9_-]{43}$")
RATE_LIMITS = {"login": {"ip": 40, "account": 10}, "register": {"ip": 20, "account": 5}}


class AccountError(RuntimeError):
    def __init__(self, code, status=400):
        super().__init__(code)
        self.code, self.status = code, status


def _storage_errors(method):
    @wraps(method)
    async def wrapped(*args, **kwargs):
        try:
            return await method(*args, **kwargs)
        except AccountError:
            raise
        except Exception:
            # SQL/driver exceptions can contain parameters. Keep them off the wire.
            raise AccountError("accounts_unavailable", 503) from None
    return wrapped


def _digest(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _iso(value):
    return value.astimezone(timezone.utc).isoformat()


class AccountService:
    def __init__(self, resolve_actor, *, get_pool=database.require_pool, pool=None, clock=None):
        self.resolve_actor = resolve_actor
        self.get_pool = (lambda: pool) if pool is not None else get_pool
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        # RFC 9106's low-memory Argon2id profile. Bound concurrent work and keep it
        # off the Telegram event loop (at most two 64-MiB hash operations).
        self.hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4,
                                     hash_len=32, salt_len=16, type=Type.ID)
        self.hash_slots = asyncio.Semaphore(2)
        self.dummy_hash = None
        self.dummy_lock = asyncio.Lock()
        self.last_rate_cleanup = None

    def _now(self):
        value = self.clock()
        if value.tzinfo is None:
            raise AccountError("accounts_unavailable", 503)
        return value.astimezone(timezone.utc)

    def _actor_id(self, actor):
        if actor not in ("sandra", "owner"):
            raise AccountError("account_identity_unavailable", 503)
        value = self.resolve_actor(actor)
        other = self.resolve_actor("owner" if actor == "sandra" else "sandra")
        if (not isinstance(value, int) or isinstance(value, bool) or not 0 < value <= 2**63 - 1
                or value == other):
            raise AccountError("account_identity_unavailable", 503)
        return value

    def _sandra_id(self):
        return self._actor_id("sandra")

    def _bound_actor(self, record):
        """A stored role never follows a changed or swapped chat-id binding."""
        actor = record.get("actor") if record else None
        if actor not in ("sandra", "owner"):
            return None
        try:
            return actor if record["chat_id"] == self._actor_id(actor) else None
        except AccountError:
            return None

    @staticmethod
    def normalize_username(value):
        if not isinstance(value, str) or len(value) > 128:
            raise AccountError("invalid_username")
        value = unicodedata.normalize("NFKC", value).strip().casefold()
        if not USERNAME.fullmatch(value):
            raise AccountError("invalid_username")
        return value

    @staticmethod
    def _password(value):
        if not isinstance(value, str) or not 1 <= len(value) <= 128:
            raise AccountError("invalid_password")
        return value

    @staticmethod
    def _ip(value):
        try:
            if not isinstance(value, str) or len(value) > 64:
                raise ValueError()
            return str(ipaddress.ip_address(value))
        except ValueError:
            return "unknown"

    async def _hash(self, password):
        async with self.hash_slots:
            return await asyncio.to_thread(self.hasher.hash, password)

    async def _verify(self, password_hash, password):
        async with self.hash_slots:
            try:
                return await asyncio.to_thread(self.hasher.verify, password_hash, password)
            except (VerificationError, InvalidHashError):
                return False

    async def _dummy(self):
        if self.dummy_hash is None:
            async with self.dummy_lock:
                if self.dummy_hash is None:
                    self.dummy_hash = await self._hash(secrets.token_urlsafe(32))
        return self.dummy_hash

    async def _rate_limit(self, operation, ip, username):
        now = self._now()
        limits = RATE_LIMITS[operation]
        buckets = sorted([
            (f"{operation}:ip:{_digest(self._ip(ip))}", limits["ip"]),
            (f"{operation}:account:{_digest(username)}", limits["account"]),
        ])
        blocked = False
        async with self.get_pool().acquire() as conn:
            async with conn.transaction():
                for bucket, maximum in buckets:
                    attempts = await conn.fetchval(
                        """insert into portal_auth_limits (bucket_key, window_start, attempts)
                           values ($1, $2, 1)
                           on conflict (bucket_key) do update set
                             attempts = case when portal_auth_limits.window_start <= $3 then 1
                                             else least(portal_auth_limits.attempts + 1, 1000000) end,
                             window_start = case when portal_auth_limits.window_start <= $3 then $2
                                                 else portal_auth_limits.window_start end
                           returning attempts""", bucket, now, now - RATE_WINDOW)
                    blocked = blocked or attempts > maximum
                if self.last_rate_cleanup is None or now - self.last_rate_cleanup > timedelta(hours=1):
                    await conn.execute("delete from portal_auth_limits where window_start < $1", now - timedelta(days=1))
                    self.last_rate_cleanup = now
        # Raise after committing attempts, including rejected requests.
        if blocked:
            raise AccountError("rate_limited", 429)

    @_storage_errors
    async def initialize(self):
        async with self.get_pool().acquire() as conn:
            await conn.execute("""
                create table if not exists portal_accounts (
                    id uuid primary key,
                    chat_id bigint not null unique check (chat_id > 0),
                    actor text not null default 'sandra' check (actor in ('sandra', 'owner')),
                    username varchar(32) not null unique,
                    password_hash text not null,
                    auth_version bigint not null default 1,
                    created_at timestamptz not null,
                    updated_at timestamptz not null
                );
                create table if not exists portal_invitations (
                    code_hash char(64) primary key,
                    chat_id bigint not null check (chat_id > 0),
                    actor text not null default 'sandra' check (actor in ('sandra', 'owner')),
                    reset boolean not null,
                    account_id uuid references portal_accounts(id),
                    created_at timestamptz not null,
                    expires_at timestamptz not null,
                    consumed_at timestamptz,
                    revoked_at timestamptz,
                    check ((reset and account_id is not null) or (not reset and account_id is null))
                );
                create index if not exists portal_invitations_scope_idx
                    on portal_invitations (chat_id, created_at desc);
                create table if not exists portal_sessions (
                    token_hash char(64) primary key,
                    account_id uuid not null references portal_accounts(id) on delete cascade,
                    auth_version bigint not null,
                    created_at timestamptz not null,
                    expires_at timestamptz not null,
                    revoked_at timestamptz
                );
                create index if not exists portal_sessions_account_idx on portal_sessions (account_id);
                create table if not exists portal_auth_limits (
                    bucket_key varchar(100) primary key,
                    window_start timestamptz not null,
                    attempts integer not null
                );
                alter table portal_accounts add column if not exists actor text not null
                    default 'sandra' check (actor in ('sandra', 'owner'));
                alter table portal_invitations add column if not exists actor text not null
                    default 'sandra' check (actor in ('sandra', 'owner'));
                create unique index if not exists portal_accounts_actor_idx on portal_accounts (actor);
            """)
        await self._dummy()

    @staticmethod
    async def _scope_lock(conn, chat_id):
        # Invitation creation and redemption use the same transaction-scoped lock.
        await conn.execute("select pg_advisory_xact_lock($1::bigint)", chat_id)

    @_storage_errors
    async def create_invitation(self, reset=False, actor="sandra"):
        if not isinstance(reset, bool):
            raise AccountError("invalid_invitation")
        chat_id, now = self._actor_id(actor), self._now()
        code = secrets.token_urlsafe(32)
        async with self.get_pool().acquire() as conn:
            async with conn.transaction():
                await self._scope_lock(conn, chat_id)
                account = await conn.fetchrow("select * from portal_accounts where chat_id = $1 for update", chat_id)
                if account and not reset:
                    raise AccountError("account_exists", 409)
                if not account and reset:
                    raise AccountError("no_account", 409)
                if self._actor_id(actor) != chat_id or account and self._bound_actor(account) != actor:
                    raise AccountError("account_identity_unavailable", 503)
                await conn.execute("""update portal_invitations set revoked_at = $2
                    where chat_id = $1 and consumed_at is null and revoked_at is null""", chat_id, now)
                await conn.execute("""insert into portal_invitations
                    (code_hash, chat_id, reset, account_id, created_at, expires_at, actor)
                    values ($1, $2, $3, $4, $5, $6, $7)""",
                    _digest(code), chat_id, reset, account["id"] if account else None, now, now + INVITATION_LIFETIME, actor)
        return {"code": code, "expires_at": _iso(now + INVITATION_LIFETIME), "reset": reset}

    @_storage_errors
    async def invitation_status(self, actor="sandra"):
        chat_id, now = self._actor_id(actor), self._now()
        async with self.get_pool().acquire() as conn:
            account = await conn.fetchval("select exists(select 1 from portal_accounts where chat_id = $1)", chat_id)
            row = await conn.fetchrow("""select expires_at, reset from portal_invitations
                where chat_id = $1 and consumed_at is null and revoked_at is null and expires_at > $2
                order by created_at desc limit 1""", chat_id, now)
        return {"has_account": bool(account), "active": row is not None,
                "expires_at": _iso(row["expires_at"]) if row else None, "reset": bool(row["reset"]) if row else False}

    @_storage_errors
    async def revoke_invitation(self, actor="sandra"):
        chat_id, now = self._actor_id(actor), self._now()
        async with self.get_pool().acquire() as conn:
            async with conn.transaction():
                await self._scope_lock(conn, chat_id)
                await conn.execute("""update portal_invitations set revoked_at = $2
                    where chat_id = $1 and consumed_at is null and revoked_at is null""", chat_id, now)
        return {"revoked": True}

    async def _new_session(self, conn, account, now):
        actor = self._bound_actor(account)
        if actor is None:
            raise AccountError("invalid_credentials", 401)
        raw = secrets.token_urlsafe(32)
        await conn.execute("""insert into portal_sessions
            (token_hash, account_id, auth_version, created_at, expires_at) values ($1, $2, $3, $4, $5)""",
            _digest(raw), account["id"], account["auth_version"], now, now + SESSION_LIFETIME)
        await conn.execute("delete from portal_sessions where account_id = $1 and expires_at <= $2", account["id"], now)
        return {"token": raw, "expires_at": _iso(now + SESSION_LIFETIME), "username": account["username"], "actor": actor}

    @_storage_errors
    async def register(self, code, username, password, ip=None):
        invalid_username = False
        try:
            username = self.normalize_username(username)
        except AccountError:
            username, invalid_username = "invalid", True
        await self._rate_limit("register", ip, username)
        if invalid_username:
            raise AccountError("invalid_username")
        if not isinstance(code, str) or not SECRET.fullmatch(code):
            raise AccountError("invalid_invitation")
        # Look up the invitation's fixed server-side identity before hashing. Recheck
        # the same record under the scope lock before consuming it below.
        async with self.get_pool().acquire() as conn:
            proposed = await conn.fetchrow("select * from portal_invitations where code_hash = $1", _digest(code))
        actor = self._bound_actor(proposed)
        if (actor is None or proposed["consumed_at"] is not None or proposed["revoked_at"] is not None
                or proposed["expires_at"] <= self._now()):
            raise AccountError("invalid_invitation")
        chat_id = proposed["chat_id"]
        password = self._password(password)
        password_hash = await self._hash(password)
        async with self.get_pool().acquire() as conn:
            async with conn.transaction():
                await self._scope_lock(conn, chat_id)
                invitation = await conn.fetchrow("select * from portal_invitations where code_hash = $1 for update", _digest(code))
                now = self._now()
                if (not invitation or invitation["chat_id"] != chat_id or invitation["consumed_at"] is not None
                        or invitation["revoked_at"] is not None or invitation["expires_at"] <= now
                        or self._bound_actor(invitation) != actor):
                    raise AccountError("invalid_invitation")
                account = await conn.fetchrow("select * from portal_accounts where chat_id = $1 for update", chat_id)
                if invitation["reset"]:
                    if (not account or self._bound_actor(account) != actor
                            or invitation["account_id"] != account["id"] or username != account["username"]):
                        raise AccountError("invalid_invitation")
                    account = await conn.fetchrow("""update portal_accounts set password_hash = $2,
                        auth_version = auth_version + 1, updated_at = $3 where id = $1 returning *""",
                        account["id"], password_hash, now)
                    await conn.execute("update portal_sessions set revoked_at = $2 where account_id = $1 and revoked_at is null",
                                       account["id"], now)
                else:
                    if account:
                        raise AccountError("invalid_invitation")
                    existing = await conn.fetchval("select exists(select 1 from portal_accounts where username = $1)", username)
                    if existing:
                        raise AccountError("invalid_invitation")
                    account = await conn.fetchrow("""insert into portal_accounts
                        (id, chat_id, username, password_hash, auth_version, created_at, updated_at, actor)
                        values ($1, $2, $3, $4, 1, $5, $5, $6) returning *""", uuid4(), chat_id, username, password_hash, now, actor)
                await conn.execute("update portal_invitations set consumed_at = $2 where code_hash = $1", _digest(code), now)
                # Revoke every outstanding code, including reset links created in another tab.
                await conn.execute("""update portal_invitations set revoked_at = $2
                    where chat_id = $1 and consumed_at is null and revoked_at is null""", chat_id, now)
                result = await self._new_session(conn, account, now)
        return result

    @_storage_errors
    async def login(self, username, password, ip=None):
        invalid_username = False
        try:
            normalized = self.normalize_username(username)
        except AccountError:
            normalized, invalid_username = "invalid", True
        await self._rate_limit("login", ip, normalized)
        try:
            password = self._password(password)
        except AccountError:
            raise AccountError("invalid_credentials", 401) from None
        async with self.get_pool().acquire() as conn:
            account = await conn.fetchrow("select * from portal_accounts where username = $1", normalized)
        actor = self._bound_actor(account)
        if invalid_username or actor is None:
            account = None
        valid = await self._verify(account["password_hash"] if account else await self._dummy(), password)
        if not account or not valid:
            raise AccountError("invalid_credentials", 401)
        # A reset or administrative revocation during Argon2 verification must not
        # create a new valid session from an already-obsolete password.
        async with self.get_pool().acquire() as conn:
            async with conn.transaction():
                current = await conn.fetchrow("select * from portal_accounts where id = $1 for update", account["id"])
                if (not current or current["auth_version"] != account["auth_version"]
                        or current["password_hash"] != account["password_hash"] or self._bound_actor(current) != actor):
                    raise AccountError("invalid_credentials", 401)
                if self.hasher.check_needs_rehash(current["password_hash"]):
                    new_hash = await self._hash(password)
                    await conn.execute("update portal_accounts set password_hash = $2, updated_at = $3 where id = $1",
                                       current["id"], new_hash, self._now())
                result = await self._new_session(conn, current, self._now())
        return result

    @_storage_errors
    async def get_session(self, raw_token):
        if not isinstance(raw_token, str) or not SECRET.fullmatch(raw_token):
            return None
        now = self._now()
        async with self.get_pool().acquire() as conn:
            row = await conn.fetchrow("""select a.username, a.chat_id, s.expires_at, a.actor from portal_sessions s
                join portal_accounts a on a.id = s.account_id and a.auth_version = s.auth_version
                where s.token_hash = $1 and s.revoked_at is null and s.expires_at > $2""",
                _digest(raw_token), now)
        actor = self._bound_actor(row)
        if not row or row["expires_at"] <= self._now() or actor is None:
            return None
        return {"actor": actor, "chat_id": row["chat_id"], "username": row["username"],
                "expires_at": _iso(row["expires_at"])}

    @_storage_errors
    async def logout(self, raw_token):
        if isinstance(raw_token, str) and SECRET.fullmatch(raw_token):
            async with self.get_pool().acquire() as conn:
                await conn.execute("update portal_sessions set revoked_at = $2 where token_hash = $1 and revoked_at is null",
                                   _digest(raw_token), self._now())
        return {"logged_out": True}

    @_storage_errors
    async def revoke_sessions(self, actor="sandra"):
        chat_id, now = self._actor_id(actor), self._now()
        async with self.get_pool().acquire() as conn:
            async with conn.transaction():
                await self._scope_lock(conn, chat_id)
                account = await conn.fetchrow("""update portal_accounts set auth_version = auth_version + 1,
                    updated_at = $2 where chat_id = $1 returning *""", chat_id, now)
                if account:
                    await conn.execute("update portal_sessions set revoked_at = $2 where account_id = $1 and revoked_at is null",
                                       account["id"], now)
        return {"revoked": True}
