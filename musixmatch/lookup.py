"""Ref -> upstream identity lookups shared by the endpoint modules.

A route's input ref (refs.resolve_*) is often enough to call the API
directly (every track method takes track_id / commontrack_vanity_id /
track_isrc / track_spotify_id). Pages, however, are addressed by vanity id
only, and track.search's artist filter by numeric id only — these helpers
bridge that with one memoized API call.
"""
from musixmatch import fetch, refs


def track_object(track_ref):
    """track.get for a ref -> the raw API track object (memoized)."""
    params = refs.track_api_params(track_ref)
    key = ("track.get",) + tuple(sorted(params.items()))
    body = fetch.memoized(key, lambda: fetch.api_body("track.get", params))
    track = body.get("track")
    if not isinstance(track, dict) or not track.get("track_id"):
        raise fetch.MusixmatchNotFound("track not found")
    return track


def track_vanity(track_ref):
    """The artist/track vanity id a lyrics page lives under."""
    if track_ref["kind"] == "vanity":
        return track_ref["value"]
    vanity = track_object(track_ref).get("commontrack_vanity_id")
    if not vanity:
        raise fetch.MusixmatchNotFound("track has no Musixmatch lyrics page")
    return vanity


def artist_object(artist_ref):
    params = refs.artist_api_params(artist_ref)
    key = ("artist.get",) + tuple(sorted(params.items()))
    body = fetch.memoized(key, lambda: fetch.api_body("artist.get", params))
    artist = body.get("artist")
    if not isinstance(artist, dict) or not artist.get("artist_id"):
        raise fetch.MusixmatchNotFound("artist not found")
    return artist


def artist_id(artist_ref):
    if artist_ref["kind"] == "artist_id":
        return artist_ref["value"]
    return int(artist_object(artist_ref)["artist_id"])


def artist_vanity(artist_ref):
    if artist_ref["kind"] == "vanity":
        return artist_ref["value"]
    vanity = artist_object(artist_ref).get("artist_vanity_id")
    if not vanity:
        raise fetch.MusixmatchNotFound("artist has no Musixmatch page")
    return vanity


def lyrics_page(track_ref, suffix=""):
    """The lyrics page (or a sub-page like /translation/<lang>) of a track."""
    vanity = track_vanity(track_ref)
    return fetch.page("/lyrics/" + refs.quote_vanity(vanity) + suffix)


def track_info(page_data):
    """pageProps.data.trackInfo.data -> (page track, page lyrics, info)."""
    info = fetch.section(page_data, "trackInfo") or {}
    track = info.get("track") if isinstance(info.get("track"), dict) else None
    if not track:
        raise fetch.MusixmatchNotFound("track not found")
    lyrics = info.get("lyrics") if isinstance(info.get("lyrics"), dict) else {}
    return track, lyrics, info
