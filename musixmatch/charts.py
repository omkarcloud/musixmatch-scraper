"""/musixmatch/charts/* — chart.tracks.get / chart.artists.get per country.

The charts are short (about 90 tracks and 80-100 artists, validated
2026-09-19) and the methods report no total, so "is there a next page" is
inferred from a full page. An unknown country silently falls back to the US
chart upstream, so the country is validated as ISO 3166-1 in the schema.
"""
from musixmatch import fetch, parsers, refs


def get_tracks(country="US", chart="top", has_lyrics=None, page=1, page_size=20):
    country = country or "US"   # `?country=` (blank) loads as None
    body = fetch.api_body("chart.tracks.get", {
        "country": country.lower(), "chart_name": refs.CHART_NAMES.get(chart or "top", "top"),
        "f_has_lyrics": 1 if has_lyrics else None, "page": page, "page_size": page_size,
    })
    tracks = [parsers.track_from_api(t) for t in parsers._items(body.get("track_list"), "track")]
    offset = (page - 1) * page_size
    ranked = [dict({"rank": offset + i}, **t) for i, t in enumerate(tracks, 1)]
    return {"pagination": parsers.pagination(page, page_size, None, len(tracks)),
            "country": country.upper(), "chart": chart or "top", "tracks": ranked}


def get_artists(country="US", page=1, page_size=20):
    country = country or "US"
    body = fetch.api_body("chart.artists.get", {"country": country.lower(), "page": page, "page_size": page_size})
    artists = [parsers.artist_from_api(a) for a in parsers._items(body.get("artist_list"), "artist")]
    offset = (page - 1) * page_size
    ranked = [dict({"rank": offset + i}, **a) for i, a in enumerate(artists, 1)]
    return {"pagination": parsers.pagination(page, page_size, None, len(artists)),
            "country": country.upper(), "artists": ranked}
