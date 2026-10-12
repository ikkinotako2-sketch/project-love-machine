"""Auth-only candidate; existing OAuth provider reused, no posting adapter imported."""
import io
import json
import time
from urllib.parse import parse_qs
from plm.social_adapters.youtube.oauth import EnvironmentOAuthTokenProvider

IDENTITY = "provider-neutral-youtube-oauth-readiness-20261012-r1"
URL = "https://oauth2.googleapis.com/token"
LIMIT = 32768
TIMEOUT = 30
FIELDS = {"client_id", "client_secret", "refresh_token", "grant_type"}

REASONS = frozenset({
    "SECOND_REQUEST_FORBIDDEN_STOP", "REQUEST_POLICY_STOP", "REQUEST_BOUND_STOP",
    "FORM_POLICY_STOP", "HTTP_SHAPE_STOP", "OAUTH_HTTP_STOP", "RESPONSE_BOUND_STOP",
    "OAUTH_RESPONSE_SHAPE_STOP", "OAUTH_TOKEN_SHAPE_STOP", "OAUTH_EXPIRY_STOP",
    "OAUTH_TOKEN_TYPE_STOP", "OAUTH_TIMEOUT_STOP", "OAUTH_CREDENTIAL_MISSING_OR_BOUND_STOP",
    "OAUTH_CREDENTIAL_SHAPE_STOP", "OAUTH_TRANSPORT_OR_PROVIDER_UNKNOWN_STOP",
})

def exact_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs)

class Stop(Exception):
    pass

def need(ok, reason):
    if not ok:
        raise Stop(reason)

class BundleProvider(EnvironmentOAuthTokenProvider):
    def __init__(self, bundle, opener):
        super().__init__(env_name="NO_AMBIENT_SECRET", opener=opener)
        self.bundle = bundle
    def _load_bundle(self):
        return self.bundle

class BoundedOpener:
    """No urllib redirect machinery, retries or second request capability."""
    def __init__(self, transport):
        self.transport = transport
        self.calls = 0
        self.http_status = None
    def __call__(self, request, timeout):
        need(self.calls == 0, "SECOND_REQUEST_FORBIDDEN_STOP")
        need(request.full_url == URL and request.get_method() == "POST", "REQUEST_POLICY_STOP")
        need(timeout == TIMEOUT and isinstance(request.data, bytes) and len(request.data) <= LIMIT, "REQUEST_BOUND_STOP")
        form = parse_qs(request.data.decode("utf-8"), strict_parsing=True)
        need(set(form) == FIELDS and all(len(v) == 1 and v[0] for v in form.values()), "FORM_POLICY_STOP")
        need(form["grant_type"] == ["refresh_token"], "FORM_POLICY_STOP")
        self.calls += 1
        status, raw = self.transport(request.data)
        need(type(status) is int and 100 <= status <= 599, "HTTP_SHAPE_STOP")
        self.http_status = status
        need(status == 200, "OAUTH_HTTP_STOP")
        need(isinstance(raw, bytes) and len(raw) <= LIMIT, "RESPONSE_BOUND_STOP")
        try:
            payload = exact_json(raw)
        except Exception:
            raise Stop("OAUTH_RESPONSE_SHAPE_STOP") from None
        need(isinstance(payload, dict), "OAUTH_RESPONSE_SHAPE_STOP")
        token = payload.get("access_token")
        expiry = payload.get("expires_in")
        need(isinstance(token, str) and bool(token) and len(token) <= 16384 and not any(ord(c) < 32 for c in token), "OAUTH_TOKEN_SHAPE_STOP")
        need(type(expiry) is int and 0 < expiry <= 86400, "OAUTH_EXPIRY_STOP")
        token_type = payload.get("token_type")
        need(isinstance(token_type, str) and token_type.lower() == "bearer", "OAUTH_TOKEN_TYPE_STOP")
        # Only the validated fields reach the unchanged provider. Nothing retained.
        clean = json.dumps({"access_token": token, "expires_in": expiry}).encode()
        del raw, payload, token
        return io.BytesIO(clean)

def authorized_https_transport(form):
    import http.client
    deadline = time.monotonic() + TIMEOUT
    conn = http.client.HTTPSConnection("oauth2.googleapis.com", timeout=TIMEOUT)
    try:
        conn.connect()
        remaining = deadline - time.monotonic()
        need(remaining > 0, "OAUTH_TIMEOUT_STOP")
        conn.sock.settimeout(remaining)
        conn.request("POST", "/token", body=form, headers={"Content-Type": "application/x-www-form-urlencoded"})
        remaining = deadline - time.monotonic()
        need(remaining > 0, "OAUTH_TIMEOUT_STOP")
        conn.sock.settimeout(remaining)
        response = conn.getresponse()
        status = response.status
        # Never read rejected remote error bodies; no exception carries remote text.
        if status != 200:
            return status, b""
        chunks = []
        size = 0
        while True:
            remaining = deadline - time.monotonic()
            need(remaining > 0, "OAUTH_TIMEOUT_STOP")
            sock = conn.sock or getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
            need(sock is not None, "OAUTH_TRANSPORT_OR_PROVIDER_UNKNOWN_STOP")
            sock.settimeout(remaining)
            chunk = response.read1(min(4096, LIMIT + 1 - size))
            if not chunk:
                return status, b"".join(chunks)
            chunks.append(chunk)
            size += len(chunk)
            need(size <= LIMIT, "RESPONSE_BOUND_STOP")
    finally:
        conn.close()

def verify(raw_bundle, transport):
    out = {"identity": IDENTITY, "classification": "OAUTH_VERIFY_BLOCKED", "reason_code": None,
           "http_status": None, "refresh_posts": 0, "retry": 0, "redirect": 0, "fallback": 0,
           "raw_retention": 0, "uploads": 0, "publishes": 0, "secret_exposure": 0}
    opener = BoundedOpener(transport)
    provider = None
    try:
        need(isinstance(raw_bundle, str) and bool(raw_bundle) and len(raw_bundle.encode()) <= LIMIT, "OAUTH_CREDENTIAL_MISSING_OR_BOUND_STOP")
        try:
            bundle = exact_json(raw_bundle)
        except Exception:
            raise Stop("OAUTH_CREDENTIAL_SHAPE_STOP") from None
        need(isinstance(bundle, dict) and all(isinstance(bundle.get(k), str) and bundle[k] and len(bundle[k]) <= 8192 for k in FIELDS - {"grant_type"}), "OAUTH_CREDENTIAL_SHAPE_STOP")
        provider = BundleProvider({k: bundle[k] for k in FIELDS - {"grant_type"}}, opener)
        del bundle, raw_bundle
        token = provider.get_access_token()
        need(bool(token), "OAUTH_TOKEN_SHAPE_STOP")
        del token
        out["classification"] = "OAUTH_REFRESH_AUTH_CONFIRMED_STOP_BEFORE_YOUTUBE"
    except Stop as exc:
        reason = exc.args[0] if len(exc.args) == 1 else None
        out["reason_code"] = reason if isinstance(reason, str) and reason in REASONS else "OAUTH_TRANSPORT_OR_PROVIDER_UNKNOWN_STOP"
    except Exception:
        out["reason_code"] = "OAUTH_TRANSPORT_OR_PROVIDER_UNKNOWN_STOP"
    finally:
        if provider:
            provider._token = None
            provider.bundle.clear()
        out["refresh_posts"] = opener.calls
        out["http_status"] = opener.http_status
    return out

def main():
    # CLI remains parked; remote transport cannot run without future gate artifact.
    print(json.dumps({"identity": IDENTITY, "classification": "OFFLINE_PREPARATION_PARKED",
                      "reason_code": "EXECUTION_APPROVAL_AND_SECRET_SELECTOR_REQUIRED", "refresh_posts": 0}))

if __name__ == "__main__":
    main()
