"""Cache TTL per /musixmatch/* endpoint (cache.py, keyed on the validated
params — marshmallow fills the defaults, so `?sort=newest` and no `sort`
share a row).

Tiers follow how fast each surface moves: the 2-hour "trending" chart and
the discover lists churn within the hour; lyrics, credits and translations
are community-edited but change rarely once a song is out; catalogue data
(albums, artist profiles) changes a few times a year; the reference tables
almost never. Caching also keeps the per-IP WAF budget for new requests.
"""
from datetime import timedelta

# --- search ------------------------------------------------------------------
SEARCH_CACHE = timedelta(hours=6)

# --- tracks ------------------------------------------------------------------
TRACK_CACHE = timedelta(days=1)                  # details, batch
LYRICS_CACHE = timedelta(days=1)                 # lyrics, writers, structure
PAGE_SECTIONS_CACHE = timedelta(hours=12)        # credits, analysis, contributions
TRANSLATION_CACHE = timedelta(hours=12)

# --- artists / albums / creators ---------------------------------------------
ARTIST_CACHE = timedelta(days=1)
ARTIST_LISTS_CACHE = timedelta(hours=12)         # albums, tracks, collaborators, lyric videos
ALBUM_CACHE = timedelta(days=1)
CREATOR_CACHE = timedelta(days=1)

# --- charts / discover -------------------------------------------------------
CHART_CACHE = timedelta(minutes=30)              # chart=trending is a 2-hour window
DISCOVER_CACHE = timedelta(hours=1)

# --- reference ---------------------------------------------------------------
REFERENCE_CACHE = timedelta(days=7)
