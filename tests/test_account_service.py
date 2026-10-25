"""Account lifecycle and races with a transactional in-memory PostgreSQL adapter.

Password hashing is real Argon2id. No production database, network or user data.
"""

import asyncio
import copy
import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from account_service import AccountError, AccountService, INVITATION_LIFETIME, RATE_WINDOW, SESSION_LIFETIME


PASSWORD = "Un secreto de prueba 2026!"
NEW_PASSWORD = "Otro secreto de prueba 2026!"
STAMP = datetime(2026, 10, 22, 10, tzinfo=timezone.utc)


class Transaction:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        await self.conn.pool.lock.acquire()
        self.conn.local = copy.deepcopy(self.conn.pool.data)
        return self

    async def __aexit__(self, kind, value, traceback):
        if kind is None:
            self.conn.pool.data = self.conn.local
        self.conn.local = None
        self.conn.pool.lock.release()


class Connection:
    def __init__(self, pool):
        self.pool = pool
        self.local = None

    @property
    def data(self):
        return self.local if self.local is not None else self.pool.data

    def transaction(self):
        return Transaction(self)

    def query(self, query, args):
        query = " ".join(query.lower().split())
        self.pool.calls.append((query, args))
        if self.pool.fail_on and self.pool.fail_on in query:
            raise RuntimeError("Simulated database failure with private parameters")
        return query

    async def execute(self, query, *args):
        query = self.query(query, args)
        if query.startswith("create table") or "pg_advisory_xact_lock" in query:
            return "OK"
        if query.startswith("delete from portal_auth_limits"):
            self.data["limits"] = {key: value for key, value in self.data["limits"].items() if value[0] >= args[0]}
        elif query.startswith("insert into portal_invitations"):
            code_hash, chat_id, reset, account_id, created_at, expires_at, actor = args
            if code_hash in self.data["invitations"]:
                raise AssertionError("Unique code constraint")
            self.data["invitations"][code_hash] = dict(code_hash=code_hash, chat_id=chat_id, reset=reset,
                account_id=account_id, created_at=created_at, expires_at=expires_at, actor=actor, consumed_at=None, revoked_at=None)
        elif query.startswith("update portal_invitations set revoked_at"):
            for row in self.data["invitations"].values():
                if row["chat_id"] == args[0] and row["consumed_at"] is None and row["revoked_at"] is None:
                    row["revoked_at"] = args[1]
        elif query.startswith("update portal_invitations set consumed_at"):
            self.data["invitations"][args[0]]["consumed_at"] = args[1]
        elif query.startswith("insert into portal_sessions"):
            token_hash, account_id, auth_version, created_at, expires_at = args
            if token_hash in self.data["sessions"]:
                raise AssertionError("Unique session constraint")
            self.data["sessions"][token_hash] = dict(token_hash=token_hash, account_id=account_id,
                auth_version=auth_version, created_at=created_at, expires_at=expires_at, revoked_at=None)
        elif query.startswith("update portal_sessions set revoked_at"):
            key = "token_hash" if "where token_hash" in query else "account_id"
            for row in self.data["sessions"].values():
                if row[key] == args[0] and row["revoked_at"] is None:
                    row["revoked_at"] = args[1]
        elif query.startswith("delete from portal_sessions"):
            self.data["sessions"] = {key: row for key, row in self.data["sessions"].items()
                                     if not (row["account_id"] == args[0] and row["expires_at"] <= args[1])}
        elif query.startswith("update portal_accounts set password_hash"):
            self.data["accounts"][args[0]]["password_hash"] = args[1]
            self.data["accounts"][args[0]]["updated_at"] = args[2]
        else:
            raise AssertionError(f"Unexpected execute: {query}")
        return "OK"

    async def fetchval(self, query, *args):
        query = self.query(query, args)
        if query.startswith("insert into portal_auth_limits"):
            bucket, now, cutoff = args
            start, attempts = self.data["limits"].get(bucket, (now, 0))
            if start <= cutoff:
                start, attempts = now, 0
            self.data["limits"][bucket] = (start, attempts + 1)
            return attempts + 1
        if "select exists(select 1 from portal_accounts" in query:
            key = "chat_id" if "where chat_id" in query else "username"
            return any(row[key] == args[0] for row in self.data["accounts"].values())
        raise AssertionError(f"Unexpected fetchval: {query}")

    async def fetchrow(self, query, *args):
        query = self.query(query, args)
        if query.startswith("select * from portal_accounts"):
            if "where chat_id" in query:
                rows = [row for row in self.data["accounts"].values() if row["chat_id"] == args[0]]
            elif "where username" in query:
                rows = [row for row in self.data["accounts"].values()
                        if row["username"] == args[0] and (len(args) == 1 or row["chat_id"] == args[1])]
            else:
                rows = [self.data["accounts"][args[0]]] if args[0] in self.data["accounts"] else []
            return copy.deepcopy(rows[0]) if rows else None
        if query.startswith("select * from portal_invitations"):
            return copy.deepcopy(self.data["invitations"].get(args[0]))
        if query.startswith("select expires_at, reset from portal_invitations"):
            rows = [row for row in self.data["invitations"].values() if row["chat_id"] == args[0]
                    and row["consumed_at"] is None and row["revoked_at"] is None and row["expires_at"] > args[1]]
            rows.sort(key=lambda row: row["created_at"], reverse=True)
            return copy.deepcopy(rows[0]) if rows else None
        if query.startswith("insert into portal_accounts"):
            identity, chat_id, username, password_hash, now, actor = args
            if any(row["chat_id"] == chat_id or row["username"] == username or row["actor"] == actor
                   for row in self.data["accounts"].values()):
                raise AssertionError("Unique account constraint")
            row = dict(id=identity, chat_id=chat_id, username=username, password_hash=password_hash,
                       auth_version=1, created_at=now, updated_at=now, actor=actor)
            self.data["accounts"][identity] = row
            return copy.deepcopy(row)
        if query.startswith("update portal_accounts set password_hash"):
            row = self.data["accounts"][args[0]]
            row.update(password_hash=args[1], updated_at=args[2], auth_version=row["auth_version"] + 1)
            return copy.deepcopy(row)
        if query.startswith("update portal_accounts set auth_version"):
            row = next((row for row in self.data["accounts"].values() if row["chat_id"] == args[0]), None)
            if row:
                row.update(auth_version=row["auth_version"] + 1, updated_at=args[1])
            return copy.deepcopy(row)
        if query.startswith("select a.username, a.chat_id, s.expires_at"):
            session = self.data["sessions"].get(args[0])
            if not session or session["revoked_at"] is not None or session["expires_at"] <= args[1]:
                return None
            account = self.data["accounts"].get(session["account_id"])
            if not account or account["auth_version"] != session["auth_version"]:
                return None
            return dict(username=account["username"], chat_id=account["chat_id"], expires_at=session["expires_at"], actor=account["actor"])
        raise AssertionError(f"Unexpected fetchrow: {query}")


class Acquire:
    def __init__(self, pool):
        self.conn = Connection(pool)

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *args):
        pass


class MemoryPool:
    def __init__(self):
        self.data = {name: {} for name in ("accounts", "invitations", "sessions", "limits")}
        self.lock = asyncio.Lock()
        self.calls = []
        self.fail_on = None

    def acquire(self):
        return Acquire(self)


class AccountTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.pool = MemoryPool()
        self.now = STAMP
        self.identities = {"sandra": 11, "owner": 22}
        self.service = self.new_service()
        await self.service.initialize()

    def new_service(self):
        return AccountService(lambda actor: self.identities.get(actor), pool=self.pool, clock=lambda: self.now)

    async def register(self, username="Patita"):
        invite = await self.service.create_invitation()
        session = await self.service.register(invite["code"], username, PASSWORD, "192.0.2.1")
        return invite, session

    async def assert_error(self, code, call, status=None):
        with self.assertRaises(AccountError) as raised:
            await call
        self.assertEqual(raised.exception.code, code)
        if status:
            self.assertEqual(raised.exception.status, status)

    async def test_invitation_registration_hashes_and_server_bound_identity(self):
        invite, session = await self.register("  ＰＡＴＩＴＡ  ")
        self.assertEqual(len(invite["code"]), 43)
        self.assertEqual(len(session["token"]), 43)
        self.assertEqual(session["username"], "patita")
        self.assertEqual(session["actor"], "sandra")
        account = next(iter(self.pool.data["accounts"].values()))
        self.assertEqual(account["chat_id"], 11)
        self.assertTrue(account["password_hash"].startswith("$argon2id$v=19$m=65536,t=3,p=4$"))
        self.assertNotEqual(account["password_hash"], PASSWORD)
        stored = str(self.pool.data)
        for secret in (PASSWORD, session["token"], invite["code"], "192.0.2.1"):
            self.assertNotIn(secret, stored)
        result = await self.service.get_session(session["token"])
        self.assertEqual(result, {"actor": "sandra", "chat_id": 11, "username": "patita",
                                 "expires_at": (STAMP + SESSION_LIFETIME).isoformat()})
        self.assertEqual(await self.service.invitation_status(),
            {"has_account": True, "active": False, "expires_at": None, "reset": False})

    async def test_one_use_under_concurrent_redemption_and_restart(self):
        invite = await self.service.create_invitation()
        other_process = self.new_service()
        results = await asyncio.gather(
            self.service.register(invite["code"], "patita", PASSWORD, "192.0.2.1"),
            other_process.register(invite["code"], "sandrita", PASSWORD, "192.0.2.2"), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        errors = [result for result in results if isinstance(result, AccountError)]
        self.assertEqual([error.code for error in errors], ["invalid_invitation"])
        self.assertEqual(len(self.pool.data["accounts"]), 1)
        self.assertEqual(len(self.pool.data["sessions"]), 1)
        token = next(result["token"] for result in results if isinstance(result, dict))
        self.assertIsNotNone(await self.new_service().get_session(token))
        await self.assert_error("invalid_invitation", self.new_service().register(invite["code"], "patita", PASSWORD))

    async def test_expired_revoked_replaced_and_unknown_invitations_are_rejected(self):
        old = await self.service.create_invitation()
        fresh = await self.service.create_invitation()
        await self.assert_error("invalid_invitation", self.service.register(old["code"], "patita", PASSWORD))
        await self.service.revoke_invitation()
        await self.assert_error("invalid_invitation", self.service.register(fresh["code"], "patita", PASSWORD))
        current = await self.service.create_invitation()
        self.now += INVITATION_LIFETIME
        await self.assert_error("invalid_invitation", self.service.register(current["code"], "patita", PASSWORD))
        await self.assert_error("invalid_invitation", self.service.register("x" * 43, "patita", PASSWORD))
        self.assertFalse((await self.service.invitation_status())["active"])
        self.assertEqual(self.pool.data["accounts"], {})

    async def test_expiry_checked_after_waiting_for_redemption_lock(self):
        invite = await self.service.create_invitation()
        reached, release = asyncio.Event(), asyncio.Event()
        original = self.service._scope_lock
        async def gated(conn, chat_id):
            await original(conn, chat_id)
            reached.set()
            await release.wait()
        with patch.object(self.service, "_scope_lock", gated):
            pending = asyncio.create_task(self.service.register(invite["code"], "patita", PASSWORD))
            await reached.wait()
            self.now += INVITATION_LIFETIME + timedelta(seconds=1)
            release.set()
            await self.assert_error("invalid_invitation", pending)
        self.assertEqual(self.pool.data["accounts"], {})

    async def test_invitation_cannot_follow_changed_binding_or_owner_identity(self):
        invite = await self.service.create_invitation()
        self.identities["sandra"] = 33
        await self.assert_error("invalid_invitation", self.service.register(invite["code"], "patita", PASSWORD))
        self.identities["sandra"] = 22
        await self.assert_error("account_identity_unavailable", self.service.create_invitation(), 503)
        self.assertEqual(self.pool.data["accounts"], {})

    async def test_password_login_errors_are_generic_and_session_is_fresh(self):
        _, first = await self.register()
        for username, password in (("patita", "Una contraseña errónea"), ("desconocida", PASSWORD), ("patita", "corta")):
            await self.assert_error("invalid_credentials", self.service.login(username, password, "192.0.2.1"), 401)
        next_session = await self.service.login("PATITA", PASSWORD, "192.0.2.1")
        self.assertNotEqual(first["token"], next_session["token"])
        self.assertIsNotNone(await self.service.get_session(next_session["token"]))
        _, record = self.pool.calls[-1]
        self.assertNotIn(PASSWORD, str(record))

    async def test_invalid_username_does_not_authenticate_literal_invalid_account(self):
        await self.register("invalid")
        for malformed in ("", "*", "x" * 100, None):
            await self.assert_error("invalid_credentials", self.service.login(malformed, PASSWORD, "192.0.2.1"), 401)
        self.assertIsNotNone(await self.service.login("invalid", PASSWORD, "192.0.2.1"))

    async def test_password_and_username_policy_are_explicit_at_registration(self):
        invite = await self.service.create_invitation()
        for username in ("ab", "bad user", "x" * 33):
            await self.assert_error("invalid_username", self.service.register(invite["code"], username, PASSWORD))
        for password in ("", "x" * 129, None, 123):
            await self.assert_error("invalid_password", self.service.register(invite["code"], "patita", password))
        self.assertFalse(self.pool.data["accounts"])

    async def test_reset_requires_account_and_revokes_every_old_session(self):
        await self.assert_error("no_account", self.service.create_invitation(reset=True), 409)
        _, first = await self.register()
        second = await self.service.login("patita", PASSWORD, "192.0.2.1")
        await self.assert_error("account_exists", self.service.create_invitation(), 409)
        invitation = await self.service.create_invitation(reset=True)
        status = await self.service.invitation_status()
        self.assertEqual((status["has_account"], status["active"], status["reset"]), (True, True, True))
        await self.assert_error("invalid_invitation", self.service.register(invitation["code"], "otra", NEW_PASSWORD))
        reset = await self.service.register(invitation["code"], "patita", NEW_PASSWORD, "192.0.2.1")
        for old in (first, second):
            self.assertIsNone(await self.service.get_session(old["token"]))
        self.assertIsNotNone(await self.service.get_session(reset["token"]))
        await self.assert_error("invalid_credentials", self.service.login("patita", PASSWORD, "192.0.2.1"), 401)
        self.assertIsNotNone(await self.service.login("patita", NEW_PASSWORD, "192.0.2.1"))

    async def test_logout_expiry_owner_revocation_and_binding_isolation(self):
        _, session = await self.register()
        await self.service.logout(session["token"])
        self.assertIsNone(await self.service.get_session(session["token"]))
        self.assertEqual(await self.service.logout("bad-token"), {"logged_out": True})
        session = await self.service.login("patita", PASSWORD, "192.0.2.1")
        self.identities["sandra"] = 33
        self.assertIsNone(await self.service.get_session(session["token"]))
        self.identities["sandra"] = 11
        await self.service.revoke_sessions()
        self.assertIsNone(await self.service.get_session(session["token"]))
        session = await self.service.login("patita", PASSWORD, "192.0.2.1")
        self.now += SESSION_LIFETIME
        self.assertIsNone(await self.service.get_session(session["token"]))

    async def test_login_in_flight_cannot_survive_password_reset(self):
        await self.register()
        invite = await self.service.create_invitation(reset=True)
        verified, release = asyncio.Event(), asyncio.Event()
        original = self.service._verify
        async def gated(password_hash, password):
            result = await original(password_hash, password)
            verified.set()
            await release.wait()
            return result
        with patch.object(self.service, "_verify", gated):
            pending = asyncio.create_task(self.service.login("patita", PASSWORD, "192.0.2.2"))
            await verified.wait()
            changed = await self.new_service().register(invite["code"], "patita", NEW_PASSWORD, "192.0.2.1")
            release.set()
            await self.assert_error("invalid_credentials", pending, 401)
        self.assertEqual(len([row for row in self.pool.data["sessions"].values() if row["revoked_at"] is None]), 1)
        self.assertIsNotNone(await self.service.get_session(changed["token"]))

    async def test_registration_failure_rolls_back_account_invitation_and_session(self):
        invite = await self.service.create_invitation()
        self.pool.fail_on = "insert into portal_sessions"
        await self.assert_error("accounts_unavailable", self.service.register(invite["code"], "patita", PASSWORD), 503)
        self.assertFalse(self.pool.data["accounts"])
        self.assertFalse(self.pool.data["sessions"])
        self.assertTrue((await self.service.invitation_status())["active"])
        self.pool.fail_on = None
        self.assertIsNotNone(await self.service.register(invite["code"], "patita", PASSWORD))

    async def test_account_login_limit_survives_restart_different_ips_and_resets_after_window(self):
        with patch.object(self.service, "_verify", AsyncMock(return_value=False)):
            for i in range(10):
                await self.assert_error("invalid_credentials", self.service.login("unknown", PASSWORD, f"192.0.2.{i + 1}"), 401)
        restarted = self.new_service()
        await self.assert_error("rate_limited", restarted.login("unknown", PASSWORD, "198.51.100.1"), 429)
        self.now += RATE_WINDOW
        with patch.object(restarted, "_verify", AsyncMock(return_value=False)):
            await self.assert_error("invalid_credentials", restarted.login("unknown", PASSWORD, "198.51.100.1"), 401)

    async def test_ip_login_limit_cannot_be_bypassed_by_changing_usernames(self):
        with patch.object(self.service, "_verify", AsyncMock(return_value=False)):
            for i in range(40):
                await self.assert_error("invalid_credentials", self.service.login(f"unknown{i}", PASSWORD, "192.0.2.1"), 401)
            await self.assert_error("rate_limited", self.new_service().login("different", PASSWORD, "192.0.2.1"), 429)

    async def test_register_limits_apply_to_account_and_ip_without_storing_raw_identifiers(self):
        for i in range(5):
            await self.assert_error("invalid_invitation", self.service.register("bad", "patita", PASSWORD, f"192.0.2.{i + 1}"))
        await self.assert_error("rate_limited", self.new_service().register("bad", "patita", PASSWORD, "198.51.100.1"), 429)
        for i in range(20):
            await self.assert_error("invalid_invitation", self.service.register("bad", f"other{i}", PASSWORD, "203.0.113.1"))
        await self.assert_error("rate_limited", self.service.register("bad", "newuser", PASSWORD, "203.0.113.1"), 429)
        self.assertNotIn("patita", str(self.pool.data["limits"]))
        self.assertNotIn("203.0.113.1", str(self.pool.data["limits"]))

    async def test_both_people_have_distinct_roles_and_can_register_with_one_character_passwords(self):
        sandra_invite = await self.service.create_invitation()
        sandra = await self.service.register(sandra_invite["code"], "patita", "ñ", "192.0.2.1")
        owner_invite = await self.service.create_invitation(actor="owner")
        owner = await self.service.register(owner_invite["code"], "miguel", "x", "192.0.2.2")
        self.assertEqual(owner["actor"], "owner")
        self.assertEqual(sandra["actor"], "sandra")
        self.assertEqual((await self.service.get_session(owner["token"]))["chat_id"], 22)
        self.assertEqual((await self.service.get_session(sandra["token"]))["chat_id"], 11)
        self.assertEqual((await self.service.login("miguel", "x"))["actor"], "owner")
        self.assertEqual((await self.service.login("patita", "ñ"))["actor"], "sandra")
        self.assertEqual(len(self.pool.data["accounts"]), 2)
        await self.assert_error("account_exists", self.service.create_invitation(actor="owner"), 409)
        await self.assert_error("account_identity_unavailable", self.service.create_invitation(actor="visitor"), 503)
        await self.assert_error("invalid_credentials", self.service.login("miguel", ""), 401)

    async def test_both_people_can_recover_with_short_passwords_preserved_exactly(self):
        for actor, username in (("sandra", "patita"), ("owner", "miguel")):
            with self.subTest(actor=actor):
                invitation = await self.service.create_invitation(actor=actor)
                first = await self.service.register(invitation["code"], username, "  ñ  ")
                await self.assert_error("invalid_credentials", self.service.login(username, "ñ"), 401)
                self.assertEqual((await self.service.login(username, "  ñ  "))["actor"], actor)
                recovery = await self.service.create_invitation(reset=True, actor=actor)
                for invalid in ("", "x" * 129):
                    await self.assert_error("invalid_password", self.service.register(recovery["code"], username, invalid))
                renewed = await self.service.register(recovery["code"], username, "z")
                self.assertEqual(renewed["actor"], actor)
                self.assertIsNone(await self.service.get_session(first["token"]))
                await self.assert_error("invalid_credentials", self.service.login(username, "  ñ  "), 401)
                self.assertEqual((await self.service.login(username, "z"))["actor"], actor)

    async def test_owner_invitation_does_not_replace_sandras_and_revocation_is_scoped(self):
        sandra_invite = await self.service.create_invitation()
        owner_invite = await self.service.create_invitation(actor="owner")
        self.assertTrue((await self.service.invitation_status())["active"])
        self.assertTrue((await self.service.invitation_status(actor="owner"))["active"])
        owner = await self.service.register(owner_invite["code"], "miguel", "x")
        sandra = await self.service.register(sandra_invite["code"], "patita", PASSWORD)
        await self.service.revoke_sessions(actor="owner")
        self.assertIsNone(await self.service.get_session(owner["token"]))
        self.assertIsNotNone(await self.service.get_session(sandra["token"]))
        reset = await self.service.create_invitation(reset=True, actor="owner")
        renewed = await self.service.register(reset["code"], "miguel", "y")
        self.assertEqual(renewed["actor"], "owner")
        await self.assert_error("invalid_credentials", self.service.login("miguel", "x"), 401)
        self.assertIsNotNone(await self.service.login("miguel", "y"))

    async def test_swapped_ids_never_promote_a_sandra_account_or_invitation(self):
        _, sandra = await self.register()
        owner_invite = await self.service.create_invitation(actor="owner")
        self.identities.update(sandra=22, owner=11)
        self.assertIsNone(await self.service.get_session(sandra["token"]))
        await self.assert_error("invalid_credentials", self.service.login("patita", PASSWORD), 401)
        await self.assert_error("invalid_invitation", self.service.register(owner_invite["code"], "miguel", "x"))

    async def test_role_mapping_is_rechecked_after_password_verification(self):
        invite = await self.service.create_invitation(actor="owner")
        owner = await self.service.register(invite["code"], "miguel", "x")
        verify = self.service._verify
        async def rebound(password_hash, password):
            result = await verify(password_hash, password)
            self.identities["owner"] = 33
            return result
        with patch.object(self.service, "_verify", rebound):
            await self.assert_error("invalid_credentials", self.service.login("miguel", "x"), 401)
        self.assertIsNone(await self.service.get_session(owner["token"]))

    async def test_real_login_sessions_enforce_two_person_portal_permissions(self):
        from aiohttp.test_utils import TestClient, TestServer
        from portal import COOKIE
        from web_bridge import WebBridge

        sandra_invite = await self.service.create_invitation()
        await self.service.register(sandra_invite["code"], "patita", "s")
        owner_invite = await self.service.create_invitation(actor="owner")
        await self.service.register(owner_invite["code"], "miguel", "x")
        bridge_data = {}
        def save(value):
            bridge_data.clear()
            bridge_data.update(value)
        bridge = WebBridge(lambda: copy.deepcopy(bridge_data), save, lambda: {},
            lambda actor: self.identities.get(actor), token="test-only-transport-secret-01234567890123456789",
            account_service=self.service, portal_origin="https://casa.example",
            get_admin_app=lambda: object(), admin_state_provider=lambda: {"marker": "owner-desk"})
        client = TestClient(TestServer(bridge.create_app()))
        await client.start_server()
        try:
            for username, password, role in (("patita", "s", "sandra"), ("miguel", "x", "owner")):
                response = await client.post("/api/account/login", json={"username": username, "password": password},
                                             headers={"Origin": "https://casa.example"})
                self.assertEqual(response.status, 200)
                self.assertEqual((await response.json())["actor"], role)
                cookie = {"Cookie": f"{COOKIE}={response.cookies[COOKIE].value}"}
                session = await client.get("/api/account/session", headers=cookie)
                self.assertEqual((await session.json())["actor"], role)
                desk = await client.get("/api/bridge/admin-state", headers={**cookie, "X-Castori-Actor": "owner"})
                self.assertEqual(desk.status, 200 if role == "owner" else 403)
                if role == "owner":
                    self.assertEqual((await desk.json())["marker"], "owner-desk")
                    action = await client.post("/api/bridge/message", json={"animal": "mimosuga", "text": "test"},
                                               headers={**cookie, "Origin": "https://casa.example"})
                    self.assertEqual(action.status, 403)
                    self.assertEqual((await action.json())["error"], "read_only")
                logout = await client.post("/api/account/logout", json={},
                                           headers={**cookie, "Origin": "https://casa.example"})
                self.assertEqual(logout.status, 200)
                denied = await client.get("/api/bridge/admin-state", headers=cookie)
                self.assertEqual(denied.status, 401)
        finally:
            await client.close()
            await bridge.close()


if __name__ == "__main__":
    unittest.main()
