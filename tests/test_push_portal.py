"""Cookie-bound Web Push configuration and public unread metadata."""
import json
import unittest
from unittest.mock import Mock

import test_portal as fixtures
import unread_notifications as unread


class PushPortalTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await fixtures.PortalTests.asyncSetUp(self)
        self.push = Mock()
        self.push.status.return_value = {"available": True, "public_key": "public-test-key", "subscribed": False, "device_count": 0, "device_ids": []}
        self.push.subscribe.return_value = {"subscribed": True, "device_id": "opaque-device-id"}
        self.push.unsubscribe.return_value = {"subscribed": False, "removed": True}
        self.bridge.push_service = self.push
        unread.initialize(self.data)

    async def asyncTearDown(self):
        await fixtures.PortalTests.asyncTearDown(self)

    def cookie(self, **extra):
        return fixtures.PortalTests.cookie(self, **extra)

    def owner_cookie(self, **extra):
        return fixtures.PortalTests.owner_cookie(self, **extra)

    async def test_permission_config_requires_a_real_portal_session(self):
        anonymous = await self.client.get("/api/bridge/push-status")
        self.assertEqual(anonymous.status, 401)
        owner = await self.client.get("/api/bridge/push-status", headers=self.owner_cookie())
        self.assertEqual(owner.status, 200)
        self.assertFalse((await owner.json())["available"])
        self.push.status.assert_not_called()
        sandra = await self.client.get("/api/bridge/push-status", headers=self.cookie(**fixtures.OWNER))
        self.assertEqual(sandra.status, 200)
        self.assertEqual((await sandra.json())["public_key"], "public-test-key")
        self.push.status.assert_called_once_with(11)
        # A proxy bearer alone cannot enroll a device through the legacy bridge.
        proxy = await self.client.get("/castori-web/push-status", headers=fixtures.OWNER)
        self.assertEqual(proxy.status, 404)

    async def test_subscription_is_bound_to_cookie_identity_not_supplied_headers(self):
        value = {"endpoint": "https://web.push.apple.com/example", "keys": {"auth": "test", "p256dh": "test"}, "userVisibleOnly": True}
        result = await self.client.post("/api/bridge/push-subscribe", json={"subscription": value}, headers=self.cookie(Origin=fixtures.ORIGIN, **fixtures.OWNER))
        self.assertEqual(result.status, 200)
        self.push.subscribe.assert_called_once_with(11, value)
        removed = await self.client.post("/api/bridge/push-unsubscribe", json={"endpoint": value["endpoint"]}, headers=self.cookie(Origin=fixtures.ORIGIN))
        self.assertEqual(removed.status, 200)
        self.push.unsubscribe.assert_called_once_with(11, value["endpoint"])

    async def test_owner_cross_origin_and_extra_fields_never_enroll(self):
        for headers, body, expected in (
            (self.owner_cookie(Origin=fixtures.ORIGIN), {"subscription": {}}, 403),
            (self.cookie(Origin="https://elsewhere.example"), {"subscription": {}}, 403),
            (self.cookie(Origin=fixtures.ORIGIN), {"subscription": {}, "actor": "sandra"}, 400),
        ):
            with self.subTest(expected=expected):
                response = await self.client.post("/api/bridge/push-subscribe", headers=headers, json=body)
                self.assertEqual(response.status, expected)
        self.push.subscribe.assert_not_called()

    async def test_unread_state_and_event_metadata_never_consume_sandras_messages(self):
        first = self.bridge.record("mimosuga", 11, "PRIVATE-EXAMPLE-ONE")
        self.bridge.record("mimosuga", 11, "PRIVATE-EXAMPLE-TWO")
        self.bridge.record("castori", 11, "PRIVATE-EXAMPLE-THREE")
        self.bridge.record("mimosuga", 22, "OWNER-ONLY")
        response = await self.client.get("/api/bridge/state", headers=self.owner_cookie())
        public = (await response.json())["unread"]
        self.assertEqual((public["total_messages"], public["total_chats"]), (3, 2))
        self.assertEqual(public["animals"]["mimosuga"]["count"], 2)
        self.assertNotIn("PRIVATE-EXAMPLE", json.dumps(public))
        self.assertEqual(len(unread.pending(self.data, 11)), 2)
        denied = await self.client.post("/api/bridge/read", headers=self.owner_cookie(Origin=fixtures.ORIGIN), json={"animal": "mimosuga", "event_id": first["id"], "consultation_id": None})
        self.assertEqual(denied.status, 403)
        self.assertEqual(unread.summary(self.data, 11)["total_messages"], 3)
        ack = await self.client.post("/api/bridge/read", headers=self.cookie(Origin=fixtures.ORIGIN), json={"animal": "mimosuga", "event_id": first["id"], "consultation_id": None})
        self.assertEqual(ack.status, 200)
        self.assertEqual((await ack.json())["unread"]["total_messages"], 2)
        events = await self.client.get("/api/bridge/events?animal=mimosuga", headers=self.cookie())
        self.assertEqual((await events.json())["unread"]["animals"]["mimosuga"]["read_id"], first["id"])

    async def test_pwa_files_have_manifest_and_worker_policies_without_opening_json(self):
        (self.root / "manifest.webmanifest").write_text('{"display":"standalone"}')
        (self.root / "service-worker.js").write_text("self.addEventListener('push', () => {});")
        manifest = await self.client.get("/castori/manifest.webmanifest")
        self.assertEqual(manifest.status, 200)
        self.assertIn("application/manifest+json", manifest.headers["Content-Type"])
        self.assertIn("manifest-src 'self'", manifest.headers["Content-Security-Policy"])
        worker = await self.client.get("/castori/service-worker.js")
        self.assertEqual(worker.status, 200)
        self.assertEqual(worker.headers["Service-Worker-Allowed"], "/castori/")
        self.assertIn("no-store", worker.headers["Cache-Control"])
        self.assertIn("worker-src 'self'", worker.headers["Content-Security-Policy"])
        private = await self.client.get("/castori/data.json")
        self.assertEqual(private.status, 404)
