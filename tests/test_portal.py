import copy
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

from aiohttp.test_utils import TestClient, TestServer

from portal import COOKIE, canonical_origin
from web_bridge import WebBridge

TOKEN = "internal-token-only-never-sent-to-a-browser-12345"
ORIGIN = "https://casa.example"
OWNER = {"Authorization": "Bearer " + TOKEN, "X-Castori-Actor": "owner"}
SESSION = "session-for-test"


class PortalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name) / "portal"
        self.root.mkdir()
        (self.root / "index.html").write_text("<h1>La casa</h1>")
        (self.root / "app.js").write_text("'use strict';")
        (self.root / "data.json").write_text('"must not be served"')
        (self.root.parent / "secret.html").write_text("must not escape")
        self.accounts = AsyncMock()
        self.accounts.get_session.side_effect = lambda raw: ({"actor": "sandra", "chat_id": 11, "username": "patita"}
                                                              if raw == SESSION else None)
        self.accounts.invitation_status.return_value = {"has_account": False, "active": False, "expires_at": None, "reset": False}
        self.accounts.create_invitation.return_value = {"code": "one-time-code", "expires_at": "2026-10-23T00:00:00+00:00", "reset": False}
        self.accounts.register.return_value = self.accounts.login.return_value = {
            "token": SESSION, "username": "patita", "expires_at": datetime.now(timezone.utc) + timedelta(days=7)}
        self.data = {}
        self.bridge = WebBridge(lambda: copy.deepcopy(self.data), lambda data: setattr(self, "data", data),
                                lambda: {}, lambda role: {"owner": 22, "sandra": 11}.get(role), token=TOKEN,
                                account_service=self.accounts, portal_origin=ORIGIN, portal_root=self.root)
        self.client = TestClient(TestServer(self.bridge.create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.bridge.close()
        self.directory.cleanup()

    def cookie(self, **extra):
        return {"Cookie": f"{COOKIE}={SESSION}", **extra}

    async def test_anonymous_portal_is_only_static_and_no_private_data(self):
        response = await self.client.get("/castori/index.html")
        self.assertEqual(response.status, 200)
        self.assertIn("La casa", await response.text())
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Referrer-Policy"], "no-referrer")
        response = await self.client.get("/api/account/session")
        self.assertEqual(await response.json(), {"portal": True, "authenticated": False})
        for route in ("state", "history?animal=mimosuga", "stories"):
            response = await self.client.get("/api/bridge/" + route)
            self.assertEqual(response.status, 401)

    async def test_cookie_binds_only_sandra_and_does_not_authenticate_internal_bridge(self):
        response = await self.client.get("/api/bridge/state", headers=self.cookie(**OWNER))
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["actor"], "sandra")
        for route in ("admin-state", "admin-events", "admin-invitation"):
            response = await self.client.get("/api/bridge/" + route, headers=self.cookie(**OWNER))
            self.assertEqual(response.status, 404)
        response = await self.client.get("/castori-web/state", headers=self.cookie())
        self.assertEqual(response.status, 401)
        response = await self.client.get("/api/bridge/state", headers=OWNER)
        self.assertEqual(response.status, 401)
        response = await self.client.get("/castori-web/state", headers=OWNER)
        self.assertEqual((await response.json())["actor"], "owner")

    async def test_forged_or_rebound_session_is_denied(self):
        for session in (None, {"actor": "owner", "chat_id": 22}, {"actor": "sandra", "chat_id": 33}):
            self.accounts.get_session.side_effect = None
            self.accounts.get_session.return_value = session
            response = await self.client.get("/api/bridge/state", headers=self.cookie())
            self.assertEqual(response.status, 401)

    async def test_post_requires_exact_origin_and_json_even_before_authentication(self):
        for route in ("/api/account/login", "/api/account/register", "/api/account/logout", "/api/bridge/message"):
            for origin in (None, "null", "https://evil.example", ORIGIN + "/", "http://casa.example"):
                headers = {"Origin": origin} if origin else {}
                response = await self.client.post(route, json={}, headers=headers)
                self.assertEqual(response.status, 403)
            response = await self.client.post(route, data="{}", headers={"Origin": ORIGIN})
            self.assertEqual(response.status, 415)
        self.accounts.login.assert_not_awaited()
        self.accounts.register.assert_not_awaited()

    async def test_duplicate_origins_and_forwarded_host_cannot_authorize_post(self):
        response = await self.client.post("/api/account/login", json={"username": "patita", "password": "a long password"},
            headers=[("Origin", ORIGIN), ("Origin", "https://evil.example")])
        self.assertEqual(response.status, 403)
        response = await self.client.post("/api/account/login", json={}, headers={
            "Origin": "https://evil.example", "X-Forwarded-Host": "evil.example", "X-Forwarded-Proto": "https"})
        self.assertEqual(response.status, 403)

    async def test_login_cookie_secure_behind_http_reverse_proxy_without_exposing_token(self):
        response = await self.client.post("/api/account/login", json={"username": "patita", "password": "a long password"},
            headers={"Origin": ORIGIN, "Host": "internal.worker", "X-Forwarded-Proto": "http"})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"authenticated": True, "username": "patita"})
        cookie = response.cookies[COOKIE]
        self.assertTrue(cookie["secure"])
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], "/")
        self.assertFalse(cookie["domain"])
        self.assertLessEqual(int(cookie["max-age"]), 604800)
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    async def test_registration_accepts_only_exact_body_and_never_accepts_role_or_chat_id(self):
        good = {"code": "invitation", "username": "patita", "password": "a long password"}
        for extra in ({"role": "owner"}, {"chat_id": 22}, {"email": "someone@example.com"}):
            response = await self.client.post("/api/account/register", json={**good, **extra}, headers={"Origin": ORIGIN})
            self.assertEqual(response.status, 400)
        self.accounts.register.assert_not_awaited()
        response = await self.client.post("/api/account/register", json=good, headers={"Origin": ORIGIN})
        self.assertEqual(response.status, 200)
        self.assertNotIn("token", await response.json())

    async def test_logout_revokes_session_and_clears_cookie(self):
        response = await self.client.post("/api/account/logout", json={}, headers=self.cookie(Origin=ORIGIN))
        self.assertEqual(response.status, 200)
        self.accounts.logout.assert_awaited_once_with(SESSION)
        self.assertEqual(response.cookies[COOKIE]["max-age"], "0")

    async def test_get_and_malformed_credentials_do_not_mutate_accounts(self):
        for route in ("login", "register", "logout"):
            response = await self.client.get("/api/account/" + route)
            self.assertEqual(response.status, 405)
        response = await self.client.post("/api/account/login", data="{", headers={"Origin": ORIGIN, "Content-Type": "application/json"})
        self.assertEqual(response.status, 400)
        response = await self.client.post("/api/account/login", json={"username": [], "password": "x"}, headers={"Origin": ORIGIN})
        self.assertEqual(response.status, 400)
        response = await self.client.post("/api/account/login", json={"username": "patita", "password": "x" * 25000}, headers={"Origin": ORIGIN})
        self.assertEqual(response.status, 413)
        self.accounts.login.assert_not_awaited()

    async def test_static_cannot_expose_runtime_files_or_path_traversal(self):
        for path in ("/castori/data.json", "/castori/.env", "/castori/.git/config", "/castori/%2e%2e/secret.html", "/api/not-found"):
            response = await self.client.get(path)
            self.assertIn(response.status, (401, 404))
            self.assertNotIn("must not", await response.text())

    async def test_only_internal_owner_can_manage_invitations(self):
        for headers, status in (({}, 401), ({**OWNER, "X-Castori-Actor": "sandra"}, 403)):
            response = await self.client.post("/castori-web/admin-invitation", json={"action": "create"}, headers=headers)
            self.assertEqual(response.status, status)
        response = await self.client.get("/castori-web/admin-invitation", headers=OWNER)
        self.assertNotIn("code", await response.json())
        response = await self.client.post("/castori-web/admin-invitation", json={"action": "create"}, headers=OWNER)
        result = await response.json()
        self.assertEqual(result["invite_url"], ORIGIN + "/castori/#invite/one-time-code")
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.bridge.admin_events, [], "Invitation secrets never enter the mirrored admin feed")

    def test_configuration_requires_explicit_https_origin(self):
        for value in ("http://casa.example", "https://x:y@casa.example", "https://casa.example/path", "https://casa.example?x=1"):
            with self.assertRaises(ValueError):
                canonical_origin(value)


if __name__ == "__main__":
    unittest.main()
