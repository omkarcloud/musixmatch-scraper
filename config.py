"""Configuration for the Musixmatch Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT                          port the API listens on (default 8000)
    MUSIXMATCH_PROXY              proxy URL for every request, e.g.
                                  http://user:pass@host:port (default: none —
                                  direct). Musixmatch sits behind AWS WAF, which
                                  rate-limits each IP at roughly 100 requests per
                                  5 minutes. Light use works direct; for volume,
                                  point this at a ROTATING residential proxy.
    MUSIXMATCH_REQUESTS_PER_EXIT  requests before a fresh proxy connection is
                                  opened (default 40 — with a rotating proxy
                                  every new connection is a new IP)
    MUSIXMATCH_WAF_FALLBACK       "true" to solve an AWS WAF challenge with a
                                  headless browser when retries keep failing
                                  (default false; needs the optional patchright
                                  setup, off in this lightweight build)

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

MUSIXMATCH_PROXY = os.environ.get("MUSIXMATCH_PROXY") or None
MUSIXMATCH_REQUESTS_PER_EXIT = int(os.environ.get("MUSIXMATCH_REQUESTS_PER_EXIT", "40"))
MUSIXMATCH_WAF_FALLBACK = os.environ.get("MUSIXMATCH_WAF_FALLBACK", "").lower() in ("1", "true", "yes")


def musixmatch_proxy():
    return os.environ.get("MUSIXMATCH_PROXY") or None
