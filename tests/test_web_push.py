"""Offline Web Push contracts, persistence and races; no real endpoints called."""

import asyncio
import base64
import copy
import json
import re
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import unread_notifications as unread
from web_push import (
    BODY, MAX_DEVICES, MAX_EVENT_AGE, MAX_TEST_RECEIPTS, NETWORK_TIMEOUT, STORE_KEY, TEST_BODY, TEST_TAG, WebPushError,
    WebPushService, _PushTransport, _post_webpush, validate_endpoint, validate_subscription,
)


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


# The public P-256 generator point and scalar 1 are public test fixtures, never
# deployment keys. They let validation exercise actual curve checks offline.
PUBLIC = b64(bytes.fromhex(
    "04" "6b17d1f2e12c4247f8bce6e563a440f277037d812deb33a0f4a13945d898c296"
    "4fe342e2fe1a7f9b8ee7eb4a7c0f9e162bce33576b315ececbb6406837bf51f5"))
PRIVATE = b64((1).to_bytes(32, "big"))


def subscription(name="one", **values):
    return {"endpoint": "https://web.push.apple.com/Q/" + name,
            "keys": {"p256dh": PUBLIC, "auth": b64(bytes(range(16)))},
            "expirationTime": None, "userVisibleOnly": True, **values}


class SubscriptionValidationTests(unittest.TestCase):
    def test_recognized_browser_push_hosts_only(self):
        for endpoint in ("https://web.push.apple.com/Q/capability", "https://a1.push.apple.com/Q/capability",
                         "https://fcm.googleapis.com/fcm/send/capability",
                         "https://updates.push.services.mozilla.com/wpush/v2/capability"):
            self.assertEqual(validate_endpoint(endpoint), endpoint)

    def test_ssrf_credentials_ports_fragments_and_ambiguous_urls_are_rejected(self):
        urls = ("http://web.push.apple.com/Q/x", "https://127.0.0.1/x", "https://[::1]/x",
                "https://localhost/x", "https://169.254.169.254/latest/meta-data",
                "https://web.push.apple.com.evil.test/x", "https://evilpush.apple.com/x",
                "https://push.apple.com@evil.test/x", "https://secret@web.push.apple.com/x",
                "https://web.push.apple.com:443/x", "https://web.push.apple.com:8080/x",
                "https://web.push.apple.com/x#token", "https://web.push.apple.com./x",
                "https://web.push.apple.com\\@127.0.0.1/x", "https://web.push.apple.com/\nx",
                "https://web.push.apple.com/x y", "https://web.push.apple.com", "https://é.push.apple.com/x")
        for endpoint in urls:
            with self.subTest(endpoint=endpoint), self.assertRaises(WebPushError) as error:
                validate_endpoint(endpoint)
            self.assertEqual(error.exception.code, "invalid_subscription")
            self.assertNotIn(endpoint, str(error.exception))

    def test_visibility_encoding_and_real_p256_keys_are_checked(self):
        now = time.time()
        self.assertEqual(validate_subscription(subscription(), now)["contentEncoding"], "aes128gcm")
        invalid = [None, {}, subscription(userVisibleOnly=False), subscription(userVisibleOnly="true"),
                   subscription(contentEncoding="aesgcm"), subscription(expirationTime=now * 1000 - 1),
                   subscription(expirationTime=float("inf")), subscription(expirationTime=10 ** 1000),
                   subscription(keys={"p256dh": PUBLIC, "auth": b64(b"short")}),
                   subscription(keys={"p256dh": b64(b"\x04" + b"\x00" * 64), "auth": b64(bytes(16))}),
                   subscription(keys={"p256dh": PUBLIC, "auth": "!!!"})]
        no_visibility = subscription()
        del no_visibility["userVisibleOnly"]
        invalid.append(no_visibility)
        for item in invalid:
            with self.subTest(item_type=type(item).__name__), self.assertRaises(WebPushError):
                validate_subscription(item, now)

    def test_unknown_fields_are_not_stored(self):
        item = subscription(message="PRIVATE BODY", headers={"Authorization": "PRIVATE TOKEN"})
        cleaned = validate_subscription(item, time.time())
        self.assertEqual(set(cleaned), {"endpoint", "keys", "expirationTime", "userVisibleOnly", "contentEncoding"})

    def test_network_adapter_forces_strict_tls_no_redirect_and_timeout(self):
        session = MagicMock()
        session.post.return_value = SimpleNamespace(status_code=302, headers={"Location": "http://127.0.0.1/"})
        endpoint = subscription()["endpoint"]
        transport = _PushTransport(endpoint, session=session)
        response = transport.post(endpoint, data=b"encrypted", allow_redirects=True, verify=False, timeout=None)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(session.trust_env)
        kwargs = session.post.call_args.kwargs
        self.assertFalse(kwargs["allow_redirects"])
        self.assertTrue(kwargs["verify"])
        self.assertEqual(kwargs["timeout"], NETWORK_TIMEOUT)
        session.post.assert_called_once()
        with self.assertRaises(WebPushError):
            transport.post("http://127.0.0.1/", data=b"encrypted")
        transport.close()
        session.close.assert_called_once()

    def test_real_library_encrypts_and_signs_der_keys_without_any_network(self):
        import http_ece
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec, utils

        server_key = ec.generate_private_key(ec.SECP256R1())
        client_key = ec.generate_private_key(ec.SECP256R1())
        private = b64(server_key.private_bytes(serialization.Encoding.DER,
                       serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        public = b64(server_key.public_key().public_bytes(serialization.Encoding.X962,
                      serialization.PublicFormat.UncompressedPoint))
        client_public = b64(client_key.public_key().public_bytes(serialization.Encoding.X962,
                             serialization.PublicFormat.UncompressedPoint))
        auth = bytes(range(16))
        sub = subscription(keys={"p256dh": client_public, "auth": b64(auth)})
        payload = {"title": "Oficina Castori", "body": BODY, "unread_count": 2,
                   "url": "/castori/#chat/mimosuga"}
        session = MagicMock()
        session.post.return_value = SimpleNamespace(status_code=201, text="", headers={})
        with patch("requests.Session", return_value=session):
            result = _post_webpush(sub, payload, private, "https://oficinacastori.es")
        self.assertEqual(result, 201)
        session.post.assert_called_once()
        request = session.post.call_args
        self.assertEqual(request.args[0], sub["endpoint"])
        encrypted = request.kwargs["data"]
        self.assertIsInstance(encrypted, bytes)
        self.assertNotIn(BODY.encode(), encrypted)
        clear = http_ece.decrypt(encrypted, private_key=client_key, auth_secret=auth, version="aes128gcm")
        self.assertEqual(json.loads(clear), payload)
        headers = request.kwargs["headers"]
        self.assertEqual(headers["content-encoding"], "aes128gcm")
        self.assertFalse(request.kwargs["allow_redirects"])
        self.assertTrue(request.kwargs["verify"])
        self.assertEqual(request.kwargs["timeout"], NETWORK_TIMEOUT)
        authorization = headers["Authorization"]
        self.assertTrue(authorization.startswith("vapid "))
        token = re.search(r"\bt=([^,\s]+)", authorization).group(1)
        encoded_header, encoded_claims, encoded_signature = token.split(".")
        decode = lambda value: base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        claims = json.loads(decode(encoded_claims))
        self.assertEqual(claims["aud"], "https://web.push.apple.com")
        self.assertEqual(claims["sub"], "https://oficinacastori.es")
        self.assertGreater(claims["exp"], time.time())
        self.assertIn("k=" + public, authorization)
        signature = decode(encoded_signature)
        der_signature = utils.encode_dss_signature(int.from_bytes(signature[:32], "big"),
                                                   int.from_bytes(signature[32:], "big"))
        server_key.public_key().verify(der_signature, (encoded_header + "." + encoded_claims).encode(),
                                       ec.ECDSA(hashes.SHA256()))
        session.close.assert_called_once()


class WebPushServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        environment = patch.dict("os.environ", {"WEB_PUSH_TEST_REQUEST_ID": "", "WEB_PUSH_TEST_EXPIRES_AT": ""})
        environment.start()
        self.addCleanup(environment.stop)
        self.now = time.time()
        self.data = {"web_bridge": {"sequence": 0, "inboxes": {}}}
        unread.initialize(self.data)
        self.actors = {"sandra": 11, "owner": 22}
        self.sender = AsyncMock(return_value=201)
        self.service = self.make_service()

    def save(self, data):
        self.data = copy.deepcopy(data)

    def make_service(self, **options):
        return WebPushService(lambda: copy.deepcopy(self.data), self.save, self.actors.get,
                              send=self.sender, clock=lambda: self.now,
                              private_key=options.pop("private_key", PRIVATE), public_key=PUBLIC,
                              subject="https://oficinacastori.es", **options)

    def register(self, name="one", **values):
        return self.service.subscribe(11, subscription(name, **values))["device_id"]

    def put(self, identity, animal="mimosuga", chat_id=11, **values):
        data = copy.deepcopy(self.data)
        item = {"id": identity, "role": "assistant", "animal": animal,
                "timestamp": self.now, "text": "PRIVATE MESSAGE BODY", **values}
        data["web_bridge"]["sequence"] = max(identity, data["web_bridge"]["sequence"])
        data["web_bridge"]["inboxes"].setdefault(f"{chat_id}:{animal}", []).append(item)
        unread.record(data, chat_id, animal, item)
        queued = self.service.enqueue(data, animal, chat_id, item)
        self.save(data)
        return queued

    async def flush(self):
        self.now += 3
        return await self.service.tick()

    def device(self, identity):
        return self.data[STORE_KEY]["devices"]["11"][identity]

    async def test_actor_only_sandra_and_never_owner_or_alias(self):
        for chat_id in (22, 33, True, None, "11"):
            self.assertFalse(self.service.status(chat_id)["available"])
            self.assertEqual(self.service.status(chat_id)["device_ids"], [])
            with self.assertRaises(WebPushError) as error:
                self.service.subscribe(chat_id, subscription())
            self.assertEqual(error.exception.status, 403)
        self.actors["owner"] = 11
        self.assertFalse(self.service.status(11)["available"])
        self.assertFalse(self.put(1))
        await self.flush()
        self.sender.assert_not_awaited()
        self.actors["sandra"] = True
        self.actors["owner"] = 22
        self.assertFalse(self.service.status(1)["available"])

    async def test_registration_baselines_old_messages_and_exposes_only_hashes(self):
        self.put(1)
        identity = self.register()
        self.assertEqual(self.device(identity)["baseline"], 1)
        self.assertEqual(len(identity), 16)
        status = self.service.status(11)
        self.assertEqual(status["device_ids"], [identity])
        self.assertEqual(status["public_key"], PUBLIC)
        self.assertNotIn(subscription()["endpoint"], json.dumps(status))
        self.assertNotIn(subscription()["keys"]["auth"], json.dumps(status))
        self.put(1)
        await self.flush()
        self.sender.assert_not_awaited()
        self.put(2)
        self.assertEqual((await self.flush())["sent"], 1)

    async def test_same_endpoint_is_idempotent_and_limit_does_not_evict_devices(self):
        identity = self.register()
        self.assertEqual(self.register(), identity)
        for index in range(1, MAX_DEVICES):
            self.register(str(index))
        self.assertEqual(self.service.status(11)["device_count"], MAX_DEVICES)
        with self.assertRaises(WebPushError) as error:
            self.register("overflow")
        self.assertEqual((error.exception.code, error.exception.status), ("push_device_limit", 409))
        self.assertIn(identity, self.service.status(11)["device_ids"])

    async def test_unsubscribe_is_scoped_and_does_not_expose_endpoint(self):
        self.register()
        with self.assertRaises(WebPushError):
            self.service.unsubscribe(22, subscription()["endpoint"])
        self.assertTrue(self.service.unsubscribe(11, subscription()["endpoint"])["removed"])
        self.assertFalse(self.service.unsubscribe(11, subscription()["endpoint"])["removed"])
        self.assertFalse(self.service.status(11)["subscribed"])

    async def test_new_fragments_are_debounced_and_payload_never_contains_message(self):
        self.register()
        self.assertTrue(self.put(1))
        self.now += 1
        self.assertTrue(self.put(2))
        await self.service.tick()
        self.sender.assert_not_awaited()
        result = await self.flush()
        self.assertEqual(result["sent"], 1)
        payload = self.sender.call_args.args[1]
        self.assertEqual(payload["body"], BODY)
        self.assertEqual(payload["url"], "/castori/#chat/mimosuga")
        self.assertEqual(payload["unread_count"], 2)
        self.assertNotIn("PRIVATE MESSAGE BODY", json.dumps(payload))
        self.assertNotIn("PRIVATE MESSAGE BODY", json.dumps(self.data[STORE_KEY]))
        self.assertFalse(self.put(2))
        await self.flush()
        self.assertEqual(self.sender.await_count, 1)

    async def test_busy_fragment_stream_has_a_maximum_debounce(self):
        self.register()
        self.put(1)
        for identity in range(2, 12):
            self.now += 1
            self.put(identity)
        self.assertLessEqual(self.data[STORE_KEY]["pending"]["11"]["due_at"], self.now)
        await self.service.tick()
        self.sender.assert_awaited_once()

    async def test_owner_read_does_not_cancel_sandra_but_her_read_does(self):
        self.register()
        self.put(1)
        self.put(2, chat_id=22)
        unread.acknowledge(self.data, 22, "mimosuga", 2)
        await self.flush()
        self.sender.assert_awaited_once()
        self.put(3)
        unread.acknowledge(self.data, 11, "mimosuga", 3)
        await self.flush()
        self.assertEqual(self.sender.await_count, 1)
        self.assertEqual(self.data[STORE_KEY]["pending"], {})

    async def test_user_messages_old_events_and_bad_animal_do_not_enqueue(self):
        self.register()
        self.assertFalse(self.put(1, role="user"))
        self.assertFalse(self.put(2, timestamp=self.now - MAX_EVENT_AGE - 1))
        self.assertFalse(self.put(3, timestamp=self.now + 100))
        self.assertFalse(self.service.enqueue(self.data, "../owner", 11, {"id": 4, "role": "assistant", "timestamp": self.now}))
        await self.flush()
        self.sender.assert_not_awaited()

    async def test_old_durable_queue_expires_without_delivery(self):
        self.register()
        self.put(1)
        self.now += MAX_EVENT_AGE + 1
        await self.service.tick()
        self.sender.assert_not_awaited()
        self.assertFalse(self.data[STORE_KEY]["pending"])

    async def test_fresh_read_event_cannot_wake_an_unrelated_old_unread_item(self):
        self.register()
        self.put(1, animal="castori", timestamp=self.now - MAX_EVENT_AGE - 1)
        self.put(2, animal="mimosuga")
        unread.acknowledge(self.data, 11, "mimosuga", 2)
        await self.flush()
        self.sender.assert_not_awaited()
        self.assertFalse(self.data[STORE_KEY]["pending"])

    async def test_reservation_is_durable_before_send_and_survives_restart(self):
        identity = self.register()
        self.put(1)

        async def check_reserved(sub, payload):
            self.assertEqual(self.device(identity)["last_reserved_seq"], 1)
            self.assertEqual(self.device(identity)["last_attempt"]["status"], "sending")
            return 201

        self.sender.side_effect = check_reserved
        await self.flush()
        # Replay the persisted queue to simulate a crash before queue cleanup.
        self.data[STORE_KEY]["pending"]["11"] = {"event_id": 1, "event_at": self.now, "due_at": self.now}
        await self.make_service().tick()
        self.assertEqual(self.sender.await_count, 1)

    async def test_two_devices_and_two_animals_receive_one_generic_batch_each(self):
        self.register("one")
        self.register("two")
        self.put(1, animal="castori")
        self.put(2, animal="vaca")
        result = await self.flush()
        self.assertEqual(result["sent"], 2)
        self.assertEqual(self.sender.await_count, 2)
        for call in self.sender.call_args_list:
            self.assertEqual(call.args[1]["url"], "/castori/#carta/vaca")

    async def test_new_device_registered_during_debounce_does_not_get_older_event(self):
        self.register("one")
        self.put(1)
        self.register("two")
        await self.flush()
        self.sender.assert_awaited_once()
        self.assertEqual(self.sender.call_args.args[0]["endpoint"], subscription("one")["endpoint"])

    async def test_send_timeout_is_uncertain_and_not_retried(self):
        identity = self.register()
        self.put(1)

        async def slow(sub, payload):
            await asyncio.Event().wait()

        self.sender.side_effect = slow
        with patch("web_push.SEND_TIMEOUT_SECONDS", .01):
            result = await self.flush()
        self.assertEqual(result["uncertain"], 1)
        self.assertEqual(self.device(identity)["last_attempt"]["status"], "uncertain")
        await self.make_service().tick()
        self.assertEqual(self.sender.await_count, 1)

    async def test_expired_provider_response_removes_device_but_other_failure_does_not(self):
        for status in (404, 410, 403, 429, 500, 302):
            with self.subTest(status=status):
                self.data[STORE_KEY] = {"version": 1, "devices": {}, "pending": {}, "last_enqueued": {}}
                identity = self.register()
                self.put(self.data["web_bridge"]["sequence"] + 1)
                self.sender.return_value = status
                self.sender.side_effect = None
                result = await self.flush()
                present = identity in self.service.status(11)["device_ids"]
                self.assertEqual(present, status not in (404, 410))
                self.assertEqual(result["expired" if status in (404, 410) else "uncertain"], 1)

    async def test_exception_status_is_read_without_logging_capability(self):
        self.register()
        self.put(1)
        error = RuntimeError("SECRET_ENDPOINT_CAPABILITY")
        error.response = SimpleNamespace(status_code=410)
        self.sender.side_effect = error
        with patch("web_push.logger") as log:
            result = await self.flush()
        self.assertEqual(result["expired"], 1)
        self.assertNotIn("SECRET_ENDPOINT_CAPABILITY", str(log.mock_calls))

    async def test_new_event_and_read_during_send_are_not_overwritten(self):
        identity = self.register()
        self.put(1)

        async def concurrent_activity(sub, payload):
            unread.acknowledge(self.data, 11, "mimosuga", 1)
            self.put(2)
            self.data["other_writer"] = "preserve me"
            return 201

        self.sender.side_effect = concurrent_activity
        await self.flush()
        self.assertEqual(self.data["other_writer"], "preserve me")
        self.assertEqual(self.data[STORE_KEY]["pending"]["11"]["event_id"], 2)
        self.assertEqual(self.data[unread.STORE_KEY]["scopes"]["11:mimosuga"]["_"]["read_id"], 1)
        self.assertEqual(self.device(identity)["last_reserved_seq"], 1)
        self.sender.side_effect = None
        await self.flush()
        self.assertEqual(self.sender.await_count, 2)

    async def test_410_after_renewal_cannot_delete_new_subscription(self):
        identity = self.register()
        self.put(1)

        async def renew(sub, payload):
            changed = subscription(keys={"p256dh": PUBLIC, "auth": b64(bytes(reversed(range(16))))})
            self.service.subscribe(11, changed)
            return 410

        self.sender.side_effect = renew
        await self.flush()
        self.assertIn(identity, self.service.status(11)["device_ids"])
        self.assertEqual(self.device(identity)["subscription"]["keys"]["auth"], b64(bytes(reversed(range(16)))))

    async def test_unsubscribe_during_send_is_never_restored(self):
        self.register()
        self.put(1)

        async def remove(sub, payload):
            self.service.unsubscribe(11, sub["endpoint"])
            return 201

        self.sender.side_effect = remove
        await self.flush()
        self.assertFalse(self.service.status(11)["subscribed"])

    async def test_actor_change_during_send_stops_remaining_devices(self):
        self.register("one")
        self.register("two")
        self.put(1)

        async def actor_changes(sub, payload):
            self.actors["sandra"] = 33
            return 201

        self.sender.side_effect = actor_changes
        await self.flush()
        self.sender.assert_awaited_once()

    async def test_save_failure_before_reservation_prevents_send(self):
        self.register()
        self.put(1)
        with patch.object(self.service, "save", side_effect=OSError("SECRET_PATH")), patch("web_push.logger") as log:
            result = await self.flush()
        self.sender.assert_not_awaited()
        self.assertEqual(result["status"], "storage_unavailable")
        self.assertNotIn("SECRET_PATH", str(log.mock_calls))

    async def test_cancellation_preserves_reservation_and_restart_does_not_resend(self):
        identity = self.register()
        self.put(1)
        self.now += 3
        started = asyncio.Event()

        async def stalled(sub, payload):
            started.set()
            await asyncio.Event().wait()

        self.sender.side_effect = stalled
        task = asyncio.create_task(self.service.tick())
        await started.wait()
        self.assertEqual((await self.service.tick())["status"], "busy")
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.device(identity)["last_attempt"]["status"], "sending")
        self.sender.side_effect = None
        await self.make_service().tick()
        self.assertEqual(self.sender.await_count, 1)

    async def test_disabled_keys_baseline_backlog_without_generating_keys(self):
        identity = self.register()
        self.put(1)
        disabled = self.make_service(private_key="")
        self.assertFalse(disabled.status(11)["available"])
        with self.assertRaises(WebPushError) as error:
            disabled.subscribe(11, subscription("other"))
        self.assertEqual(error.exception.status, 503)
        self.now += 3
        self.assertEqual((await disabled.tick())["status"], "unavailable")
        self.assertEqual(self.device(identity)["baseline"], 1)
        await self.service.tick()
        self.sender.assert_not_awaited()
        self.put(2)
        await self.flush()
        self.sender.assert_awaited_once()

    async def test_vapid_mismatched_or_invalid_keys_never_report_available(self):
        for key in ("", "private.pem", b64(bytes(32)), b64((2).to_bytes(32, "big"))):
            service = self.make_service(private_key=key)
            self.assertFalse(service.status(11)["available"])
            self.assertIsNone(service.status(11)["public_key"])


class WebPushTestRequestTests(unittest.IsolatedAsyncioTestCase):
    make_service = WebPushServiceTests.make_service
    save = WebPushServiceTests.save
    register = WebPushServiceTests.register
    put = WebPushServiceTests.put
    device = WebPushServiceTests.device

    async def asyncSetUp(self):
        await WebPushServiceTests.asyncSetUp(self)
        self.request_id = "test-request-one"
        self.expires_at = self.now + 86400
        self.service = self.restart()

    def restart(self):
        return self.make_service(test_request_id=self.request_id, test_expires_at=self.expires_at)

    def receipt(self):
        return self.data[STORE_KEY]["test_receipts"][self.request_id]

    async def test_waits_for_registration_then_reserves_one_attempt_and_survives_restart(self):
        before = copy.deepcopy(self.data)
        with patch("web_push.logger") as log:
            self.assertEqual((await self.service.tick())["test_status"], "waiting")
            self.assertEqual((await self.service.tick())["test_status"], "waiting")
            self.service = self.restart()
            self.assertEqual((await self.service.tick())["test_status"], "waiting")
            self.assertEqual(sum(call.args == ("Web Push test waiting for a registered device",)
                                 for call in log.info.call_args_list), 1)
        self.sender.assert_not_awaited()
        self.assertEqual(self.data["web_bridge"], before["web_bridge"])
        self.assertEqual(self.data[unread.STORE_KEY], before[unread.STORE_KEY])
        identity = self.register()

        async def check_reserved(sub, payload):
            self.assertEqual(self.receipt()["status"], "sending")
            self.assertEqual(self.receipt()["device_id"], identity)
            self.assertEqual(self.device(identity)["last_reserved_seq"], 0)
            self.assertEqual(payload, {"kind": "test", "title": "Oficina Castori", "body": TEST_BODY,
                                       "tag": TEST_TAG, "url": "/castori/#conversations"})
            self.assertNotIn("unread_count", payload)
            return 201

        self.sender.side_effect = check_reserved
        self.assertEqual((await self.service.tick())["test_status"], "sent")
        self.assertEqual((await self.restart().tick())["test_status"], "sent")
        self.sender.assert_awaited_once()
        self.assertEqual(self.data[unread.STORE_KEY], before[unread.STORE_KEY])
        self.assertEqual(self.data[STORE_KEY]["pending"], {})

    async def test_only_latest_current_device_gets_test_and_expired_device_is_skipped(self):
        self.register("older")
        self.now += 1
        self.register("latest")
        self.now += 1
        expired = self.register("expires", expirationTime=(self.now + 1) * 1000)
        self.now += 2
        await self.service.tick()
        self.sender.assert_awaited_once()
        self.assertEqual(self.sender.call_args.args[0]["endpoint"], subscription("latest")["endpoint"])
        self.assertNotIn(expired, self.service.status(11)["device_ids"])

    async def test_refreshed_device_is_the_latest_registration(self):
        self.register("one")
        self.now += 1
        self.register("two")
        self.now += 1
        self.register("one")
        await self.service.tick()
        self.sender.assert_awaited_once()
        self.assertEqual(self.sender.call_args.args[0]["endpoint"], subscription("one")["endpoint"])

    async def test_no_valid_environment_order_means_no_test(self):
        self.register()
        invalid = [("", self.expires_at), ("short", self.expires_at), ("contains space", self.expires_at),
                   ("not-ascii-ñ", self.expires_at), ("x" * 65, self.expires_at),
                   (self.request_id, ""), (self.request_id, "nan"), (self.request_id, "inf"),
                   (self.request_id, True), (self.request_id, -1), (self.request_id, "not a timestamp")]
        for request_id, expiry in invalid:
            service = self.make_service(test_request_id=request_id, test_expires_at=expiry)
            result = await service.tick()
            self.assertNotIn("test_status", result)
        self.assertNotIn("test_status", await self.make_service().tick())
        self.sender.assert_not_awaited()
        self.assertNotIn("test_receipts", self.data[STORE_KEY])

    async def test_environment_uuid_order_is_supported_without_modifying_vapid_configuration(self):
        self.register()
        request_id = "7b32d164-6d70-431c-b388-4b82e9229a76"
        with patch.dict("os.environ", {"WEB_PUSH_TEST_REQUEST_ID": request_id,
                                      "WEB_PUSH_TEST_EXPIRES_AT": str(self.expires_at)}):
            service = self.make_service()
            self.assertEqual((await service.tick())["test_status"], "sent")
            self.assertEqual(service.private_key, PRIVATE)
            self.assertEqual(service.public_key, PUBLIC)
        self.assertEqual(self.data[STORE_KEY]["test_receipts"][request_id]["status"], "sent")

    async def test_disabled_delivery_configuration_cannot_send_an_authorized_test(self):
        self.register()
        service = self.make_service(private_key="", test_request_id=self.request_id,
                                    test_expires_at=self.expires_at)
        self.assertEqual((await service.tick())["status"], "unavailable")
        self.sender.assert_not_awaited()
        self.assertNotIn("test_receipts", self.data[STORE_KEY])

    async def test_expiry_before_device_registration_never_sends_or_rearms_same_request(self):
        await self.service.tick()
        self.now = self.expires_at + 1
        self.register()
        with patch("web_push.logger") as log:
            self.assertEqual((await self.service.tick())["test_status"], "expired")
            self.expires_at = self.now + 86400
            self.assertEqual((await self.restart().tick())["test_status"], "expired")
            self.assertEqual(sum(call.args == ("Web Push test expired",) for call in log.info.call_args_list), 1)
        self.sender.assert_not_awaited()

    async def test_canonical_missing_invalid_or_owner_identity_never_receives_test(self):
        self.register()
        for actor in (None, True, 0, -1, "11", 22, 33):
            self.actors["sandra"] = actor
            result = await self.service.tick()
            self.assertIn(result["test_status"], ("unavailable", "waiting"))
        self.sender.assert_not_awaited()
        self.assertNotIn("attempted_at", self.receipt())

    async def test_ambiguous_failures_and_timeout_are_reserved_once_and_never_retried(self):
        async def stalled(sub, payload):
            await asyncio.Event().wait()

        for index, failure in enumerate((None, 403, 500, RuntimeError("PRIVATE_ENDPOINT_TOKEN"), stalled)):
            self.request_id = f"test-failure-{index}"
            self.service = self.restart()
            self.register()
            self.sender.reset_mock()
            self.sender.side_effect = failure if isinstance(failure, Exception) or callable(failure) else None
            self.sender.return_value = failure if type(failure) is int else None
            with patch("web_push.SEND_TIMEOUT_SECONDS", .01), patch("web_push.logger") as log:
                self.assertEqual((await self.service.tick())["test_status"], "uncertain")
                self.sender.side_effect = None
                self.assertEqual((await self.restart().tick())["test_status"], "uncertain")
            self.sender.assert_awaited_once()
            self.assertNotIn("PRIVATE_ENDPOINT_TOKEN", str(log.mock_calls))
            self.assertNotIn(subscription()["endpoint"], str(log.mock_calls))
            self.assertNotIn(TEST_BODY, str(log.mock_calls))

    async def test_cancelled_attempt_survives_restart_without_another_delivery(self):
        self.register()
        started = asyncio.Event()

        async def stalled(sub, payload):
            started.set()
            await asyncio.Event().wait()

        self.sender.side_effect = stalled
        task = asyncio.create_task(self.service.tick())
        await started.wait()
        self.assertEqual(self.receipt()["status"], "sending")
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.sender.side_effect = None
        self.assertEqual((await self.restart().tick())["test_status"], "uncertain")
        self.sender.assert_awaited_once()

    async def test_provider_expiry_prunes_device_but_does_not_retry_another_device(self):
        self.register("older")
        self.now += 1
        latest = self.register("latest")
        self.sender.return_value = 410
        self.assertEqual((await self.service.tick())["test_status"], "expired")
        self.assertNotIn(latest, self.service.status(11)["device_ids"])
        await self.restart().tick()
        self.sender.assert_awaited_once()

    async def test_expiry_response_cannot_delete_a_renewed_subscription(self):
        identity = self.register()

        async def renew(sub, payload):
            self.service.subscribe(11, subscription(keys={"p256dh": PUBLIC, "auth": b64(bytes(reversed(range(16))))}))
            return 410

        self.sender.side_effect = renew
        await self.service.tick()
        self.assertIn(identity, self.service.status(11)["device_ids"])
        self.assertEqual(self.receipt()["status"], "expired")

    async def test_test_receipts_are_bounded_without_changing_pending_normal_delivery(self):
        identity = self.register()
        self.put(1)
        before_pending = copy.deepcopy(self.data[STORE_KEY]["pending"])
        before_unread = copy.deepcopy(self.data[unread.STORE_KEY])
        self.data[STORE_KEY]["extra_config"] = "preserved"
        self.data[STORE_KEY]["test_receipts"] = {
            f"previous-{number}": {"status": "sent", "created_at": self.now - 100 + number}
            for number in range(MAX_TEST_RECEIPTS)
        }
        await self.service.tick()
        self.assertEqual(len(self.data[STORE_KEY]["test_receipts"]), MAX_TEST_RECEIPTS)
        self.assertIn(self.request_id, self.data[STORE_KEY]["test_receipts"])
        self.assertNotIn("previous-0", self.data[STORE_KEY]["test_receipts"])
        self.assertEqual(self.data[STORE_KEY]["pending"], before_pending)
        self.assertEqual(self.data[unread.STORE_KEY], before_unread)
        self.assertEqual(self.data[STORE_KEY]["extra_config"], "preserved")
        self.assertEqual(self.device(identity)["last_reserved_seq"], 0)
        self.sender.assert_awaited_once()

    async def test_concurrent_reads_and_new_messages_during_test_delivery_are_preserved(self):
        self.register()
        self.put(1)

        async def update_other_state(sub, payload):
            unread.acknowledge(self.data, 11, "mimosuga", 1)
            self.put(2)
            self.data["other_writer"] = "preserved"
            return 201

        self.sender.side_effect = update_other_state
        await self.service.tick()
        self.assertEqual(self.data[STORE_KEY]["pending"]["11"]["event_id"], 2)
        self.assertEqual(self.data[unread.STORE_KEY]["scopes"]["11:mimosuga"]["_"]["read_id"], 1)
        self.assertEqual(self.data["other_writer"], "preserved")
        self.sender.assert_awaited_once()

    async def test_storage_failure_before_reservation_blocks_send_and_after_send_cannot_repeat(self):
        self.register()
        with patch.object(self.service, "save", side_effect=OSError("private path")):
            self.assertEqual((await self.service.tick())["status"], "storage_unavailable")
        self.sender.assert_not_awaited()
        original_save, writes = self.service.save, 0

        def fail_after_reserving(data):
            nonlocal writes
            writes += 1
            if writes == 2:
                raise OSError("private path")
            original_save(data)

        with patch.object(self.service, "save", side_effect=fail_after_reserving):
            self.assertEqual((await self.service.tick())["status"], "storage_unavailable")
        self.assertEqual((await self.restart().tick())["test_status"], "uncertain")
        self.sender.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
