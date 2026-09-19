"""/musixmatch/albums/details — album.get (label, copyright, release type,
external ids) + album.tracks.get (the full tracklist, one call of up to 100).
album.tracks.get needs the numeric album id, so a vanity ref resolves the
album first and then fetches its tracks."""
from musixmatch import fetch, parsers, refs

TRACKS_PAGE_SIZE = 100


def _tracks(album_id):
    body = fetch.api_body("album.tracks.get", {"album_id": album_id, "page_size": TRACKS_PAGE_SIZE})
    return [parsers.track_from_api(t) for t in parsers._items(body.get("track_list"), "track")]


def get_details(album):
    if album["kind"] == "album_id":
        album_body, tracks = fetch.run_parallel([
            lambda: fetch.api_body("album.get", {"album_id": album["value"]}),
            fetch.optional(lambda: _tracks(album["value"])),
        ])
        raw = album_body.get("album")
    else:
        raw = fetch.api_body("album.get", refs.album_api_params(album)).get("album")
        tracks = None
        if isinstance(raw, dict) and raw.get("album_id"):
            tracks = fetch.optional(lambda: _tracks(raw["album_id"]))()
    if not isinstance(raw, dict) or not raw.get("album_id"):
        raise fetch.MusixmatchNotFound("album not found")
    parsed = parsers.album_from_api(raw)
    parsed["tracks"] = [dict(t, position=i) for i, t in enumerate(tracks or [], 1)]
    return {"album": parsed}
