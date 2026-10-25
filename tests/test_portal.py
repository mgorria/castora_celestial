import copy
import json
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
OWNER = {"Authorization": "Bearer " + TOKEN, "X-Castori-Actor": "owner", "X-Castori-Owner-Id": "owner-test"}
SESSION = "session-for-test"
OWNER_SESSION = "owner-session-for-test"


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
        self.accounts.get_session.side_effect = lambda raw: {
            SESSION: {"actor": "sandra", "chat_id": 11, "username": "patita", "expires_at": "2099-01-01T00:00:00+00:00"},
            OWNER_SESSION: {"actor": "owner", "chat_id": 22, "username": "miguel", "expires_at": "2099-01-01T00:00:00+00:00"}
        }.get(raw)
        self.accounts.invitation_status.return_value = {"has_account": False, "active": False, "expires_at": None, "reset": False}
        self.accounts.create_invitation.return_value = {"code": "one-time-code", "expires_at": "2026-10-23T00:00:00+00:00", "reset": False}
        self.accounts.register.return_value = self.accounts.login.return_value = {
            "token": SESSION, "username": "patita", "actor": "sandra", "expires_at": datetime.now(timezone.utc) + timedelta(days=7)}
        self.accounts.desk_status.return_value = {"configured": True, "unlocked": False,
                                                  "expires_at": None, "reauthenticate": True}
        async def unlock(raw, password, ip=None):
            result = {"configured": True, "unlocked": True,
                      "expires_at": "2099-01-01T00:00:00+00:00", "reauthenticate": True}
            self.accounts.desk_status.return_value = result
            return result
        async def lock(raw):
            result = {"configured": True, "unlocked": False, "expires_at": None, "reauthenticate": True}
            self.accounts.desk_status.return_value = result
            return result
        self.accounts.unlock_desk.side_effect = unlock
        self.accounts.lock_desk.side_effect = lock
        self.data = {}
        self.access = AsyncMock()
        self.access.status.return_value = {"configured": True, "unlocked": True, "expires_at": "2099-01-01T00:00:00+00:00"}
        self.bridge = WebBridge(lambda: copy.deepcopy(self.data), lambda data: setattr(self, "data", data),
                                lambda: {}, lambda role: {"owner": 22, "sandra": 11}.get(role), token=TOKEN,
                                account_service=self.accounts, portal_origin=ORIGIN, portal_root=self.root,
                                admin_access=self.access, get_admin_app=lambda: object(),
                                admin_state_provider=lambda: {"animal_count": 5})
        self.client = TestClient(TestServer(self.bridge.create_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        await self.bridge.close()
        self.directory.cleanup()

    def cookie(self, **extra):
        return {"Cookie": f"{COOKIE}={SESSION}", **extra}

    def owner_cookie(self, **extra):
        return {"Cookie": f"{COOKIE}={OWNER_SESSION}", **extra}

    async def test_anonymous_portal_is_only_static_and_no_private_data(self):
        response = await self.client.get("/castori/index.html")
        self.assertEqual(response.status, 200)
        self.assertIn("La casa", await response.text())
        self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
        response = await self.client.get("/api/account/session")
        self.assertEqual(await response.json(), {"portal": True, "authenticated": False})
        for route in ("state", "history?animal=mimosuga", "stories", "consultations", "consultation?id=abc12345"):
            response = await self.client.get("/api/bridge/" + route)
            self.assertEqual(response.status, 401)

    async def test_sandra_cookie_cannot_use_owner_headers_or_authenticate_internal_bridge(self):
        response = await self.client.get("/api/bridge/state", headers=self.cookie(**OWNER))
        self.assertEqual(response.status, 200)
        self.assertEqual((await response.json())["actor"], "sandra")
        for route in ("admin-state", "admin-events", "admin-invitation", "admin-owner-invitation", "admin-auth"):
            response = await self.client.get("/api/bridge/" + route, headers=self.cookie(**OWNER))
            self.assertEqual(response.status, 403)
        response = await self.client.get("/castori-web/state", headers=self.cookie())
        self.assertEqual(response.status, 401)
        response = await self.client.get("/api/bridge/state", headers=OWNER)
        self.assertEqual(response.status, 401)
        response = await self.client.get("/castori-web/state", headers=OWNER)
        self.assertEqual((await response.json())["actor"], "owner")

    async def test_forged_or_rebound_session_is_denied(self):
        for session in (None, {"actor": "owner", "chat_id": 11}, {"actor": "sandra", "chat_id": 22},
                        {"actor": "sandra", "chat_id": 33}, {"actor": "visitor", "chat_id": 22}):
            self.accounts.get_session.side_effect = None
            self.accounts.get_session.return_value = session
            response = await self.client.get("/api/bridge/state", headers=self.cookie())
            self.assertEqual(response.status, 401)

    async def test_duplicate_session_cookies_never_select_a_person_or_grant_access(self):
        cases = [
            [("Cookie", f"{COOKIE}={SESSION}; {COOKIE}={OWNER_SESSION}")],
            [("Cookie", f"{COOKIE}={OWNER_SESSION}; {COOKIE}={SESSION}")],
            [("Cookie", f"{COOKIE}={OWNER_SESSION}; {COOKIE}={OWNER_SESSION}")],
            [("Cookie", f"{COOKIE}={SESSION}"), ("Cookie", f"{COOKIE}={OWNER_SESSION}")],
            [("Cookie", f"{COOKIE}=; {COOKIE}={OWNER_SESSION}")],
        ]
        for headers in cases:
            with self.subTest(headers=headers):
                response = await self.client.get("/api/account/session", headers=headers)
                self.assertEqual(await response.json(), {"portal": True, "authenticated": False})
                for route in ("state", "admin-state", "admin-auth"):
                    response = await self.client.get("/api/bridge/" + route, headers=headers)
                    self.assertEqual(response.status, 401)
                response = await self.client.post("/api/bridge/admin-owner-invitation",
                    json={"action": "create"}, headers=[*headers, ("Origin", ORIGIN)])
                self.assertEqual(response.status, 401)
        self.accounts.get_session.assert_not_awaited()
        self.accounts.create_invitation.assert_not_awaited()
        self.access.status.assert_not_awaited()

    async def test_single_session_cookie_still_works_with_unrelated_cookies(self):
        response = await self.client.get("/api/account/session", headers=[
            ("Cookie", "unrelated=first"), ("Cookie", f"{COOKIE}={SESSION}; other=second")])
        self.assertEqual((await response.json())["actor"], "sandra")
        self.accounts.get_session.assert_awaited_once_with(SESSION)

    async def test_post_requires_exact_origin_and_json_even_before_authentication(self):
        for route in ("/api/account/login", "/api/account/register", "/api/account/logout", "/api/bridge/message",
                      "/api/bridge/consultation-action", "/api/bridge/consultation-message"):
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

    async def test_origin_rejection_logs_only_categories_without_request_secrets(self):
        secret_origin = "https://untrusted.example/private-origin-secret"
        base_headers = [("Cookie", f"{COOKIE}={SESSION}"), ("Authorization", "Bearer credential-secret")]
        cases = (([], "missing"), ([("Origin", "null")], "null"),
                 ([("Origin", secret_origin)], "mismatch"),
                 ([("Origin", ORIGIN), ("Origin", secret_origin)], "duplicate"),
                 ([("Origin", ORIGIN), ("Origin", ORIGIN)], "duplicate"))
        for origins, kind in cases:
            with self.subTest(kind=kind), self.assertLogs("control-castora.portal", level="WARNING") as captured:
                response = await self.client.post("/api/bridge/consultation-action?token=query-secret",
                    headers=[*base_headers, *origins], json={"password": "body-secret"})
            self.assertEqual(response.status, 403)
            self.assertEqual(await response.json(), {"error": "origin_not_allowed"})
            self.assertEqual(response.headers["Referrer-Policy"], "same-origin")
            self.assertEqual([json.loads(record.getMessage()) for record in captured.records], [{
                "event": "portal_request_rejected", "route": "/api/bridge/consultation-action",
                "error": "origin_not_allowed", "origin_kind": kind}])
            for secret in (secret_origin, ORIGIN, SESSION, "credential-secret", "query-secret", "body-secret"):
                self.assertNotIn(secret, " ".join(captured.output))
        self.accounts.get_session.assert_not_awaited()

    async def test_rejection_diagnostics_ignore_unknown_or_static_paths(self):
        with self.assertNoLogs("control-castora.portal", level="WARNING"):
            for path in ("/api/bridge/private-path-secret", "/api/account/private-path-secret", "/castori/index.html"):
                response = await self.client.post(path, json={"password": "body-secret"})
                self.assertEqual(response.status, 403)

    async def test_owner_rejection_diagnostic_has_no_cookie_body_or_query(self):
        with self.assertLogs("control-castora.portal", level="WARNING") as captured:
            response = await self.client.post("/api/bridge/push-subscribe?token=query-secret",
                headers=self.owner_cookie(Origin=ORIGIN), json={"subscription": "body-secret"})
        self.assertEqual(response.status, 403)
        self.assertEqual(await response.json(), {"error": "read_only"})
        self.assertEqual([json.loads(record.getMessage()) for record in captured.records], [{
            "event": "portal_request_rejected", "route": "/api/bridge/push-subscribe", "error": "read_only"}])
        for secret in (OWNER_SESSION, ORIGIN, "query-secret", "body-secret"):
            self.assertNotIn(secret, " ".join(captured.output))

    async def test_login_cookie_secure_behind_http_reverse_proxy_without_exposing_token(self):
        response = await self.client.post("/api/account/login", json={"username": "patita", "password": "a long password"},
            headers={"Origin": ORIGIN, "Host": "internal.worker", "X-Forwarded-Proto": "http"})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"authenticated": True, "username": "patita", "actor": "sandra"})
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

    async def test_logout_clears_ambiguous_cookie_without_choosing_an_account_to_revoke(self):
        response = await self.client.post("/api/account/logout", json={}, headers={
            "Cookie": f"{COOKIE}={SESSION}; {COOKIE}={OWNER_SESSION}", "Origin": ORIGIN})
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"authenticated": False})
        self.assertEqual(response.cookies[COOKIE]["max-age"], "0")
        self.accounts.logout.assert_not_awaited()

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

    async def test_owner_cookie_requires_same_account_password_again_before_despacho(self):
        response = await self.client.get("/api/account/session", headers=self.owner_cookie())
        self.assertEqual(await response.json(), {"portal": True, "authenticated": True,
                                                "username": "miguel", "actor": "owner"})
        response = await self.client.get("/api/bridge/admin-state", headers=self.owner_cookie())
        self.assertEqual(response.status, 423)
        response = await self.client.get("/api/bridge/admin-auth", headers=self.owner_cookie())
        self.assertEqual(response.status, 200)
        self.assertEqual(await response.json(), {"configured": True, "unlocked": False,
                                                "expires_at": None, "reauthenticate": True})
        response = await self.client.post("/api/bridge/admin-auth", headers=self.owner_cookie(Origin=ORIGIN),
                                         json={"action": "unlock", "password": "x"})
        self.assertEqual(response.status, 200)
        self.assertNotIn("session_token", await response.json())
        self.accounts.unlock_desk.assert_awaited_once_with(OWNER_SESSION, "x", ip="127.0.0.1")
        self.assertEqual((await self.client.get("/api/bridge/admin-state", headers=self.owner_cookie())).status, 200)
        response = await self.client.post("/api/bridge/admin-auth", headers=self.owner_cookie(Origin=ORIGIN), json={"action": "lock"})
        self.assertEqual(response.status, 200)
        self.accounts.lock_desk.assert_awaited_once_with(OWNER_SESSION)
        self.assertEqual((await self.client.get("/api/bridge/admin-state", headers=self.owner_cookie())).status, 423)
        self.assertTrue((await (await self.client.get("/api/account/session", headers=self.owner_cookie())).json())["authenticated"])
        self.accounts.login.assert_not_awaited()
        self.accounts.logout.assert_not_awaited()
        self.access.status.assert_not_awaited()
        response = await self.client.get("/castori-web/admin-state", headers=self.owner_cookie())
        self.assertEqual(response.status, 401, "Portal cookies never authenticate the internal transport")

    async def test_every_portal_admin_route_and_admin_receipt_requires_elevation(self):
        self.data["web_bridge"] = {"sequence": 0, "inboxes": {}, "requests": {
            "22:adminreceipt": {"status": "processed", "admin": True}}}
        for route in ("admin-state", "admin-events", "admin-invitation", "admin-owner-invitation", "request?request_id=adminreceipt"):
            response = await self.client.get("/api/bridge/" + route, headers=self.owner_cookie(**OWNER))
            self.assertEqual(response.status, 423)
        for route in ("admin-action", "admin-callback", "admin-invitation", "admin-owner-invitation"):
            response = await self.client.post("/api/bridge/" + route, json={}, headers=self.owner_cookie(Origin=ORIGIN, **OWNER))
            self.assertEqual(response.status, 423)
        self.accounts.create_invitation.assert_not_awaited()
        self.assertEqual(self.bridge.admin_events, [])

    async def test_portal_reauth_rejects_injected_fields_and_keeps_exact_origin(self):
        for body in ({"action": "setup", "password": "x"}, {"action": "unlock", "password": "x", "actor": "owner"},
                     {"action": "lock", "password": "x"}, {"action": "unlock"}):
            response = await self.client.post("/api/bridge/admin-auth", headers=self.owner_cookie(Origin=ORIGIN), json=body)
            self.assertEqual(response.status, 400)
        response = await self.client.post("/api/bridge/admin-auth", headers=self.owner_cookie(Origin="https://other.example"),
                                         json={"action": "unlock", "password": "x"})
        self.assertEqual(response.status, 403)
        self.accounts.unlock_desk.assert_not_awaited()

    async def test_owner_normal_view_cannot_send_or_mutate_sandra_state(self):
        for route in ("message", "callback", "consultation-action", "consultation-message"):
            response = await self.client.post("/api/bridge/" + route, json={},
                                             headers=self.owner_cookie(Origin=ORIGIN))
            self.assertEqual(response.status, 403)
            self.assertEqual((await response.json())["error"], "read_only")
        self.assertEqual(self.bridge.admin_events, [])

    async def test_sandra_cannot_post_to_any_despacho_endpoint(self):
        for route in ("admin-action", "admin-callback", "admin-invitation", "admin-owner-invitation", "admin-auth"):
            response = await self.client.post("/api/bridge/" + route, json={"action": "unlock", "password": "x"},
                                             headers=self.cookie(Origin=ORIGIN, **OWNER))
            self.assertEqual(response.status, 403)
            self.assertEqual((await response.json())["error"], "owner_required")
        self.accounts.create_invitation.assert_not_awaited()
        self.access.unlock.assert_not_awaited()
        self.assertEqual(self.bridge.admin_events, [])

    async def test_owner_admin_writes_still_require_exact_origin_and_do_not_accept_roles(self):
        for route in ("admin-action", "admin-invitation", "admin-owner-invitation"):
            response = await self.client.post("/api/bridge/" + route, json={},
                                             headers=self.owner_cookie(Origin="https://other.example"))
            self.assertEqual(response.status, 403)
        response = await self.client.get("/api/bridge/unknown-admin", headers=self.owner_cookie())
        self.assertEqual(response.status, 404)

    def test_configuration_requires_explicit_https_origin(self):
        for value in ("http://casa.example", "https://x:y@casa.example", "https://casa.example/path", "https://casa.example?x=1"):
            with self.assertRaises(ValueError):
                canonical_origin(value)


if __name__ == "__main__":
    unittest.main()
