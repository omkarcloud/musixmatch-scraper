"""Musixmatch transport: plain curl_cffi through rotating residential exits,
with a patchright-minted AWS WAF token as the last-resort fallback.

Two upstream surfaces on www.musixmatch.com, both validated 2026-09-19:

  * API    https://www.musixmatch.com/ws/1.1/<method>?app_id=community-app-v1.0
           &format=json&<params>&signature=<sig>&signature_protocol=sha256
    The site's own "community" API (the classic Musixmatch REST methods:
    track.search, track.get, tracks.get, track.lyrics.get, artist.get,
    album.get, chart.tracks.get, ...). Anonymous, no usertoken. Every URL is
    signed: sig = base64(HMAC-SHA256(CLIENT_KEY, <url without signature> +
    YYYYMMDD in UTC)). CLIENT_KEY ships in the site's `_app-<hash>.js`
    bundle as a reversed base64 string; the known value is the default and
    an HTTP 401 (what a stale key gets) re-reads it from the live bundle.
    Response envelope: {"message": {"header": {"status_code", "available",
    "hint"}, "body": ...}} — the HTTP status is 200 even for an API-level
    404/400, which lives in header.status_code.
    Must be sent with `accept: application/json` (a navigation-style accept
    gets a Varnish 503).

  * PAGES  https://www.musixmatch.com/lyrics/<artist>/<track>, /artist/...,
           /creator/..., /discover, /lyrics/.../translation/<language>
    Next.js pages whose data is server-rendered into __NEXT_DATA__
    (props.pageProps.data.<section> = {"data": ...} or {"error":
    "__COM_RESPONSE_404__"}). Used only for what the API does not expose
    anonymously: credits with roles, the AI "lens" (meaning / moods /
    themes), community contributions, crowd translations, songwriter
    profiles, the discover lists.

Not obtainable anonymously (so not offered): synced / word-synced lyrics
(track.subtitle.get, track.richsync.get answer 403 "not enabled on this
plan"), related artists (always 400), macro.search / matcher.track.get
(403 at the WAF). apic-desktop.musixmatch.com hands out an all-zeros token
and then serves DECOY data — never use that host.

AWS WAF: a per-IP rate rule (~100 requests / 5 min, then HTTP 202 with the
`awsWafCookieDomainList` interstitial, or 405 for the CAPTCHA action) and
some exits are refused outright (403). So each worker thread holds one
sticky residential proxy exit (config.musixmatch_proxy) that is rotated after
config.MUSIXMATCH_REQUESTS_PER_EXIT requests or on any block. If rotation
keeps failing, the process mints an `aws-waf-token` cookie with a throwaway
headless patchright load of /search?query=… (the one URL the WAF always
challenges) and attaches it to every new session — the token is accepted
from other exits (transfermarkt pattern). The browser does nothing else.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  MusixmatchUpstreamError  transport failure / 5xx / bad JSON  — retryable
  MusixmatchBlocked        WAF 202 / 403 / 405 / 429            — retryable on a new exit
  MusixmatchBadRequest     API 400                              — never retried
  MusixmatchNotFound       API 404 / page 404                   — never retried
"""
import base64
import datetime
import hashlib
import hmac
import json
import os
import re
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlencode

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

SITE = "https://www.musixmatch.com"
API_BASE = SITE + "/ws/1.1/"
APP_ID = "community-app-v1.0"
IMPERSONATE = "chrome"

# Read from _app-<hash>.js (module 22325: `a.from("=MmNy…".split("").reverse()
# .join(""),"base64")`) on 2026-09-19, bundle mxm-com@1.41.7.
DEFAULT_CLIENT_KEY = "f09016176ba43a1cfd1031fbd6b3d26c"
_APP_BUNDLE_RE = re.compile(r'src="([^"]*/_next/static/chunks/pages/_app-[^"]+\.js)"')
_KEY_RE = re.compile(r'"([A-Za-z0-9+/=]{16,})"\.split\(""\)\.reverse\(\)\.join\(""\)\s*,\s*"base64"')

API_TIMEOUT = 30
PAGE_TIMEOUT = 45
FANOUT_WORKERS = 4

WAF_MARKER = "awswafcookiedomainlist"
WAF_COOKIE = "aws-waf-token"
WAF_MINT_URL = SITE + "/search?query=lyrics"
HARVEST_SETTLE_TIMEOUT = 60
HARVEST_POLL_INTERVAL = 2
TOKEN_REMINT_AFTER = 120      # a token still blocked after this long is re-minted

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

API_HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.9",
    "origin": SITE,
    "referer": SITE + "/",
}
PAGE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "upgrade-insecure-requests": "1",
}


class MusixmatchUpstreamError(UpstreamError):
    """Transport failure, 5xx or an unreadable body — retryable."""


class MusixmatchBlocked(MusixmatchUpstreamError, Blocked):
    """AWS WAF challenge / 403 / 405 / 429 — retryable on a fresh exit."""


class MusixmatchBadRequest(BadRequest):
    """API 400 — never retried."""


class MusixmatchNotFound(NotFound):
    """Entity / page does not exist — never retried."""


class _SignatureRejected(MusixmatchUpstreamError):
    """HTTP 401 on a signed API call: the client key is stale."""


# ---- signing -----------------------------------------------------------------------

_key_lock = threading.Lock()
_client_key = {"value": DEFAULT_CLIENT_KEY, "refreshed_at": 0.0}


def sign_url(url, key=None, now=None):
    """Append signature + signature_protocol to a fully built API url."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    message = url + now.strftime("%Y%m%d")
    digest = hmac.new((key or _client_key["value"]).encode(), message.encode(), hashlib.sha256).digest()
    signature = base64.b64encode(digest).decode()
    return url + "&" + urlencode({"signature": signature, "signature_protocol": "sha256"})


def extract_client_key(bundle_js):
    """The reversed-base64 CLIENT_KEY literal of the _app bundle -> key, or None."""
    for match in _KEY_RE.finditer(bundle_js or ""):
        try:
            key = base64.b64decode(match.group(1)[::-1]).decode()
        except Exception:
            continue
        if re.fullmatch(r"[0-9a-f]{32}", key):
            return key
    return None


def _refresh_client_key():
    """Re-read CLIENT_KEY from the live bundle (at most once a minute).
    Returns True when the key changed."""
    with _key_lock:
        if time.monotonic() - _client_key["refreshed_at"] < 60:
            return False
        _client_key["refreshed_at"] = time.monotonic()
        try:
            home = _raw_get(SITE + "/", PAGE_HEADERS, PAGE_TIMEOUT).text
            bundle = _APP_BUNDLE_RE.search(home or "")
            if not bundle:
                return False
            src = bundle.group(1)
            src = src if src.startswith("http") else SITE + src
            key = extract_client_key(_raw_get(src, {"accept": "*/*"}, PAGE_TIMEOUT).text)
        except Exception as e:
            print(f"musixmatch: client key refresh failed: {type(e).__name__}: {e}")
            return False
        if key and key != _client_key["value"]:
            print("musixmatch: client key rotated")
            _client_key["value"] = key
            return True
        return False


# ---- sessions ----------------------------------------------------------------------
# One curl session per worker thread (a curl handle must not be shared across
# threads). Each session holds one sticky exit and is rotated after
# config.MUSIXMATCH_REQUESTS_PER_EXIT requests or on any failure.
_local = threading.local()


def _session():
    sess = getattr(_local, "session", None)
    if sess is not None and getattr(_local, "used", 0) >= config.MUSIXMATCH_REQUESTS_PER_EXIT:
        _drop_session()
        sess = None
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = config.musixmatch_proxy()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        sess.mxm_proxy = proxy
        token = _current_token()
        if token:
            sess.cookies.set(WAF_COOKIE, token, domain="www.musixmatch.com")
        _local.session = sess
        _local.used = 0
    _local.used = getattr(_local, "used", 0) + 1
    return sess


def _drop_session():
    """Close the thread's session so a challenged exit / keep-alive dies."""
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _raw_get(url, headers, timeout):
    sess = _session()
    try:
        return sess.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    except Exception as e:
        raise MusixmatchUpstreamError(f"request failed: {type(e).__name__}: {e}")


def dump_debug(name, text):
    """Write a raw response to $MUSIXMATCH_DEBUG_DIR/<name>.txt."""
    dbg = os.environ.get("MUSIXMATCH_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- AWS WAF token (fallback identity) ---------------------------------------------
_identity = None
_identity_lock = threading.Lock()


def _current_token():
    ident = _identity
    return ident["token"] if ident else None


def _harvest_token(proxy):
    """One throwaway headless patchright load of the always-challenged
    search page on `proxy`; the challenge clears itself and sets
    aws-waf-token. Returns the token. Raises RuntimeError when none appears."""
    from chrome_manager import create_scope
    from patchright_driver import PatchrightDriver

    print("musixmatch: minting aws-waf-token via patchright...")
    with create_scope():
        driver = PatchrightDriver(proxy_url=proxy, headless=True)
    try:
        driver.nav(WAF_MINT_URL, referer=SITE + "/", mode="blocked", challenge_markers=(WAF_MARKER,))
        deadline = time.monotonic() + HARVEST_SETTLE_TIMEOUT
        while True:
            cookies = {c["name"]: c["value"] for c in driver.call(lambda page: page.context.cookies())}
            token = cookies.get(WAF_COOKIE)
            if token:
                print(f"musixmatch: aws-waf-token minted ({len(token)} chars)")
                return token
            if time.monotonic() >= deadline:
                raise RuntimeError("AWS WAF challenge did not set aws-waf-token")
            time.sleep(HARVEST_POLL_INTERVAL)
    finally:
        driver.close()


def _mint_token(proxy):
    """Mint a token unless a fresh one exists; one thread mints, others reuse."""
    global _identity
    if not config.MUSIXMATCH_WAF_FALLBACK:
        return None
    with _identity_lock:
        ident = _identity
        if ident and time.monotonic() - ident["minted_at"] < TOKEN_REMINT_AFTER:
            return ident["token"]
        try:
            token = _harvest_token(proxy)
        except Exception as e:
            print(f"musixmatch: WAF token mint failed: {type(e).__name__}: {e}")
            return None
        _identity = {"token": token, "minted_at": time.monotonic()}
        return token


# ---- classification + retry ----------------------------------------------------------

def _is_waf(resp):
    return resp.status_code in (202, 405) or WAF_MARKER in (resp.text or "")[:5000].lower()


def _classify_http(resp, label):
    status = resp.status_code
    if status == 200 and not _is_waf(resp):
        return
    if _is_waf(resp) or status in (403, 429):
        dump_debug("blocked", resp.text)
        raise MusixmatchBlocked(f"HTTP {status} on {label}")
    if status == 404:
        raise MusixmatchNotFound(f"{label} not found")
    if status == 401:
        raise _SignatureRejected(f"HTTP 401 on {label}")
    if status == 400:
        raise MusixmatchBadRequest(f"upstream rejected {label}")
    raise MusixmatchUpstreamError(f"HTTP {status} on {label}")


def _retrying(fn):
    """Transport errors rotate the exit; a WAF block rotates the exit and,
    before the last try, mints the fallback token; a stale signing key is
    re-read once."""
    last = None
    key_refreshed = False
    for attempt in range(1, config.MAX_RETRIES + 1):
        used_key = _client_key["value"]
        try:
            return fn()
        except _SignatureRejected as e:
            last = e
            if _client_key["value"] != used_key:
                # another thread already rotated the key (and the refresh
                # throttle would now refuse to re-read it): just re-sign
                continue
            if key_refreshed or not _refresh_client_key():
                raise MusixmatchUpstreamError(f"musixmatch rejected the request signature: {e}")
            key_refreshed = True
            continue
        except MusixmatchBlocked as e:
            last = e
            proxy = getattr(getattr(_local, "session", None), "mxm_proxy", None)
            _drop_session()
            if attempt >= config.MAX_RETRIES - 1:
                _mint_token(proxy or config.musixmatch_proxy())
        except MusixmatchUpstreamError as e:
            last = e
            _drop_session()
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


# ---- API -----------------------------------------------------------------------------

def build_api_url(method, params):
    query = {"app_id": APP_ID, "format": "json"}
    for key, value in (params or {}).items():
        if value is None or value == "":
            continue
        query[key] = int(value) if isinstance(value, bool) else value
    return API_BASE + method + "?" + urlencode(query)


# API method -> the entity its 404 means (for the error message).
_NOT_FOUND_ENTITY = {
    "track.get": "track", "tracks.get": "tracks", "track.lyrics.get": "lyrics", "track.snippet.get": "lyrics snippet",
    "track.writers.get": "track writers", "crowd.track.metadata.get": "track structure",
    "artist.get": "artist", "artist.albums.get": "artist", "macro.artist.image.get": "artist",
    "album.get": "album", "album.tracks.get": "album tracks",
}


def _api_once(method, params):
    url = sign_url(build_api_url(method, params))
    resp = _raw_get(url, API_HEADERS, API_TIMEOUT)
    _classify_http(resp, method)
    try:
        payload = resp.json()
    except Exception:
        dump_debug("nonjson", resp.text)
        raise MusixmatchBlocked(f"non-JSON response from {method}")
    message = (payload or {}).get("message") or {}
    header = message.get("header") or {}
    status = header.get("status_code")
    body = message.get("body")
    if status == 200:
        return {"body": body if isinstance(body, dict) else {}, "header": header}
    if status == 404:
        raise MusixmatchNotFound(f"{_NOT_FOUND_ENTITY.get(method, 'resource')} not found")
    if status == 400:
        raise MusixmatchBadRequest(header.get("hint") or f"{method} rejected the parameters")
    if status in (401, 402, 403):
        raise MusixmatchUpstreamError(f"{method} is not available ({status}{': ' + header['hint'] if header.get('hint') else ''})")
    raise MusixmatchUpstreamError(f"{method} answered status {status}")


def api(method, params=None):
    """Call one signed API method -> {"body": dict, "header": dict}."""
    return _retrying(lambda: _api_once(method, params))


def api_body(method, params=None):
    return api(method, params)["body"]


# ---- pages ---------------------------------------------------------------------------

def extract_next_data(html):
    match = _NEXT_DATA_RE.search(html or "")
    if not match:
        return None
    try:
        return json.loads(match.group(1))
    except ValueError:
        return None


def _page_once(path):
    resp = _raw_get(SITE + path, PAGE_HEADERS, PAGE_TIMEOUT)
    if resp.status_code == 404:
        raise MusixmatchNotFound(f"{path} not found")
    _classify_http(resp, path)
    next_data = extract_next_data(resp.text)
    if next_data is None:
        dump_debug("nopayload", resp.text)
        raise MusixmatchBlocked(f"{path} returned no page payload")
    if next_data.get("page") in ("/404", "/_error"):
        raise MusixmatchNotFound(f"{path} not found")
    props = (next_data.get("props") or {}).get("pageProps") or {}
    return {"page": next_data.get("page"), "data": props.get("data") or {}}


# Small in-process memo so several routes served from ONE page (credits,
# analysis, contributions, translation all read the lyrics page) share a
# fetch within a few minutes. The route-level response cache sits above it.
_memo = OrderedDict()
_memo_lock = threading.Lock()
MEMO_TTL = 300
MEMO_MAX = 128


def memoized(key, fn, ttl=MEMO_TTL):
    now = time.monotonic()
    with _memo_lock:
        hit = _memo.get(key)
        if hit and now - hit[0] < ttl:
            _memo.move_to_end(key)
            return hit[1]
    value = fn()
    with _memo_lock:
        _memo[key] = (now, value)
        _memo.move_to_end(key)
        while len(_memo) > MEMO_MAX:
            _memo.popitem(last=False)
    return value


def page(path):
    """GET one www.musixmatch.com page -> {"page": route, "data": pageProps.data}."""
    return memoized(("page", path), lambda: _retrying(lambda: _page_once(path)))


def section(page_data, name):
    """pageProps.data.<name>.data, or None when absent or an error marker."""
    entry = (page_data or {}).get(name)
    if not isinstance(entry, dict) or "error" in entry:
        return None
    return entry.get("data")


# ---- fan-out -------------------------------------------------------------------------

def run_parallel(fns):
    """Run zero-arg callables in parallel; results align with `fns`.
    Exceptions propagate from the first failing call."""
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    with ThreadPoolExecutor(max_workers=min(FANOUT_WORKERS, len(fns))) as ex:
        futures = [ex.submit(fn) for fn in fns]
        return [f.result() for f in futures]


def optional(fn):
    """Wrap a call so NotFound / BadRequest yield None (optional enrichment)."""
    def run():
        try:
            return fn()
        except (MusixmatchNotFound, MusixmatchBadRequest):
            return None
    return run


if __name__ == "__main__":
    # Smoke test: python musixmatch/fetch.py [track vanity]
    vanity = sys.argv[1] if len(sys.argv) > 1 else "Coldplay/Yellow"
    track = api_body("track.get", {"commontrack_vanity_id": vanity}).get("track") or {}
    print("track:", track.get("track_name"), "-", track.get("artist_name"), track.get("track_id"))
    got = page("/lyrics/" + vanity)
    print("page:", got["page"], sorted(got["data"].keys()))
