"""Two-person invitation portal; database sessions decide the allowed role."""
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from aiohttp import web

from account_service import AccountError

COOKIE = "__Host-castori_session"
PUBLIC_GET = ("state", "events", "request", "history", "stories", "story", "consultations", "consultation")
PUBLIC_POST = ("message", "callback", "consultation-action", "consultation-message", "read")
ADMIN_GET = ("admin-state", "admin-events", "admin-invitation", "admin-owner-invitation", "admin-auth")
ADMIN_POST = ("admin-action", "admin-callback", "admin-invitation", "admin-owner-invitation", "admin-auth")
ASSET_EXTENSIONS = {".html", ".css", ".js", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".woff", ".woff2", ".ico"}


def canonical_origin(value):
    parsed = urlsplit(value)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("CASTORI_PORTAL_ORIGIN must be a bare HTTPS origin")
    return value.rstrip("/")


def failure(code, status=400):
    return web.json_response({"error": code}, status=status)


class Portal:
    def __init__(self, bridge, accounts, origin, root=None):
        self.bridge, self.accounts = bridge, accounts
        self.origin = canonical_origin(origin)
        self.root = Path(root or Path(__file__).parent / "portal_web").resolve()

    @staticmethod
    def handles(request):
        return request.path == "/" or request.path.startswith(("/castori/", "/api/"))

    @staticmethod
    def protect(response):
        response.headers.update({
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer", "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        })
        return response

    async def authenticate(self, request, handler):
        try:
            if request.method not in {"GET", "HEAD", "POST"}:
                return self.protect(failure("method_not_allowed", 405))
            if request.method == "POST":
                origins = request.headers.getall("Origin", [])
                if origins != [self.origin]:
                    return self.protect(failure("origin_not_allowed", 403))
                if request.content_type != "application/json":
                    return self.protect(failure("json_required", 415))
            if request.path.startswith("/api/bridge/"):
                route = request.path.removeprefix("/api/bridge/")
                if route not in PUBLIC_GET + PUBLIC_POST + ADMIN_GET + ADMIN_POST:
                    return self.protect(failure("not_found", 404))
                session = await self._session(request)
                if not session:
                    return self.protect(failure("sign_in_required", 401))
                # Only the DB session and current server mapping can bind this role.
                # Browser headers and JSON never participate in this decision.
                request["actor"], request["chat_id"] = session["actor"], session["chat_id"]
                request["portal_session"] = session
                request["portal_owner"] = session["actor"] == "owner"
                if route in ADMIN_GET + ADMIN_POST and not request["portal_owner"]:
                    return self.protect(failure("owner_required", 403))
                if route in PUBLIC_POST and request["portal_owner"]:
                    return self.protect(failure("read_only", 403))
            response = await handler(request)
        except AccountError as exc:
            response = failure(exc.code, exc.status)
        except web.HTTPException as exc:
            response = exc
        except Exception:
            # Never log credentials, request bodies or session cookies.
            response = failure("temporarily_unavailable", 503)
        return self.protect(response)

    @staticmethod
    def _session_token(request):
        # Parse every header before a cookie parser can discard duplicate names.
        # Ambiguous cookies must never choose which person's session to use.
        values = []
        for header in request.headers.getall("Cookie", []):
            for part in header.split(";"):
                name, _, value = part.strip().partition("=")
                if name.strip() == COOKIE:
                    values.append(value)
        return values[0] if len(values) == 1 else ""

    async def _session(self, request):
        if self.accounts is None:
            raise web.HTTPServiceUnavailable()
        raw = self._session_token(request)
        session = await self.accounts.get_session(raw) if raw else None
        if (not session or session.get("actor") not in ("sandra", "owner")
                or not isinstance(session.get("chat_id"), int) or isinstance(session.get("chat_id"), bool)
                or session["chat_id"] <= 0
                or session["chat_id"] != self.bridge.resolve_actor(session["actor"])
                or self.bridge.resolve_actor("sandra") == self.bridge.resolve_actor("owner")):
            return None
        return session

    async def session(self, request):
        session = await self._session(request)
        result = {"portal": True, "authenticated": bool(session)}
        if session:
            result["username"] = session["username"]
            result["actor"] = session["actor"]
        return web.json_response(result)

    @staticmethod
    async def body(request, fields):
        if request.query:
            raise web.HTTPBadRequest()
        try:
            value = await request.json()
        except (ValueError, UnicodeError):
            raise web.HTTPBadRequest()
        if (not isinstance(value, dict) or set(value) != set(fields)
                or any(not isinstance(value[key], str) for key in fields)):
            raise web.HTTPBadRequest()
        return value

    @staticmethod
    def signed_in(result):
        response = web.json_response({"authenticated": True, "username": result["username"], "actor": result["actor"]})
        expires = result["expires_at"]
        if isinstance(expires, str):
            expires = datetime.fromisoformat(expires.replace("Z", "+00:00"))
        age = max(0, min(604800, int((expires - datetime.now(timezone.utc)).total_seconds())))
        response.set_cookie(COOKIE, result["token"], max_age=age, secure=True,
                            httponly=True, samesite="Strict", path="/")
        return response

    async def register(self, request):
        data = await self.body(request, ("code", "username", "password"))
        if not self.accounts:
            return failure("temporarily_unavailable", 503)
        # Do not trust arbitrary forwarded client IPs. Railway's shared peer is
        # a conservative extra limiter; per-account limits remain authoritative.
        result = await self.accounts.register(**data, ip=request.remote or "unknown")
        return self.signed_in(result)

    async def login(self, request):
        data = await self.body(request, ("username", "password"))
        if not self.accounts:
            return failure("temporarily_unavailable", 503)
        result = await self.accounts.login(**data, ip=request.remote or "unknown")
        return self.signed_in(result)

    async def logout(self, request):
        await self.body(request, ())
        if not self.accounts:
            return failure("temporarily_unavailable", 503)
        raw = self._session_token(request)
        if raw:
            await self.accounts.logout(raw)
        response = web.json_response({"authenticated": False})
        response.del_cookie(COOKIE, secure=True, httponly=True, samesite="Strict", path="/")
        return response

    async def index(self, request):
        raise web.HTTPFound("/castori/index.html")

    async def asset(self, request):
        relative = request.match_info.get("file", "") or "index.html"
        requested = self.root / relative
        target = requested.resolve()
        if (not target.is_relative_to(self.root) or target.suffix.lower() not in ASSET_EXTENSIONS
                or not target.is_file() or any(part.startswith(".") for part in Path(relative).parts)
                or any(p.is_symlink() for p in [requested, *requested.parents] if p != self.root.parent)):
            raise web.HTTPNotFound()
        return web.FileResponse(target)

    def install(self, app):
        app.router.add_get("/", self.index)
        app.router.add_get("/castori/{file:.*}", self.asset)
        app.router.add_get("/api/account/session", self.session)
        app.router.add_post("/api/account/register", self.register)
        app.router.add_post("/api/account/login", self.login)
        app.router.add_post("/api/account/logout", self.logout)
        for name in PUBLIC_GET:
            handler = self.bridge._request_status if name == "request" else getattr(self.bridge, "_" + name.replace("-", "_"))
            app.router.add_get("/api/bridge/" + name, handler)
        for name in PUBLIC_POST:
            handler = self.bridge._mark_read if name == "read" else getattr(self.bridge, "_" + name.replace("-", "_"))
            app.router.add_post("/api/bridge/" + name, handler)
        for name in ADMIN_GET:
            app.router.add_get("/api/bridge/" + name, getattr(self.bridge, "_" + name.replace("-", "_")))
        for name in ADMIN_POST:
            app.router.add_post("/api/bridge/" + name, getattr(self.bridge, "_" + name.replace("-", "_")))
