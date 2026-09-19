"""/musixmatch/artists/* — one artist, by id, vanity id or link.

details     macro.artist.image.get: ONE call returning the full artist.get
            record plus a cropped artist image (the plain artist.get has no
            image field)
albums      artist.albums.get (release-type filter, date sort, edition grouping)
tracks      track.search filtered by f_artist_id (sorted by popularity/date)
collaborators / lyric-videos
            the artist page's __NEXT_DATA__ (songwriters & producers credited
            on the artist's songs; official YouTube lyric videos)
"""
from musixmatch import fetch, lookup, parsers, refs
from musixmatch.search import MAX_PAGE

IMAGE_SIZE = 800


def get_details(artist):
    # The macro only resolves numeric ids (a vanity id answers an inner 404,
    # validated 2026-09-19), so a vanity goes through artist.get first.
    params = {"artist_id": lookup.artist_id(artist), "ww": IMAGE_SIZE, "hh": IMAGE_SIZE}
    body = fetch.api_body("macro.artist.image.get", params)
    inner = ((body.get("artist.get") or {}).get("message") or {})
    status = (inner.get("header") or {}).get("status_code")
    raw = ((inner.get("body") or {}) if isinstance(inner.get("body"), dict) else {}).get("artist")
    if status == 404 or not isinstance(raw, dict) or not raw.get("artist_id"):
        raise fetch.MusixmatchNotFound("artist not found")
    return {"artist": parsers.artist_from_api(raw, image_url=body.get("final_url"))}


def get_albums(artist, type=None, sort="newest", group_editions=True, page=1, page_size=20):
    params = dict(refs.artist_api_params(artist))
    params.update({
        "f_album_release_type": type,
        "s_release_date": refs.ALBUM_SORTS.get(sort or "newest"),
        "g_album_name": 1 if group_editions else None,
        "page": page, "page_size": page_size,
    })
    result = fetch.api("artist.albums.get", params)
    albums = [parsers.album_from_api(a) for a in parsers._items(result["body"].get("album_list"), "album")]
    total = parsers.integer(result["header"].get("available"))
    return {"pagination": parsers.pagination(page, page_size, total, len(albums), cap=MAX_PAGE * page_size),
            "albums": albums}


def get_tracks(artist, sort="popularity", has_lyrics=None, page=1, page_size=20):
    params = {"f_artist_id": lookup.artist_id(artist), "f_has_lyrics": 1 if has_lyrics else None,
              "page": page, "page_size": page_size}
    order = refs.TRACK_SORTS.get(sort or "popularity")
    if order:
        params[order[0]] = order[1]
    result = fetch.api("track.search", params)
    tracks = [parsers.track_from_api(t) for t in parsers._items(result["body"].get("track_list"), "track")]
    total = parsers.integer(result["header"].get("available"))
    return {"pagination": parsers.pagination(page, page_size, total, len(tracks), cap=MAX_PAGE * page_size),
            "tracks": tracks}


def _artist_page(artist):
    data = fetch.page("/artist/" + refs.quote_vanity(lookup.artist_vanity(artist)))["data"]
    raw = fetch.section(data, "artistGet")
    if not isinstance(raw, dict) or not raw.get("id"):
        raise fetch.MusixmatchNotFound("artist not found")
    return data, raw


def _artist_summary(raw):
    return {key: value for key, value in parsers.artist_from_page(raw).items()
            if key in ("id", "name", "link", "vanity_id", "image", "is_verified")}


def get_collaborators(artist):
    data, raw = _artist_page(artist)
    people = [parsers.credit(c) for c in fetch.section(data, "artistCollaborators") or [] if isinstance(c, dict)]
    return {"artist": _artist_summary(raw), "count": len(people), "collaborators": people}


def get_lyric_videos(artist):
    data, raw = _artist_page(artist)
    videos = [parsers.lyric_video(v) for v in fetch.section(data, "artistLyricVideos") or [] if isinstance(v, dict)]
    total = fetch.section(data, "artistLyricVideosCountGet")
    return {"artist": _artist_summary(raw), "total_count": parsers.integer(total), "count": len(videos),
            "lyric_videos": videos}
