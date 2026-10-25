"""Durable, generic Web Push for Sandra's authenticated office devices.

All DATA_FILE transactions are synchronous on the application's single event
loop. Call enqueue within the same save as unread.record and the inbox event.
Delivery reserves a sequence before awaiting: outcomes left uncertain are not
replayed. This intentionally provides at-most-once attempts, not guaranteed
delivery. Endpoint capabilities and encryption keys never enter log messages.
"""

import asyncio
import base64
import copy
import hashlib
import importlib.util
import json
import logging
import math
import os
import re
import time
from urllib.parse import urlsplit

import unread_notifications as unread


logger = logging.getLogger("control-castora.web_push")
STORE_KEY = "web_push"
MAX_DEVICES = 16
MAX_EVENT_AGE = 24 * 60 * 60
MAX_DEBOUNCE_SECONDS = 10
SEND_TIMEOUT_SECONDS = 15
NETWORK_TIMEOUT = (4, 8)
PUSH_TTL = 60 * 60
TITLE = "Oficina Castori"
BODY = "Hay mensajes nuevos en Oficina Castori"
TAG = "castori-new-messages"
_EXACT_HOSTS = frozenset(("fcm.googleapis.com", "updates.push.services.mozilla.com"))
_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class WebPushError(RuntimeError):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def _positive(value):
    return type(value) is int and value > 0


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _decode_key(value, size=None):
    if not isinstance(value, str) or not 1 <= len(value) <= 2048:
        raise ValueError("Invalid key")
    if not re.fullmatch(r"[A-Za-z0-9_-]+={0,2}", value):
        raise ValueError("Invalid key")
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if size is not None and len(raw) != size:
        raise ValueError("Invalid key")
    return raw


def _encode_key(raw):
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def validate_endpoint(endpoint):
    """Accept only known browser push providers, never arbitrary destinations."""
    if (not isinstance(endpoint, str) or not 1 <= len(endpoint) <= 2048
            or not endpoint.isascii() or any(ord(char) <= 32 or ord(char) == 127 for char in endpoint)
            or "\\" in endpoint):
        raise WebPushError("invalid_subscription")
    try:
        address = urlsplit(endpoint)
        host = address.hostname or ""
        valid_host = host in _EXACT_HOSTS or host == "push.apple.com" or host.endswith(".push.apple.com")
        if (address.scheme != "https" or not valid_host or address.username is not None
                or address.password is not None or address.port is not None or address.fragment
                or address.netloc.lower() != host or not address.path.startswith("/")
                or not all(_DOMAIN_LABEL.fullmatch(label) for label in host.split("."))):
            raise ValueError("Invalid endpoint")
    except ValueError:
        raise WebPushError("invalid_subscription") from None
    return endpoint


def validate_subscription(subscription, now):
    if not isinstance(subscription, dict) or subscription.get("userVisibleOnly") is not True:
        raise WebPushError("invalid_subscription")
    if subscription.get("contentEncoding", "aes128gcm") != "aes128gcm":
        raise WebPushError("invalid_subscription")
    endpoint = validate_endpoint(subscription.get("endpoint"))
    keys = subscription.get("keys")
    try:
        if not isinstance(keys, dict):
            raise ValueError("Invalid keys")
        point, auth = _decode_key(keys.get("p256dh"), 65), _decode_key(keys.get("auth"), 16)
        if point[0] != 4:
            raise ValueError("Invalid point")
        from cryptography.hazmat.primitives.asymmetric import ec
        ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), point)
    except (ValueError, TypeError):
        raise WebPushError("invalid_subscription") from None
    expiration = subscription.get("expirationTime")
    if expiration is not None and (not _number(expiration) or expiration <= now * 1000):
        raise WebPushError("invalid_subscription")
    return {"endpoint": endpoint, "keys": {"p256dh": _encode_key(point), "auth": _encode_key(auth)},
            "expirationTime": expiration, "userVisibleOnly": True, "contentEncoding": "aes128gcm"}


def _device_id(endpoint):
    return hashlib.sha256(endpoint.encode("ascii")).hexdigest()[:16]


def _generation(subscription):
    return hashlib.sha256(json.dumps(subscription, sort_keys=True).encode("ascii")).hexdigest()[:24]


def _state(data):
    current = data.get(STORE_KEY)
    if not isinstance(current, dict) or current.get("version") != 1:
        current = data[STORE_KEY] = {"version": 1, "devices": {}, "pending": {}, "last_enqueued": {}}
    for key in ("devices", "pending", "last_enqueued"):
        if not isinstance(current.get(key), dict):
            current[key] = {}
    return current


def _baseline(data, chat_id):
    values = [data.get("web_bridge", {}).get("sequence", 0)]
    for animal in unread.ANIMALS:
        scopes = data.get(unread.STORE_KEY, {}).get("scopes", {}).get(f"{chat_id}:{animal}", {})
        values.extend(item.get("latest_id", 0) for item in scopes.values() if isinstance(item, dict))
    return max((value for value in values if _positive(value)), default=0)


def _unread_count(data, chat_id, items):
    # The ledger's summary also handles retained consultations and trimmed feeds.
    summary = getattr(unread, "summary", None)
    if summary is not None:
        count = summary(data, chat_id).get("total_messages", 0)
        if type(count) is int and count >= 0:
            return count
    return len(items)


def _payload(data, chat_id, items, eligible):
    animal = max(eligible, key=lambda item: item["event_id"])["animal"]
    fragment = "carta/vaca" if animal == "vaca" else f"chat/{animal}"
    return {"title": TITLE, "body": BODY, "tag": TAG,
            "unread_count": _unread_count(data, chat_id, items),
            "url": "/castori/#" + fragment}


def _recent_item(data, chat_id, item, now):
    scope = f"{chat_id}:{item['animal']}"
    sub = item.get("consultation_id") or unread.DEFAULT_SCOPE
    entry = data.get(unread.STORE_KEY, {}).get("scopes", {}).get(scope, {}).get(sub, {})
    stamp = entry.get("latest_at") if entry.get("latest_id") == item["event_id"] else None
    if stamp is None:
        stamp = next((event.get("timestamp") for event in data.get("web_bridge", {}).get("inboxes", {}).get(scope, [])
                      if event.get("id") == item["event_id"] and event.get("role") == "assistant"), None)
    return _number(stamp) and now - MAX_EVENT_AGE < stamp <= now + 60


class _PushTransport:
    """The encryption library's HTTP adapter: no redirects or environment proxy."""
    def __init__(self, endpoint, session=None):
        self.endpoint = validate_endpoint(endpoint)
        if session is None:
            import requests
            session = requests.Session()
        self.session = session
        self.session.trust_env = False

    def post(self, url, **kwargs):
        if url != self.endpoint:
            raise WebPushError("invalid_subscription")
        validate_endpoint(url)
        kwargs["allow_redirects"] = False
        kwargs["timeout"] = NETWORK_TIMEOUT
        kwargs["verify"] = True
        return self.session.post(url, **kwargs)

    def close(self):
        self.session.close()


def _post_webpush(subscription, payload, private_key, subject):
    from py_vapid import Vapid
    from pywebpush import webpush

    # Parse the key explicitly; never let a configured string be treated as a
    # filesystem path by the library. No key is generated at runtime.
    vapid = Vapid.from_string(private_key)
    transport = _PushTransport(subscription["endpoint"])
    try:
        response = webpush(
            subscription_info={"endpoint": subscription["endpoint"], "keys": subscription["keys"]},
            data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            vapid_private_key=vapid, vapid_claims={"sub": subject},
            content_encoding="aes128gcm", timeout=NETWORK_TIMEOUT, ttl=PUSH_TTL,
            headers={"Urgency": "normal", "Topic": TAG}, requests_session=transport, verbose=False,
        )
        return getattr(response, "status_code", None)
    finally:
        transport.close()


def _http_status(value):
    if type(value) is int:
        return value
    for obj in (value, getattr(value, "response", None)):
        for field in ("status_code", "status"):
            code = getattr(obj, field, None)
            if type(code) is int:
                return code
    return None


class WebPushService:
    def __init__(self, load_data, save_data, resolve_actor, *, send=None, clock=time.time,
                 debounce_seconds=2.5, private_key=None, public_key=None, subject=None):
        self.load, self.save, self.resolve_actor = load_data, save_data, resolve_actor
        self.clock, self.send = clock, send
        self.debounce_seconds = min(max(float(debounce_seconds), 0), MAX_DEBOUNCE_SECONDS)
        self.private_key = private_key if private_key is not None else os.getenv("WEB_PUSH_VAPID_PRIVATE_KEY", "")
        self.public_key = public_key if public_key is not None else os.getenv("WEB_PUSH_VAPID_PUBLIC_KEY", "")
        self.subject = subject if subject is not None else os.getenv("WEB_PUSH_SUBJECT", "https://oficinacastori.es")
        self.lock = asyncio.Lock()

    def _allowed(self, chat_id):
        try:
            sandra_id = self.resolve_actor("sandra")
            return (_positive(chat_id) and _positive(sandra_id) and chat_id == sandra_id
                    and chat_id != self.resolve_actor("owner"))
        except Exception:
            return False

    def _configured(self):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import ec
            private, public = _decode_key(self.private_key), _decode_key(self.public_key, 65)
            subject = urlsplit(self.subject)
            if len(private) == 32:
                key = ec.derive_private_key(int.from_bytes(private, "big"), ec.SECP256R1())
            else:
                key = serialization.load_der_private_key(private, password=None)
            valid_private = (isinstance(key, ec.EllipticCurvePrivateKey) and isinstance(key.curve, ec.SECP256R1)
                             and key.public_key().public_bytes(serialization.Encoding.X962,
                                  serialization.PublicFormat.UncompressedPoint) == public)
            valid_subject = (subject.scheme == "https" and bool(subject.hostname)
                             and subject.username is None and subject.password is None
                             and subject.port is None and not subject.fragment and not subject.query)
            return (valid_private and public[0] == 4 and valid_subject
                    and (self.send is not None or importlib.util.find_spec("pywebpush") is not None))
        except Exception:
            return False

    def _read(self):
        try:
            data = copy.deepcopy(self.load())
            if not isinstance(data, dict):
                raise ValueError("Invalid storage")
            return data
        except Exception:
            raise WebPushError("push_storage_unavailable", 503) from None

    def _save(self, data):
        try:
            self.save(data)
        except Exception:
            logger.warning("Web Push storage unavailable")
            raise WebPushError("push_storage_unavailable", 503) from None

    def status(self, chat_id):
        allowed = self._allowed(chat_id)
        available = allowed and self._configured()
        identities = []
        if allowed:
            devices = self._read().get(STORE_KEY, {}).get("devices", {}).get(str(chat_id), {})
            for identity, device in devices.items() if isinstance(devices, dict) else []:
                try:
                    validate_subscription(device.get("subscription"), self.clock())
                    if isinstance(identity, str) and re.fullmatch(r"[0-9a-f]{16}", identity):
                        identities.append(identity)
                except (WebPushError, AttributeError):
                    continue
        return {"available": bool(available), "public_key": self.public_key if available else None,
                "subscribed": bool(identities), "device_count": len(identities),
                "device_ids": identities, "max_devices": MAX_DEVICES}

    def subscribe(self, chat_id, subscription):
        if not self._allowed(chat_id):
            raise WebPushError("push_not_allowed", 403)
        if not self._configured():
            raise WebPushError("push_unavailable", 503)
        now = self.clock()
        subscription = validate_subscription(subscription, now)
        identity = _device_id(subscription["endpoint"])
        data = self._read()
        devices = _state(data)["devices"].setdefault(str(chat_id), {})
        existing = devices.get(identity)
        if existing and existing.get("subscription", {}).get("endpoint") != subscription["endpoint"]:
            raise WebPushError("invalid_subscription")
        if not existing and len(devices) >= MAX_DEVICES:
            raise WebPushError("push_device_limit", 409)
        devices[identity] = {**(existing or {}), "subscription": subscription,
                             "generation": _generation(subscription),
                             "baseline": existing.get("baseline", 0) if existing else _baseline(data, chat_id),
                             "last_reserved_seq": existing.get("last_reserved_seq", 0) if existing else 0,
                             "created_at": existing.get("created_at", now) if existing else now,
                             "updated_at": now}
        self._save(data)
        return {"subscribed": True, "device_id": identity}

    def unsubscribe(self, chat_id, endpoint):
        if not self._allowed(chat_id):
            raise WebPushError("push_not_allowed", 403)
        identity = _device_id(validate_endpoint(endpoint))
        data = self._read()
        devices = _state(data)["devices"].get(str(chat_id), {})
        existing = devices.get(identity)
        removed = bool(existing and existing.get("subscription", {}).get("endpoint") == endpoint)
        if removed:
            del devices[identity]
            self._save(data)
        return {"subscribed": False, "removed": removed}

    def enqueue(self, data, animal, chat_id, event):
        """Mutate the caller's event transaction; never load or save separately."""
        now = self.clock()
        if (not self._configured() or not self._allowed(chat_id) or animal not in unread.ANIMALS or not isinstance(event, dict)
                or event.get("role") != "assistant" or event.get("animal", animal) != animal
                or not _positive(event.get("id")) or not _number(event.get("timestamp"))
                or not now - MAX_EVENT_AGE < event["timestamp"] <= now + 60):
            return False
        state = _state(data)
        key = str(chat_id)
        if not state["devices"].get(key) or event["id"] <= state["last_enqueued"].get(key, 0):
            return False
        previous = state["pending"].get(key, {})
        first_at = previous.get("first_at", now)
        state["pending"][key] = {"event_id": event["id"], "animal": animal,
                                 "event_at": event["timestamp"], "first_at": first_at,
                                 "due_at": min(now + self.debounce_seconds, first_at + MAX_DEBOUNCE_SECONDS)}
        state["last_enqueued"][key] = event["id"]
        return True

    def _drop_pending(self, chat_id, event_id):
        data = self._read()
        pending = _state(data)["pending"]
        if pending.get(str(chat_id), {}).get("event_id") == event_id:
            del pending[str(chat_id)]
            self._save(data)

    async def _deliver(self, subscription, payload):
        if self.send is not None:
            return await self.send(copy.deepcopy(subscription), copy.deepcopy(payload))
        return await asyncio.to_thread(_post_webpush, subscription, payload, self.private_key, self.subject)

    def _skip_disabled_backlog(self):
        data = self._read()
        if STORE_KEY not in data:
            return
        state = _state(data)
        changed = bool(state["pending"])
        state["pending"].clear()
        for key, devices in state["devices"].items():
            try:
                chat_id = int(key)
            except (ValueError, TypeError):
                continue
            baseline = _baseline(data, chat_id)
            for device in devices.values():
                if baseline > device.get("baseline", 0):
                    device["baseline"] = baseline
                    changed = True
        if changed:
            self._save(data)

    async def tick(self):
        result = {"status": "ok", "sent": 0, "expired": 0, "uncertain": 0, "skipped": 0}
        if self.lock.locked():
            return {**result, "status": "busy"}
        if not self._configured():
            try:
                self._skip_disabled_backlog()
            except WebPushError:
                return {**result, "status": "storage_unavailable"}
            return {**result, "status": "unavailable"}
        async with self.lock:
            try:
                snapshot = self._read()
                work = list(snapshot.get(STORE_KEY, {}).get("pending", {}).items())
                for key, batch in work:
                    try:
                        chat_id = int(key)
                    except (ValueError, TypeError):
                        continue
                    event_id = batch.get("event_id")
                    if not _positive(event_id):
                        continue
                    if not self._allowed(chat_id) or batch.get("event_at", 0) <= self.clock() - MAX_EVENT_AGE:
                        self._drop_pending(chat_id, event_id)
                        result["skipped"] += 1
                        continue
                    if batch.get("due_at", 0) > self.clock():
                        continue
                    device_ids = list(snapshot.get(STORE_KEY, {}).get("devices", {}).get(key, {}))[:MAX_DEVICES]
                    for device_id in device_ids:
                        # Reload before every reservation. Reads, subscriptions,
                        # account bindings or new fragments may change on await.
                        current = self._read()
                        devices = _state(current)["devices"].get(key, {})
                        device = devices.get(device_id)
                        if not device or not self._allowed(chat_id):
                            continue
                        cutoff = max(device.get("baseline", 0), device.get("last_reserved_seq", 0))
                        items = unread.pending(current, chat_id)
                        eligible = [item for item in items if cutoff < item["event_id"] <= event_id
                                    and _recent_item(current, chat_id, item, self.clock())]
                        if not eligible:
                            continue
                        try:
                            subscription = validate_subscription(device.get("subscription"), self.clock())
                        except WebPushError:
                            del devices[device_id]
                            self._save(current)
                            result["expired"] += 1
                            continue
                        generation = device.get("generation")
                        payload = _payload(current, chat_id, items, eligible)
                        device["last_reserved_seq"] = event_id
                        device["last_attempt"] = {"event_id": event_id, "status": "sending", "at": self.clock()}
                        self._save(current)
                        status, http_status = "uncertain", None
                        try:
                            response = await asyncio.wait_for(self._deliver(subscription, payload), SEND_TIMEOUT_SECONDS)
                            http_status = _http_status(response)
                            status = "sent" if http_status is None or 200 <= http_status < 300 else "uncertain"
                        except asyncio.CancelledError:
                            raise
                        except Exception as exc:
                            # Exceptions may contain endpoint tokens or provider
                            # bodies; retain only the numeric HTTP status.
                            http_status = _http_status(exc)
                        latest = self._read()
                        latest_devices = _state(latest)["devices"].get(key, {})
                        latest_device = latest_devices.get(device_id)
                        if (latest_device and latest_device.get("generation") == generation
                                and latest_device.get("last_attempt", {}).get("event_id") == event_id):
                            if http_status in (404, 410):
                                del latest_devices[device_id]
                                status = "expired"
                            else:
                                latest_device["last_attempt"]["status"] = status
                            self._save(latest)
                        result[status] += 1
                    self._drop_pending(chat_id, event_id)
            except WebPushError:
                result["status"] = "storage_unavailable"
            return result
