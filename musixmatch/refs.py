"""Musixmatch reference parsing: ONE param per input that auto-detects its
form (tripadvisor QueryOrIdField convention — never a sibling `url`/`id`
pair). Every resolver returns a small {"kind": ..., "value": ...} dict that
fetch-level helpers turn into the upstream API params (`api_params`).

  track    461806032                               Musixmatch track id
           Coldplay/Yellow                         artist/track vanity id
           https://www.musixmatch.com/lyrics/Coldplay/Yellow[/translation/french]
           https://www.musixmatch.com/es/letras/Coldplay/Yellow   (any locale)
           https://www.musixmatch.com/credits/461806032
           GBAYE0000267                            ISRC
           3AJwUDP919kvQ9QcozQPxg                  Spotify track id
           https://open.spotify.com/track/3AJw… | spotify:track:3AJw…
  artist   1039 | Coldplay | https://www.musixmatch.com/artist/Coldplay[/albums]
  album    20908173 | Coldplay/Parachutes | https://www.musixmatch.com/album/Coldplay/Parachutes
  creator  Chris-Martin-3 | https://www.musixmatch.com/creator/Chris-Martin-3[/credits]
  language es | spanish | Haitian Creole     (ISO 639-1 code or English name;
           translation routes also take the site's slug, e.g. chinese-trad)
  genre    14 | Pop | Pop-Pop-Rock | Pop / Pop/Rock   (id, name, vanity or full name)

Vanity ids are case-insensitive upstream (validated 2026-09-19: "coldplay/
yellow" resolves), so they are passed through as typed.

Also holds the tables the routes share: the 266 translation languages and
362 genres (musixmatch/data/*.json, captured from languages.get /
music.genres.get on 2026-09-19), credit-role categories, chart names and
sort orders.
"""
import json
import os
import re
from urllib.parse import unquote, urlparse

_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load(name):
    with open(os.path.join(_DATA, name), encoding="utf-8") as handle:
        return json.load(handle)


SITE = "https://www.musixmatch.com"

# ---- static tables ---------------------------------------------------------------------

LANGUAGES = _load("languages.json")            # [{code, iso_639_3, name}]
GENRES = _load("genres.json")                  # [{id, parent_id, name, full_name, vanity_id}]
ROLE_CATEGORIES = _load("role_categories.json")  # {role id: category name}
# The 88 languages the site publishes crowd translations into, with the URL
# slug of /lyrics/<a>/<t>/translation/<slug> and /discover/translated/<slug>
# (the "en" locale map in _app-<hash>.js, 2026-09-19). Slugs are NOT the
# languages.get names: ar -> "arab", fi -> "suomi", id -> "bahasa-indonesia",
# zh -> "chinese", z1 -> "chinese-trad", h3 -> "hindi-romanized".
TRANSLATION_LANGUAGES = _load("translation_languages.json")  # [{code, slug, name}]

_LANG_BY_CODE = {lang["code"].lower(): lang for lang in LANGUAGES}
_LANG_BY_ISO3 = {lang["iso_639_3"].lower(): lang for lang in LANGUAGES if lang.get("iso_639_3")}
_LANG_BY_NAME = {lang["name"].lower(): lang for lang in LANGUAGES}

_TR_BY_CODE = {lang["code"]: lang for lang in TRANSLATION_LANGUAGES}
_TR_BY_SLUG = {lang["slug"]: lang for lang in TRANSLATION_LANGUAGES}

_GENRE_BY_ID = {int(g["id"]): g for g in GENRES}
_GENRE_BY_KEY = {}
for _g in GENRES:
    for _key in (_g["vanity_id"], _g["full_name"], _g["name"]):
        # a vanity / full name is unique; a bare name may repeat under two
        # parents ("Pop" under Music and under Pop/Rock) — first (top-level) wins
        _GENRE_BY_KEY.setdefault((_key or "").strip().lower(), _g)

# Public chart name -> chart.tracks.get chart_name (semantics per Musixmatch's
# API docs; all four answer with different lists, validated 2026-09-19).
CHART_NAMES = {
    "top": "top",                         # editorial top chart
    "trending": "hot",                    # most viewed lyrics in the last 2 hours
    "weekly": "mxmweekly",                # most viewed lyrics in the last 7 days
    "weekly-new-releases": "mxmweekly_new",  # same, new releases only
}

# Public sort -> (upstream param, value).
TRACK_SORTS = {
    "relevance": None,
    "popularity": ("s_track_rating", "desc"),
    "newest": ("s_track_release_date", "desc"),
    "oldest": ("s_track_release_date", "asc"),
}
ALBUM_SORTS = {"newest": "desc", "oldest": "asc"}
ALBUM_TYPES = {"album": "album", "single": "single", "ep": "ep", "compilation": "compilation", "remix": "remix"}

# ---- helpers -----------------------------------------------------------------------------

_DIGITS_RE = re.compile(r"^\d{1,12}$")
_ISRC_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{3}\d{7}$")
_SPOTIFY_ID_RE = re.compile(r"^[A-Za-z0-9]{22}$")
_VANITY_PART_RE = re.compile(r"^[^\s/?#]+$")

# Localised first path segment for each page family ("/es/letras/A/T" etc).
_LYRICS_SEGMENTS = {"lyrics", "letras", "paroles", "testo", "songtext", "songtexte"}
_TRANSLATION_SEGMENTS = {"translation", "traduccion", "traduction", "traduzione", "ubersetzung",
                         "übersetzung", "traducao", "tradução"}
_LOCALES = {"es", "fr", "it", "de", "pt", "ja", "ko", "en"}


def _ref(kind, value):
    return {"kind": kind, "value": value}


def _as_url(text):
    if text.startswith("//"):
        return "https:" + text
    if "://" not in text:
        return "https://" + text
    return text


def _is_link(text):
    lowered = text.lower()
    return lowered.startswith(("http://", "https://", "//", "www.", "musixmatch.com", "open.spotify.com"))


def _musixmatch_segments(text, kind):
    """A musixmatch.com link -> its path segments (locale prefix dropped,
    percent-decoding applied). Raises ValueError for another host."""
    parsed = urlparse(_as_url(text))
    host = (parsed.hostname or "").lower()
    if host != "musixmatch.com" and not host.endswith(".musixmatch.com"):
        raise ValueError(f"{kind} link must be a musixmatch.com link")
    segments = [unquote(s) for s in parsed.path.split("/") if s]
    if segments and segments[0].lower() in _LOCALES and len(segments) > 1:
        segments = segments[1:]
    return segments


def _vanity(parts, kind):
    parts = [p.strip() for p in parts]
    if not all(p and _VANITY_PART_RE.match(p) for p in parts):
        raise ValueError(f"invalid {kind} vanity id")
    return "/".join(parts)


# ---- resolvers ---------------------------------------------------------------------------

def resolve_track(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("track must not be empty")
    if _DIGITS_RE.match(text):
        return _ref("track_id", int(text))
    if text.lower().startswith("spotify:track:"):
        spotify_id = text.split(":")[-1]
        if _SPOTIFY_ID_RE.match(spotify_id):
            return _ref("spotify_id", spotify_id)
        raise ValueError("invalid Spotify track URI")
    if _is_link(text):
        host = (urlparse(_as_url(text)).hostname or "").lower()
        if host == "open.spotify.com":
            parts = [p for p in urlparse(_as_url(text)).path.split("/") if p]
            if "track" in parts and parts.index("track") + 1 < len(parts):
                spotify_id = parts[parts.index("track") + 1]
                if _SPOTIFY_ID_RE.match(spotify_id):
                    return _ref("spotify_id", spotify_id)
            raise ValueError("Spotify link must be an open.spotify.com/track/ link")
        segments = _musixmatch_segments(text, "track")
        if len(segments) >= 2 and segments[0].lower() == "credits" and _DIGITS_RE.match(segments[1]):
            return _ref("track_id", int(segments[1]))
        if len(segments) >= 3 and segments[0].lower() in _LYRICS_SEGMENTS:
            return _ref("vanity", _vanity(segments[1:3], "track"))
        raise ValueError("track link must be a musixmatch.com/lyrics/<artist>/<track> link")
    upper = text.upper()
    if _ISRC_RE.match(upper):
        return _ref("isrc", upper)
    if "/" in text:
        parts = text.split("/")
        if len(parts) == 2:
            return _ref("vanity", _vanity(parts, "track"))
        raise ValueError("track vanity id must look like Artist/Track (e.g. Coldplay/Yellow)")
    if _SPOTIFY_ID_RE.match(text):
        return _ref("spotify_id", text)
    raise ValueError("track must be a Musixmatch track id, an Artist/Track vanity id, a musixmatch.com "
                     "lyrics link, an ISRC, or a Spotify track id/link")


def resolve_artist(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("artist must not be empty")
    if _DIGITS_RE.match(text):
        return _ref("artist_id", int(text))
    if _is_link(text):
        segments = _musixmatch_segments(text, "artist")
        if len(segments) >= 2 and segments[0].lower() == "artist":
            return _ref("vanity", _vanity(segments[1:2], "artist"))
        if len(segments) >= 2 and segments[0].lower() in _LYRICS_SEGMENTS | {"album"}:
            return _ref("vanity", _vanity(segments[1:2], "artist"))
        raise ValueError("artist link must be a musixmatch.com/artist/<artist> link")
    if "/" in text or " " in text:
        raise ValueError("artist must be a Musixmatch artist id, a vanity id (e.g. Taylor-Swift) or a "
                         "musixmatch.com/artist/ link; search by name with /musixmatch/search/artists")
    return _ref("vanity", _vanity([text], "artist"))


def resolve_album(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("album must not be empty")
    if _DIGITS_RE.match(text):
        return _ref("album_id", int(text))
    if _is_link(text):
        segments = _musixmatch_segments(text, "album")
        if len(segments) >= 3 and segments[0].lower() == "album":
            return _ref("vanity", _vanity(segments[1:3], "album"))
        raise ValueError("album link must be a musixmatch.com/album/<artist>/<album> link")
    parts = text.split("/")
    if len(parts) == 2:
        return _ref("vanity", _vanity(parts, "album"))
    raise ValueError("album must be a Musixmatch album id, an Artist/Album vanity id (e.g. "
                     "Coldplay/Parachutes) or a musixmatch.com/album/ link")


def resolve_creator(value):
    text = str(value or "").strip()
    if not text:
        raise ValueError("creator must not be empty")
    if _is_link(text):
        segments = _musixmatch_segments(text, "creator")
        if len(segments) >= 2 and segments[0].lower() == "creator":
            return _vanity(segments[1:2], "creator")
        raise ValueError("creator link must be a musixmatch.com/creator/<name> link")
    if "/" in text or " " in text:
        raise ValueError("creator must be a Musixmatch creator vanity id (e.g. Chris-Martin-3, the `vanity_id` "
                         "in /musixmatch/tracks/credits) or a musixmatch.com/creator/ link")
    return _vanity([text], "creator")


def resolve_language(value):
    """ISO 639-1 code, ISO 639-3 code or English name -> the language record."""
    text = " ".join(str(value or "").split()).lower()
    if not text:
        raise ValueError("language must not be empty")
    lang = (_LANG_BY_CODE.get(text) or _LANG_BY_ISO3.get(text) or _LANG_BY_NAME.get(text)
            or _LANG_BY_NAME.get(text.replace("-", " ")))
    if lang is None:
        raise ValueError("language must be an ISO 639-1 code (es, fr, ja, ...) or a language name "
                         "(spanish, haitian creole, ...); see /musixmatch/languages/list")
    return lang


def resolve_translation_language(value):
    """A language Musixmatch translates into, as an ISO 639-1 code, the site's
    slug ("spanish", "chinese-trad") or a languages.get name -> the language
    record with its `slug`."""
    text = " ".join(str(value or "").split()).lower()
    if not text:
        raise ValueError("language must not be empty")
    entry = _TR_BY_SLUG.get(text.replace(" ", "-"))
    if entry is None:
        try:
            entry = _TR_BY_CODE.get(resolve_language(text)["code"])
        except ValueError:
            entry = None
    if entry is None:
        raise ValueError("Musixmatch has no translations into that language; pass one of: "
                         + ", ".join(sorted(lang["code"] for lang in TRANSLATION_LANGUAGES)))
    base = _LANG_BY_CODE.get(entry["code"]) or {}
    return {"code": entry["code"], "iso_639_3": base.get("iso_639_3"), "name": entry["name"] or entry["slug"],
            "slug": entry["slug"]}


def resolve_genre(value):
    """Genre id, name, vanity id or full name -> genre id."""
    text = " ".join(str(value or "").split())
    if not text:
        raise ValueError("genre must not be empty")
    if _DIGITS_RE.match(text):
        genre_id = int(text)
        if genre_id not in _GENRE_BY_ID:
            raise ValueError("unknown genre id; see /musixmatch/genres/list")
        return genre_id
    genre = _GENRE_BY_KEY.get(text.lower())
    if genre is None:
        raise ValueError("unknown genre; pass a genre id or name from /musixmatch/genres/list")
    return int(genre["id"])


# ---- ref -> upstream API params ------------------------------------------------------------

_TRACK_PARAM = {"track_id": "track_id", "vanity": "commontrack_vanity_id",
                "isrc": "track_isrc", "spotify_id": "track_spotify_id"}
_ARTIST_PARAM = {"artist_id": "artist_id", "vanity": "artist_vanity_id"}
_ALBUM_PARAM = {"album_id": "album_id", "vanity": "album_vanity_id"}


def track_api_params(ref):
    return {_TRACK_PARAM[ref["kind"]]: ref["value"]}


def artist_api_params(ref):
    return {_ARTIST_PARAM[ref["kind"]]: ref["value"]}


def album_api_params(ref):
    return {_ALBUM_PARAM[ref["kind"]]: ref["value"]}


def language_record(code):
    """ISO 639-1 code (as the upstream returns it) -> {code, name} or None."""
    if not code:
        return None
    lang = _LANG_BY_CODE.get(str(code).lower())
    if lang is None:
        return {"code": str(code).lower(), "name": None}
    return {"code": lang["code"], "name": display_language_name(lang["name"])}


def display_language_name(name):
    """Upstream names are lower-case ("haitian creole") -> "Haitian creole"."""
    if not name:
        return None
    return name[:1].upper() + name[1:]


def language_slug(lang):
    """Translation page slug of a resolve_translation_language() record."""
    return lang["slug"]


def genre_record(genre_id):
    return _GENRE_BY_ID.get(int(genre_id)) if genre_id not in (None, "") else None


# ---- links ---------------------------------------------------------------------------------

def quote_vanity(vanity):
    from urllib.parse import quote
    return "/".join(quote(part, safe="-_.~()!'*") for part in str(vanity).split("/"))


def track_link(vanity):
    return f"{SITE}/lyrics/{quote_vanity(vanity)}" if vanity else None


def artist_link(vanity):
    return f"{SITE}/artist/{quote_vanity(vanity)}" if vanity else None


def album_link(vanity):
    return f"{SITE}/album/{quote_vanity(vanity)}" if vanity else None


def creator_link(vanity):
    return f"{SITE}/creator/{quote_vanity(vanity)}" if vanity else None
