"""Musixmatch payload -> API response shapes. Pure functions, no network.

Two upstream dialects feed ONE output shape per entity:

  * API objects (snake_case: track_id, commontrack_id, album_coverart_500x500,
    primary_genres.music_genre_list, external_ids, ...), from /ws/1.1/*
  * page objects (camelCase: id, commonTrackId, coverImageHD, artists[],
    externalIds, ...), from __NEXT_DATA__ of the server-rendered pages

so a track from /search/tracks and one from /discover/featured carry the
same keys (a field the dialect lacks is null, never omitted).

Upstream fields intentionally dropped (and why):
  * lyrics: script/pixel/html_tracking_url, backlink_url (tracking), can_edit,
    locked, check_validation_overridable, action_requested, published_status
    (community-editor state), lyrics_id is kept as `id`
  * track: lyrics_id, subtitle_id (internal ids no other route takes),
    track_share_url / track_edit_url (utm-tagged; `link` is rebuilt from the
    vanity id), hasPreReleaseRestricted, performersMiscTags (a static UI
    label table), performersTagging (always null anonymously)
  * artist: artist_fq_id ("mxm:artist:<id>", duplicates id), artist_edit_url /
    artist_share_url (link is rebuilt), managed (undocumented flag),
    imageCopyright (always empty), bandsintownUrl's app_id query (tracking)
  * lyrics-page user objects: rank colours / badge image urls / counters /
    weekly score / "key" (gamification presentation); the contributor `id`
    (a 150-char opaque uaid, not accepted by any route)
  * writers: writer_vanity_id (no public page or route takes it)
  * creator socials: __typename
"""
import datetime
import re

from musixmatch import refs

_NOCOVER_RE = re.compile(r"nocover|/images-storage/albums/nocover", re.I)


# ---- value helpers ---------------------------------------------------------------------

def text(value):
    """Stripped string, or None for None / "" / whitespace."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def integer(value):
    """int, or None when missing / not numeric."""
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def positive(value):
    """int > 0, else None (upstream uses 0 for "unknown")."""
    number = integer(value)
    return number if number and number > 0 else None


def flag(value):
    """1/0, "1"/"0", True/False -> bool; None stays None."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in ("1", "true", "yes")


def date(value):
    """Upstream date forms -> ISO date. "2000-07-10T00:00:00Z" -> "2000-07-10",
    "1996-09-00" -> "1996-09", "1996-00-00" -> "1996", "0000-00-00" -> None,
    epoch milliseconds -> "YYYY-MM-DD"."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().lstrip("-").isdigit()
                                          and len(value.strip()) > 8):
        try:
            stamp = int(value) / 1000
            return datetime.datetime.fromtimestamp(stamp, datetime.timezone.utc).date().isoformat()
        except (ValueError, OverflowError, OSError):
            return None
    raw = str(value).strip()[:10]
    parts = raw.split("-")
    if not parts or not parts[0].isdigit() or int(parts[0]) == 0:
        return None
    keep = [parts[0]]
    for part in parts[1:3]:
        if not part.isdigit() or int(part) == 0:
            break
        keep.append(part)
    return "-".join(keep)


def timestamp(value):
    """ISO datetime kept as UTC ISO ("2026-08-29T05:50:25Z"); epoch ms converted."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(value / 1000, datetime.timezone.utc) \
                .strftime("%Y-%m-%dT%H:%M:%SZ")
        except (ValueError, OverflowError, OSError):
            return None
    raw = str(value).strip()
    if raw.endswith("+00:00"):
        raw = raw[:-6] + "Z"
    return raw if raw and not raw.startswith("0000") else None


def image(value):
    """Image URL, or None for empty / Musixmatch's "nocover" placeholder."""
    url = text(value)
    if not url or _NOCOVER_RE.search(url):
        return None
    return url


def unique(values):
    out = []
    for value in values or []:
        if value in (None, "", 0) or value in out:
            continue
        out.append(value)
    return out


def _as_str_list(values):
    return unique(str(v) for v in (values or []) if v not in (None, "", 0))


def _flatten(values):
    out = []
    for value in values or []:
        if isinstance(value, list):
            out.extend(_flatten(value))
        else:
            out.append(value)
    return out


def _vanity_head(vanity):
    """"Coldplay/Yellow" -> "Coldplay" (the credited artist's vanity id)."""
    vanity = text(vanity)
    return vanity.split("/", 1)[0] if vanity and "/" in vanity else None


def _dig(obj, *path):
    for key in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def _items(value, key):
    """Upstream list of {key: {...}} wrappers -> the inner dicts."""
    out = []
    for entry in value or []:
        if isinstance(entry, dict):
            inner = entry.get(key)
            if isinstance(inner, dict):
                out.append(inner)
    return out


# ---- genres ------------------------------------------------------------------------------

def genre(g, is_primary=None):
    """API music_genre or page genre -> {id, name, full_name, is_primary}."""
    if not isinstance(g, dict):
        return None
    genre_id = positive(g.get("music_genre_id", g.get("id", g.get("musicGenreId"))))
    known = refs.genre_record(genre_id) if genre_id else None
    return {
        "id": genre_id,
        "name": text(g.get("music_genre_name") or g.get("name")) or (known or {}).get("name"),
        "full_name": text(g.get("music_genre_name_extended") or g.get("musicGenreNameExtended"))
        or (known or {}).get("full_name"),
        "is_primary": is_primary,
    }


def api_genres(obj):
    out = []
    for key, primary in (("primary_genres", True), ("secondary_genres", False)):
        for g in _items(_dig(obj, key, "music_genre_list"), "music_genre"):
            parsed = genre(g, primary)
            if parsed and parsed["id"] and all(o["id"] != parsed["id"] for o in out):
                out.append(parsed)
    return out


def page_genres(values):
    out = []
    for g in values or []:
        parsed = genre(g, None)
        if parsed and parsed["id"] and all(o["id"] != parsed["id"] for o in out):
            out.append(parsed)
    return out


def genre_list_item(g):
    return {
        "id": positive(g.get("music_genre_id")),
        "name": text(g.get("music_genre_name")),
        "full_name": text(g.get("music_genre_name_extended")),
        "parent_id": positive(g.get("music_genre_parent_id")),
    }


# ---- covers ---------------------------------------------------------------------------------

def _covers(size_100=None, size_350=None, size_500=None, size_800=None):
    covers = {"size_100": image(size_100), "size_350": image(size_350),
              "size_500": image(size_500), "size_800": image(size_800)}
    return covers if any(covers.values()) else None


def api_cover_images(obj):
    return _covers(obj.get("album_coverart_100x100"), obj.get("album_coverart_350x350"),
                   obj.get("album_coverart_500x500"), obj.get("album_coverart_800x800"))


# ---- artists --------------------------------------------------------------------------------

def artist_ref(artist_id, name, vanity):
    """Compact artist block embedded in tracks / albums."""
    return {"id": positive(artist_id), "name": text(name), "link": refs.artist_link(text(vanity)),
            "vanity_id": text(vanity)}


def _external_links(website=None, twitter=None, instagram=None, facebook=None, tiktok=None, youtube=None,
                    bandsintown=None, ticketmaster=None, tour=None, merchandise=None):
    if bandsintown:
        bandsintown = str(bandsintown).split("?", 1)[0]   # drops the came_from / app_id tracking query
    return {
        "website": text(website), "twitter": text(twitter), "instagram": text(instagram),
        "facebook": text(facebook), "tiktok": text(tiktok), "youtube": text(youtube),
        "bandsintown": text(bandsintown), "ticketmaster": text(ticketmaster),
        "tour": text(tour), "merchandise": text(merchandise),
    }


def _name_translations(values, wrapper, field):
    out = []
    for entry in _items(values, wrapper):
        name = text(entry.get("translation"))
        if name:
            out.append({"language": text(entry.get("language").lower() if entry.get("language") else None),
                        "name": name})
    return out


def artist_from_api(a, image_url=None):
    """artist.get / artist.search / chart.artists.get artist -> artist."""
    a = a or {}
    vanity = text(a.get("artist_vanity_id"))
    external = a.get("external_ids") or {}
    return {
        "id": positive(a.get("artist_id")),
        "name": text(a.get("artist_name")),
        "link": refs.artist_link(vanity),
        "vanity_id": vanity,
        "image": image(image_url),
        "comment": text(a.get("artist_comment")),
        "country": text(a.get("artist_country")),
        "formed_date": date(a.get("begin_date")) or text(a.get("begin_date_year")),
        "disbanded_date": date(a.get("end_date")) or text(a.get("end_date_year")),
        "aliases": unique(text(e.get("artist_alias")) for e in (a.get("artist_alias_list") or [])
                          if isinstance(e, dict)),
        "name_translations": _name_translations(a.get("artist_name_translation_list"),
                                                "artist_name_translation", "translation"),
        "genres": api_genres(a),
        "is_verified": None,
        "is_restricted": flag(a.get("restricted")),
        "popularity": integer(a.get("artist_rating")),
        "favorites_count": integer(a.get("artist_crowd_favourites")),
        "credited_artists": [artist_ref(c.get("artist_id"), c.get("artist_name"), c.get("artist_vanity_id"))
                             for c in _items(_dig(a, "artist_credits", "artist_list"), "artist")],
        "external_links": _external_links(
            a.get("artist_website_url"), a.get("artist_twitter_url"), a.get("artist_instagram_url"),
            a.get("artist_facebook_url"), a.get("artist_tiktok_url"), a.get("artist_youtube_url"),
            a.get("artist_bandsintown_url"), a.get("artist_ticketmaster_url"), a.get("artist_tour_url"),
            a.get("artist_merchandising_url")),
        "external_ids": {
            "spotify_ids": _as_str_list(external.get("spotify")),
            "itunes_ids": _as_str_list(external.get("itunes")),
            "seven_digital_ids": _as_str_list(external.get("7digital")),
            "musicbrainz_id": text(a.get("artist_mbid")),
        },
        "updated_at": timestamp(a.get("updated_time")),
    }


def artist_from_page(a):
    """Page artist (artistGet / chartArtistsGet / a track's artists[]) -> artist."""
    a = a or {}
    vanity = text(a.get("vanityId"))
    external = a.get("externalIds") or {}
    return {
        "id": positive(a.get("id")),
        "name": text(a.get("name")),
        "link": refs.artist_link(vanity),
        "vanity_id": vanity,
        "image": image(a.get("image")),
        "comment": None,
        "country": None,
        "formed_date": None,
        "disbanded_date": None,
        "aliases": unique(text(x) for x in (a.get("aliases") or [])),
        "name_translations": [],
        "genres": page_genres(a.get("genres")),
        "is_verified": flag(a.get("isVerified")),
        "is_restricted": None,
        "popularity": integer(a.get("rating")),
        "favorites_count": None,
        "credited_artists": [],
        "external_links": _external_links(a.get("websiteUrl"), a.get("twitterUrl"), None, None, None,
                                          a.get("youtubeUrl"), a.get("bandsintownUrl")),
        "external_ids": {
            "spotify_ids": _as_str_list(external.get("spotify")),
            "itunes_ids": _as_str_list(external.get("itunes")),
            "seven_digital_ids": _as_str_list(external.get("7digital")),
            "musicbrainz_id": None,
        },
        "updated_at": None,
    }


def track_artist_from_page(a):
    """Compact artist of a page track's artists[] (main + featured)."""
    a = a or {}
    out = artist_ref(a.get("id"), a.get("name"), a.get("vanityId"))
    out["is_featured"] = flag(a.get("isFeaturingArtist"))
    return out


# ---- tracks ---------------------------------------------------------------------------------

def track_from_api(t):
    """API track object (track.get / track.search / chart / album tracks) -> track."""
    t = t or {}
    vanity = text(t.get("commontrack_vanity_id"))
    album_vanity = text(t.get("album_vanity_id"))
    artist_vanity = _vanity_head(vanity) or _vanity_head(album_vanity)
    return {
        "id": positive(t.get("track_id")),
        "common_id": positive(t.get("commontrack_id")),
        "name": text(t.get("track_name")),
        "link": refs.track_link(vanity),
        "vanity_id": vanity,
        "artist": artist_ref(t.get("artist_id"), t.get("artist_name"), artist_vanity),
        "artists": None,
        "album": {
            "id": positive(t.get("album_id")),
            "name": text(t.get("album_name")),
            "link": refs.album_link(album_vanity),
            "vanity_id": album_vanity,
            "cover_images": api_cover_images(t),
        },
        "duration_seconds": positive(t.get("track_length")),
        "release_date": date(t.get("first_release_date")),
        "lyrics_snippet": None,
        "is_explicit": flag(t.get("explicit")),
        "is_instrumental": flag(t.get("instrumental")),
        "is_restricted": flag(t.get("restricted")),
        "is_pre_release": None,
        "has_lyrics": flag(t.get("has_lyrics")),
        "has_synced_lyrics": flag(t.get("has_subtitles")),
        "has_word_synced_lyrics": flag(t.get("has_richsync")),
        "has_structure": flag(t.get("has_track_structure")),
        "has_lyrics_analysis": flag(t.get("has_lyrics_analysis")),
        "popularity": integer(t.get("track_rating")),
        "favorites_count": integer(t.get("num_favourite")),
        "genres": api_genres(t),
        "name_translations": _name_translations(t.get("track_name_translation_list"),
                                                "track_name_translation", "translation"),
        "external_ids": {
            "isrc": text(t.get("track_isrc")),
            "isrcs": _as_str_list(_flatten(t.get("commontrack_isrcs"))),
            "spotify_id": text(t.get("track_spotify_id")),
            "spotify_ids": _as_str_list(t.get("commontrack_spotify_ids")),
            "itunes_ids": _as_str_list(t.get("commontrack_itunes_ids")),
            "seven_digital_ids": _as_str_list(t.get("commontrack_7digital_ids")),
            "soundcloud_id": text(positive(t.get("track_soundcloud_id"))),
            "musicbrainz_id": text(t.get("track_mbid")),
        },
        "updated_at": timestamp(t.get("updated_time")),
    }


def track_from_page(t):
    """Page track object (trackInfo.track / discover lists / album trackList) -> track."""
    t = t or {}
    vanity = text(t.get("vanityId"))
    album_vanity = text(t.get("albumVanityId"))
    artist_vanity = _vanity_head(vanity) or _vanity_head(album_vanity)
    artists = [track_artist_from_page(a) for a in (t.get("artists") or []) if isinstance(a, dict)]
    spotify_ids = _as_str_list(t.get("commontrackSpotifyIds"))
    return {
        "id": positive(t.get("id")),
        "common_id": positive(t.get("commonTrackId")),
        "name": text(t.get("name")),
        "link": refs.track_link(vanity),
        "vanity_id": vanity,
        "artist": artist_ref(t.get("artistId"), t.get("artistName"), artist_vanity),
        "artists": artists or None,
        "album": {
            "id": positive(t.get("albumId")),
            "name": text(t.get("albumName")),
            "link": refs.album_link(album_vanity),
            "vanity_id": album_vanity,
            "cover_images": _covers(None, t.get("coverImage"), t.get("coverImageHD")),
        },
        "duration_seconds": None,
        "release_date": date(t.get("releaseDate")),
        "lyrics_snippet": text(t.get("lyricsSnippet")),
        "is_explicit": flag(t.get("isExplicit")),
        "is_instrumental": flag(t.get("isInstrumental")),
        "is_restricted": None,
        "is_pre_release": flag(t.get("isPreRelease")),
        "has_lyrics": flag(t.get("hasLyrics")),
        "has_synced_lyrics": flag(t.get("hasSync")),
        "has_word_synced_lyrics": None,
        "has_structure": flag(t.get("hasTrackStructure")),
        "has_lyrics_analysis": None,
        "popularity": None,
        "favorites_count": None,
        "genres": [],
        "name_translations": [],
        "external_ids": {
            "isrc": None,
            "isrcs": [],
            "spotify_id": text(t.get("spotifyId")) or (spotify_ids[0] if spotify_ids else None),
            "spotify_ids": spotify_ids,
            "itunes_ids": _as_str_list(t.get("commontrackItunesIds")),
            "seven_digital_ids": [],
            "soundcloud_id": None,
            "musicbrainz_id": None,
        },
        "updated_at": timestamp(t.get("lastEditDate")),
    }


def track_summary(track):
    """Compact identity block of a parsed track (embedded in lyrics / credits / ...)."""
    if not track:
        return None
    return {key: track.get(key) for key in ("id", "common_id", "name", "link", "vanity_id", "artist", "album")}


# ---- albums ---------------------------------------------------------------------------------

def album_from_api(a):
    a = a or {}
    vanity = text(a.get("album_vanity_id"))
    external = a.get("external_ids") or {}
    return {
        "id": positive(a.get("album_id")),
        "name": text(a.get("album_name")),
        "link": refs.album_link(vanity),
        "vanity_id": vanity,
        "artist": artist_ref(a.get("artist_id"), a.get("artist_name"), _vanity_head(vanity)),
        "release_date": date(a.get("album_release_date")),
        "release_type": (text(a.get("album_release_type")) or "").lower() or None,
        "track_count": integer(a.get("album_track_count")),
        "label": text(a.get("album_label")),
        "copyright": text(a.get("album_copyright")),
        "phonographic_copyright": text(a.get("album_pline")),
        "genres": api_genres(a),
        "cover_images": api_cover_images(a),
        "is_restricted": flag(a.get("restricted")),
        "is_pre_release": None,
        "popularity": integer(a.get("album_rating")),
        "external_ids": {
            "spotify_ids": _as_str_list(external.get("spotify")),
            "itunes_ids": _as_str_list(external.get("itunes")),
            "amazon_music_ids": _as_str_list(external.get("amazon_music")),
            "seven_digital_ids": _as_str_list(external.get("7digital")),
            "musicbrainz_id": text(a.get("album_mbid")),
        },
        "updated_at": timestamp(a.get("updated_time")),
    }


def album_from_page(a):
    a = a or {}
    vanity = text(a.get("vanityId"))
    external = a.get("externalIds") or {}
    return {
        "id": positive(a.get("id")),
        "name": text(a.get("name")),
        "link": refs.album_link(vanity),
        "vanity_id": vanity,
        "artist": artist_ref(a.get("artistId"), a.get("artistName"), _vanity_head(vanity)),
        "release_date": date(a.get("releaseDate")),
        "release_type": (text(a.get("releaseType")) or "").lower() or None,
        "track_count": integer(a.get("trackCount")),
        "label": None,
        "copyright": None,
        "phonographic_copyright": None,
        "genres": [],
        # the page's bare coverImage is the 100x100 original (same url as the
        # API's album_coverart_100x100), not a full-size image
        "cover_images": _covers(a.get("coverImage"), None, a.get("coverImage500x500")),
        "is_restricted": None,
        "is_pre_release": flag(a.get("isPreRelease")),
        "popularity": None,
        "external_ids": {
            "spotify_ids": _as_str_list(external.get("spotify")),
            "itunes_ids": _as_str_list(external.get("itunes")),
            "amazon_music_ids": _as_str_list(external.get("amazon_music")),
            "seven_digital_ids": _as_str_list(external.get("7digital")),
            "musicbrainz_id": None,
        },
        "updated_at": None,
    }


# ---- lyrics ---------------------------------------------------------------------------------

def lyrics_lines(body):
    """Lyrics body -> its non-empty lines, in order (blank lines separate stanzas)."""
    return [line.strip() for line in (body or "").split("\n") if line.strip()]


def stanzas(body):
    out, current = [], []
    for line in (body or "").split("\n"):
        if line.strip():
            current.append(line.strip())
        elif current:
            out.append(current)
            current = []
    if current:
        out.append(current)
    return out


def writers(writer_list):
    out = []
    for entry in writer_list or []:
        if not isinstance(entry, dict):
            continue
        w = entry.get("writer") if isinstance(entry.get("writer"), dict) else entry
        name = text(w.get("writer_name"))
        if not name:
            continue
        out.append({"id": positive(w.get("writer_id")), "name": name, "role": text(entry.get("role"))})
    return out


def publishers(publisher_list):
    out = []
    for entry in publisher_list or []:
        if not isinstance(entry, dict):
            continue
        p = entry.get("publisher") if isinstance(entry.get("publisher"), dict) else entry
        name = text(p.get("publisher_name") or p.get("name"))
        if name and name not in out:
            out.append(name)
    return out


def lyrics(l, snippet=None):
    """track.lyrics.get lyrics (+ track.snippet.get snippet) -> lyrics block."""
    l = l or {}
    restricted = flag(l.get("restricted"))
    body = None if restricted else text(l.get("lyrics_body"))
    return {
        "id": positive(l.get("lyrics_id")),
        "language": refs.language_record(text(l.get("lyrics_language"))),
        "text": body,
        "lines": lyrics_lines(body),
        "stanzas": stanzas(body),
        "line_count": len(lyrics_lines(body)),
        "snippet": text((snippet or {}).get("snippet_body")),
        # a restricted track's copyright field carries the refusal notice
        # ("Unfortunately we're not authorized to show these lyrics."), not a copyright
        "copyright": None if restricted else text(l.get("lyrics_copyright")),
        "writers": writers(l.get("writer_list")),
        "publishers": publishers(l.get("publisher_list")),
        "is_verified": flag(l.get("verified")),
        "is_restricted": restricted,
        "is_explicit": flag(l.get("explicit")),
        "is_instrumental": flag(l.get("instrumental")),
        "updated_at": timestamp(l.get("updated_time")),
    }


def structure(metadata):
    """crowd.track.metadata.get metadata.track_structure -> sections in song
    order. The upstream list is already in song order but every entry's own
    `position` is 0 (validated 2026-09-19), so positions are numbered here."""
    entries = [e for e in (metadata or {}).get("track_structure") or [] if isinstance(e, dict)]
    out = []
    for i, e in enumerate(entries, 1):
        body = e.get("snippet") or ""
        out.append({
            "position": i,
            "type": text(e.get("description")),
            "lines": lyrics_lines(body),
            "text": text(body),
            "updated_at": timestamp(e.get("last_updated")),
        })
    return out


def page_structure(structure_list):
    """Lyrics page trackStructureList -> sections (fallback / page source)."""
    out = []
    for i, sec in enumerate(structure_list or []):
        if not isinstance(sec, dict):
            continue
        lines = [text(l.get("text")) for l in sec.get("lines") or [] if isinstance(l, dict) and text(l.get("text"))]
        out.append({"position": i + 1, "type": text(sec.get("title")), "lines": lines,
                    "text": "\n".join(lines) or None, "updated_at": None})
    return out


# ---- lyrics page sections --------------------------------------------------------------------

def credit(c):
    """creditsTrackCollaboratorsGet / artistCollaborators entry -> credited person."""
    c = c or {}
    vanity = text(c.get("vanity"))
    roles = []
    for r in c.get("roles") or []:
        if isinstance(r, str) and text(r):
            roles.append({"id": None, "name": text(r), "category": None})
        elif isinstance(r, dict) and text(r.get("name")):
            roles.append({"id": positive(r.get("id")), "name": text(r.get("name")),
                          "category": refs.ROLE_CATEGORIES.get(str(r.get("id")))})
    return {
        "id": text(c.get("id")),
        "name": text(c.get("name")),
        "link": refs.creator_link(vanity),
        "vanity_id": vanity,
        "stage_name": text(c.get("stageName")),
        "first_name": text(c.get("firstName")),
        "last_name": text(c.get("lastName")),
        "image": image(c.get("avatar_img_url") or c.get("avatarPicture")),
        "roles": roles,
    }


def lyric_video(v):
    """artistLyricVideos / allMxmCom*LyricsVideos entry -> lyric video."""
    v = v or {}
    vanity = text(v.get("trackVanityId"))
    return {
        "track": {"common_id": positive(v.get("commonTrackId")), "name": text(v.get("helperTrackName")),
                  "link": refs.track_link(vanity), "vanity_id": vanity},
        "video_link": text(v.get("youtubeVideo")),
        "type": text(v.get("lvType")),
        "created_at": timestamp(v.get("createdAt")),
    }


def lens(l):
    """trackInfo.track.lens (Musixmatch's AI lyrics analysis) -> analysis."""
    l = l or {}
    meaning = l.get("meaning") or {}
    moods = l.get("moods") or {}
    themes = l.get("themes") or {}
    rating = l.get("rating") or {}
    return {
        "meaning": text(meaning.get("explanation")),
        "moods": unique(text(m) for m in (moods.get("main_moods") or [])),
        "themes": [{"theme": text(t.get("theme")), "quotes": unique(text(q) for q in (t.get("quotes") or []))}
                   for t in (themes.get("main_themes") or []) if isinstance(t, dict) and text(t.get("theme"))],
        "content_rating": {"audience": text(rating.get("audience")),
                           "description": text(rating.get("descriptor"))} if rating else None,
    }


def contribution(h):
    """crowdTrackHistoryGet entry -> contribution."""
    h = h or {}
    return {
        "type": text(h.get("contributionType")),
        "date": timestamp(h.get("date")),
        "is_ai": flag(h.get("isAI")),
        "contributor": {"name": text(h.get("name")), "role": text(h.get("role")), "image": image(h.get("avatar"))},
    }


def transcriber(user):
    """lyrics.lyricsUser -> the community member credited for the lyrics."""
    if not isinstance(user, dict) or not text(user.get("user_name")):
        return None
    return {
        "name": text(user.get("user_name")),
        "image": image(user.get("user_profile_photo")),
        "rank": text(user.get("rank_name")),
        "level": text(user.get("level")),
        "score": integer(user.get("score")),
        "is_moderator": flag(user.get("moderator")),
        "is_admin": flag(user.get("admin")),
        "joined_at": timestamp(user.get("created")),
    }


def translation_lines(body, mapping):
    """Song-order translation: every lyrics line (repeats included) paired
    with its crowd translation. Without a lyrics body (restricted page) the
    translation mapping's own order is used."""
    mapping = {k.strip(): v for k, v in (mapping or {}).items() if isinstance(k, str) and text(k)}
    lines = lyrics_lines(body)
    if not lines:
        return [{"original": k, "translated": text(v)} for k, v in mapping.items()]
    return [{"original": line, "translated": text(mapping.get(line))} for line in lines]


# ---- creators ------------------------------------------------------------------------------------

def _social_link(url):
    url = text(url)
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def creator_profile(p):
    p = p or {}
    vanity = text(p.get("vanity"))
    return {
        "id": text(p.get("id")),
        "name": text(p.get("name")),
        "link": refs.creator_link(vanity),
        "vanity_id": vanity,
        "stage_name": text(p.get("stageName")),
        "first_name": text(p.get("firstName")),
        "last_name": text(p.get("lastName")),
        "aliases": unique(text(a) for a in (p.get("aliases") or [])),
        "image": image(p.get("avatarPicture")),
        "cover_image": image(p.get("coverPicture")),
        "biography": text(p.get("biography")),
        "biography_link": _social_link(p.get("biography_url")),
        "country": text(p.get("country")),
        "roles": unique(text(r) for r in (p.get("displayRoles") or [])),
        "is_claimed": flag(p.get("isClaimed")),
        "registry_id": text(p.get("registryId")),
        "socials": [{"type": text(s.get("type")), "link": _social_link(s.get("url"))}
                    for s in (p.get("socials") or []) if isinstance(s, dict) and text(s.get("url"))],
    }


def creator_artist(a):
    a = a or {}
    vanity = text(a.get("vanityId"))
    return {"id": positive(a.get("id")), "name": text(a.get("label")), "link": refs.artist_link(vanity),
            "vanity_id": vanity}


def creator_credit(c):
    c = c or {}
    artist_vanity = text(c.get("artistVanity"))
    return {
        "track": {"id": positive(c.get("trackId")), "name": text(c.get("trackTitle"))},
        "artist": artist_ref(c.get("artistId"), c.get("artistName"), artist_vanity),
        "album": {"id": positive(c.get("albumId")), "name": text(c.get("albumTitle")),
                  "cover_image": image(c.get("albumPictureUrl"))},
        "roles": [{"id": positive(r.get("id")), "name": text(r.get("name")),
                   "category": refs.ROLE_CATEGORIES.get(str(r.get("id"))), "is_verified": flag(r.get("verified"))}
                  for r in (c.get("roles") or []) if isinstance(r, dict) and text(r.get("name"))],
    }


# ---- reference lists ----------------------------------------------------------------------------

def language_item(entry):
    lang = entry.get("language") if isinstance(entry.get("language"), dict) else entry
    return {"code": text(lang.get("language_iso_code_1")),
            "iso_639_3": text(lang.get("language_iso_code_3")),
            "name": refs.display_language_name(text(lang.get("language_name")))}


def country_item(c):
    return {
        "code": text(c.get("iso_code")),
        "name": text(c.get("name")),
        "continent": {"code": text(c.get("continent_code")), "name": text(c.get("continent_description"))}
        if text(c.get("continent_code")) else None,
    }


# ---- pagination ----------------------------------------------------------------------------------

def pagination(page, page_size, total, count, cap=None):
    """Route-glue pagination block. `total` = header.available (None when
    the method does not report it: then "is there a next page" is inferred
    from a full page). `cap` = the deepest item the upstream serves."""
    if total is None:
        total_pages = page + 1 if count >= page_size else page
        total_count = None if count >= page_size else (page - 1) * page_size + count
    else:
        reachable = min(total, cap) if cap else total
        total_pages = max(1, -(-reachable // page_size)) if reachable else (page if count else 0)
        total_count = total
    return {"page": page, "items_per_page": page_size, "total_pages": total_pages, "total_count": total_count}
