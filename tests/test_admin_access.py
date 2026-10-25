"""Real password hashing and web gating with a transactional in-memory DB."""

import asyncio
import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from aiohttp.test_utils import TestClient, TestServer

from admin_access import AdminAccessError, AdminAccessService, RATE_LIMIT, RATE_WINDOW, SESSION_LIFETIME
from test_account_service import Transaction
from web_bridge import WebBridge


PASSWORD = "A private test phrase 2026!"
OWNER = "gateway-owner-test"
BRIDGE_TOKEN = "test-private-bridge-token-more-than-32-characters"
HEADERS = {"Authorization": "Bearer " + BRIDGE_TOKEN, "X-Castori-Actor": "owner", "X-Castori-Owner-Id": OWNER}
STAMP = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)


class Connection:
    def __init__(self, pool):
        self.pool, self.local = pool, None

    @property
    def data(self):
        return self.local if self.local is not None else self.pool.data

    def transaction(self):
        return Transaction(self)

    def query(self, query):
        if self.pool.fail:
            raise RuntimeError("Private SQL parameters must not escape")
        return " ".join(query.lower().split())

    async def execute(self, query, *args):
        query = self.query(query)
        if query.startswith("create table") or "pg_advisory_xact_lock" in query:
            return "OK"
        if query.startswith("insert into centralita_passwords"):
            chat_id, password_hash, now = args
            if chat_id in self.data["passwords"]:
                raise AssertionError("Duplicate owner")
            self.data["passwords"][chat_id] = password_hash
        elif query.startswith("insert into centralita_sessions"):
            key, chat_id, identity_hash, now, expires = args
            self.data["sessions"][key] = {"chat_id": chat_id, "identity_hash": identity_hash,
                "created_at": now, "expires_at": expires, "revoked_at": None}
        elif query.startswith("delete from centralita_sessions"):
            self.data["sessions"] = {key: row for key, row in self.data["sessions"].items()
                if not (row["chat_id"] == args[0] and row["expires_at"] <= args[1])}
        elif query.startswith("update centralita_sessions set revoked_at"):
            row = self.data["sessions"].get(args[0])
            if row and row["chat_id"] == args[1] and row["identity_hash"] == args[2] and row["revoked_at"] is None:
                row["revoked_at"] = args[3]
        else:
            raise AssertionError("Unexpected execute: " + query)
        return "OK"

    async def fetchval(self, query, *args):
        query = self.query(query)
        if query.startswith("insert into centralita_auth_limits"):
            chat_id, now, cutoff = args
            start, attempts = self.data["limits"].get(chat_id, (now, 0))
            if start <= cutoff:
                start, attempts = now, 0
            self.data["limits"][chat_id] = (start, attempts + 1)
            return attempts + 1
        if query.startswith("select exists(select 1 from centralita_passwords"):
            return args[0] in self.data["passwords"]
        if query.startswith("select password_hash from centralita_passwords"):
            return self.data["passwords"].get(args[0])
        if query.startswith("select expires_at from centralita_sessions"):
            row = self.data["sessions"].get(args[0])
            if row and row["chat_id"] == args[1] and row["identity_hash"] == args[2] and row["revoked_at"] is None and row["expires_at"] > args[3]:
                return row["expires_at"]
            return None
        raise AssertionError("Unexpected fetchval: " + query)


class Acquire:
    def __init__(self, pool):
        self.conn = Connection(pool)

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        pass


class MemoryPool:
    def __init__(self):
        self.data = {name: {} for name in ("passwords", "sessions", "limits")}
        self.lock = asyncio.Lock()
        self.fail = False

    def acquire(self):
        return Acquire(self)


class AdminAccessTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool, self.now = MemoryPool(), STAMP
        self.actors = {"owner": 22, "sandra": 11}
        self.service = AdminAccessService(self.actors.get, pool=self.pool, clock=lambda: self.now)
        await self.service.initialize()

    async def test_first_setup_hashes_password_and_session_and_status_never_returns_token(self):
        self.assertEqual(await self.service.status(OWNER), {"configured": False, "unlocked": False, "expires_at": None})
        session = await self.service.setup(OWNER, PASSWORD)
        self.assertTrue(session["unlocked"])
        self.assertEqual(session["expires_at"], (STAMP + SESSION_LIFETIME).isoformat())
        self.assertTrue(self.pool.data["passwords"][22].startswith("$argon2id$"))
        serialized = json.dumps(self.pool.data, default=str)
        self.assertNotIn(PASSWORD, serialized)
        self.assertNotIn(session["session_token"], serialized)
        self.assertNotIn(OWNER, serialized)
        status = await self.service.status(OWNER, session["session_token"])
        self.assertEqual(set(status), {"configured", "unlocked", "expires_at"})
        self.assertTrue(status["unlocked"])

    async def test_setup_cannot_replace_password_and_concurrent_setup_has_one_winner(self):
        outcomes = await asyncio.gather(self.service.setup(OWNER, PASSWORD),
            self.service.setup(OWNER, "Another password for test"), return_exceptions=True)
        self.assertEqual(sum(isinstance(value, dict) for value in outcomes), 1)
        error = next(value for value in outcomes if isinstance(value, AdminAccessError))
        self.assertEqual((error.code, error.status), ("admin_already_configured", 409))
        self.assertEqual(len(self.pool.data["sessions"]), 1)

    async def test_unlock_requires_correct_password_and_does_not_return_stored_secret(self):
        with self.assertRaises(AdminAccessError) as missing:
            await self.service.unlock(OWNER, PASSWORD)
        self.assertEqual(missing.exception.code, "admin_setup_required")
        original = await self.service.setup(OWNER, PASSWORD)
        await self.service.lock(OWNER, original["session_token"])
        with self.assertRaises(AdminAccessError) as wrong:
            await self.service.unlock(OWNER, "Wrong password for test")
        self.assertEqual((wrong.exception.code, wrong.exception.status), ("invalid_admin_password", 401))
        self.assertFalse((await self.service.status(OWNER, original["session_token"]))["unlocked"])
        fresh = await self.service.unlock(OWNER, PASSWORD)
        self.assertNotEqual(fresh["session_token"], original["session_token"])
        self.assertTrue((await self.service.status(OWNER, fresh["session_token"]))["unlocked"])

    async def test_single_character_password_setup_and_unlock_keep_hashing_and_exact_match(self):
        original = await self.service.setup(OWNER, "x")
        self.assertTrue(self.pool.data["passwords"][22].startswith("$argon2id$"))
        await self.service.lock(OWNER, original["session_token"])
        with self.assertRaises(AdminAccessError) as wrong:
            await self.service.unlock(OWNER, "y")
        self.assertEqual((wrong.exception.code, wrong.exception.status), ("invalid_admin_password", 401))
        fresh = await self.service.unlock(OWNER, "x")
        self.assertTrue((await self.service.status(OWNER, fresh["session_token"]))["unlocked"])
        self.assertFalse((await self.service.status(OWNER, original["session_token"]))["unlocked"])

    async def test_empty_oversized_and_nonstring_passwords_rejected_before_storage(self):
        for method in (self.service.setup, self.service.unlock):
            for password in ("", "x" * 129, None, 123):
                with self.subTest(method=method.__name__, password_type=type(password).__name__):
                    with self.assertRaises(AdminAccessError) as invalid:
                        await method(OWNER, password)
                    self.assertEqual((invalid.exception.code, invalid.exception.status), ("invalid_password", 400))
        self.assertFalse(self.pool.data["passwords"])
        self.assertFalse(self.pool.data["sessions"])

    async def test_128_characters_are_accepted_without_trimming_spaces(self):
        password = " " + "x" * 126 + " "
        original = await self.service.setup(OWNER, password)
        await self.service.lock(OWNER, original["session_token"])
        with self.assertRaises(AdminAccessError) as trimmed:
            await self.service.unlock(OWNER, password.strip())
        self.assertEqual(trimmed.exception.code, "invalid_admin_password")
        fresh = await self.service.unlock(OWNER, password)
        self.assertTrue((await self.service.status(OWNER, fresh["session_token"]))["unlocked"])

    async def test_session_expiry_identity_binding_revocation_and_owner_rebinding(self):
        session = await self.service.setup(OWNER, PASSWORD)
        token = session["session_token"]
        self.assertFalse((await self.service.status("another-gateway-owner", token))["unlocked"])
        await self.service.lock("another-gateway-owner", token)
        self.assertTrue((await self.service.status(OWNER, token))["unlocked"])
        self.actors["owner"] = 23
        self.assertFalse((await self.service.status(OWNER, token))["unlocked"])
        self.actors["owner"] = 22
        self.now += SESSION_LIFETIME
        self.assertFalse((await self.service.status(OWNER, token))["unlocked"])
        self.now = STAMP
        await self.service.lock(OWNER, token)
        self.assertFalse((await self.service.status(OWNER, token))["unlocked"])

    async def test_rate_limit_persists_and_cannot_be_evaded_with_gateway_identity(self):
        for attempt in range(RATE_LIMIT):
            with self.assertRaises(AdminAccessError) as invalid:
                await self.service.unlock("gateway-" + str(attempt), "")
            self.assertEqual(invalid.exception.code, "invalid_password")
        restarted = AdminAccessService(self.actors.get, pool=self.pool, clock=lambda: self.now)
        with self.assertRaises(AdminAccessError) as limited:
            await restarted.setup(OWNER, PASSWORD)
        self.assertEqual((limited.exception.code, limited.exception.status), ("rate_limited", 429))
        self.now += RATE_WINDOW
        self.assertTrue((await restarted.setup(OWNER, PASSWORD))["unlocked"])

    async def test_invalid_identity_and_storage_failures_are_closed_and_sanitized(self):
        for value in (None, "", " user", "a\nb", "x" * 257):
            with self.assertRaises(AdminAccessError) as missing:
                await self.service.status(value)
            self.assertEqual(missing.exception.code, "owner_identity_required")
        self.pool.fail = True
        for operation in (self.service.status(OWNER), self.service.setup(OWNER, PASSWORD), self.service.unlock(OWNER, PASSWORD), self.service.lock(OWNER)):
            with self.assertRaises(AdminAccessError) as failure:
                await operation
            self.assertEqual(str(failure.exception), "admin_auth_unavailable")
            self.assertEqual(failure.exception.status, 503)


class AdminAccessTransportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool, self.now, self.data = MemoryPool(), STAMP, {}
        self.service = AdminAccessService(lambda actor: {"owner": 22, "sandra": 11}.get(actor),
            pool=self.pool, clock=lambda: self.now)
        await self.service.initialize()
        self.provider = AsyncMock(return_value={"counts": {"stories_pending": 9}})
        self.bridge = WebBridge(lambda: copy.deepcopy(self.data), lambda data: setattr(self, "data", data), lambda: {},
            lambda actor: {"owner": 22, "sandra": 11}.get(actor), token=BRIDGE_TOKEN,
            admin_access=self.service, get_admin_app=lambda: object(), admin_state_provider=self.provider)
        self.client = TestClient(TestServer(self.bridge.create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.bridge.close()

    async def test_all_admin_routes_fail_closed_before_setup_and_sandra_cannot_setup(self):
        for path, method, body in (("admin-state", "get", None), ("admin-events", "get", None),
                ("admin-invitation", "get", None), ("admin-invitation", "post", {"action": "create"}),
                ("admin-action", "post", {"text": "/status", "request_id": "testadmin1"}),
                ("admin-callback", "post", {"event_id": 1, "data": "x", "request_id": "testadmin2"})):
            response = await getattr(self.client, method)("/castori-web/" + path, headers=HEADERS, **({"json": body} if body is not None else {}))
            self.assertEqual(response.status, 423)
            self.assertEqual(await response.json(), {"error": "admin_locked"})
        for method in ("get", "post"):
            response = await getattr(self.client, method)("/castori-web/admin-auth", headers={**HEADERS, "X-Castori-Actor": "sandra"},
                **({"json": {"action": "setup", "password": PASSWORD}} if method == "post" else {}))
            self.assertEqual(response.status, 403)
        self.provider.assert_not_awaited()
        self.assertFalse(self.pool.data["passwords"])

    async def test_setup_unlock_lock_expiry_and_request_receipt_enforced_by_transport(self):
        response = await self.client.post("/castori-web/admin-auth", headers=HEADERS, json={"action": "setup", "password": "x"})
        self.assertEqual(response.status, 200)
        session = await response.json()
        headers = {**HEADERS, "X-Castori-Admin-Session": session["session_token"]}
        response = await self.client.get("/castori-web/admin-state", headers=headers)
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["counts"], {"stories_pending": 9})
        self.bridge._reserve("22:admin-test-1", "test-fingerprint", admin=True)
        self.assertEqual((await self.client.get("/castori-web/request?request_id=admin-test-1", headers=HEADERS)).status, 423)
        self.assertEqual((await self.client.get("/castori-web/request?request_id=admin-test-1", headers=headers)).status, 200)
        self.bridge._reserve("22:chat-test-1", "chat-fingerprint")
        self.assertEqual((await self.client.get("/castori-web/request?request_id=chat-test-1", headers=HEADERS)).status, 200)
        response = await self.client.post("/castori-web/admin-auth", headers=headers, json={"action": "lock"})
        self.assertEqual(await response.json(), {"configured": True, "unlocked": False, "expires_at": None})
        self.assertEqual((await self.client.get("/castori-web/admin-state", headers=headers)).status, 423)
        response = await self.client.post("/castori-web/admin-auth", headers=HEADERS, json={"action": "unlock", "password": "x"})
        self.assertEqual(response.status, 200)
        fresh = await response.json()
        self.now += SESSION_LIFETIME
        self.assertEqual((await self.client.get("/castori-web/admin-state", headers={**HEADERS, "X-Castori-Admin-Session": fresh["session_token"]})).status, 423)

    async def test_transport_rejects_empty_and_oversized_passwords(self):
        for action in ("setup", "unlock"):
            for password in ("", "x" * 129):
                response = await self.client.post("/castori-web/admin-auth", headers=HEADERS,
                    json={"action": action, "password": password})
                self.assertEqual(response.status, 400)
                self.assertEqual(await response.json(), {"error": "invalid_password"})
        self.assertFalse(self.pool.data["passwords"])
        self.assertFalse(self.pool.data["sessions"])

    async def test_auth_exact_body_owner_identity_and_storage_errors(self):
        for body in ({"action": "setup", "password": PASSWORD, "owner": "spoof"}, {"action": "reset", "password": PASSWORD},
                {"action": "lock", "password": PASSWORD}, ["setup"], {"action": {"bad": True}}):
            response = await self.client.post("/castori-web/admin-auth", headers=HEADERS, json=body)
            self.assertEqual(response.status, 400)
        no_identity = {key: value for key, value in HEADERS.items() if key != "X-Castori-Owner-Id"}
        self.assertEqual((await self.client.get("/castori-web/admin-auth", headers=no_identity)).status, 403)
        self.assertEqual((await self.client.get("/castori-web/admin-auth?owner=spoof", headers=HEADERS)).status, 400)
        self.assertEqual((await self.client.post("/castori-web/admin-auth", headers=HEADERS, data='{}')).status, 415)
        self.bridge.admin_access = None
        for path in ("admin-auth", "admin-state"):
            response = await self.client.get("/castori-web/" + path, headers=HEADERS)
            self.assertEqual(response.status, 503)
            self.assertEqual(await response.json(), {"error": "admin_auth_unavailable"})


if __name__ == "__main__":
    unittest.main()
