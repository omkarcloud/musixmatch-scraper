"""/musixmatch/discover/* — the lists Musixmatch curates on its /discover
pages (server-rendered only; no API method exposes "trending" or the
weekly per-country tops anonymously).

featured     /discover: trending tracks, top tracks, weekly top tracks for the
             US and Italy, top albums, top artists, and tracks with an official
             lyric video (with the YouTube link)
translated   /discover/translated/<language>: songs whose lyrics were most
             recently translated into that language

Dropped from /discover (editorial / presentation only): community cards,
banners, "lyrics in motion" cards, the podcast teaser, pre-release albums
(an error marker for anonymous visitors).
"""
from musixmatch import fetch, parsers, refs


def _tracks(data, name):
    return [parsers.track_from_page(t) for t in fetch.section(data, name) or [] if isinstance(t, dict)]


def get_featured():
    data = fetch.page("/discover")["data"]
    videos = {}
    for key in ("allMxmComTopLyricsVideos", "allMxmComLyricsVideos"):
        for v in fetch.section(data, key) or []:
            if isinstance(v, dict) and parsers.positive(v.get("commonTrackId")):
                videos.setdefault(parsers.positive(v.get("commonTrackId")), parsers.text(v.get("youtubeVideo")))
    video_tracks = [dict(t, lyric_video_link=videos.get(t["common_id"])) for t in _tracks(data, "topVideoTracksGet")]
    return {
        "trending_tracks": _tracks(data, "trendingTracksGet"),
        "top_tracks": _tracks(data, "topTracksGet"),
        "weekly_top_tracks": {"us": _tracks(data, "topTracksWeeklyGetUS"), "it": _tracks(data, "topTracksWeeklyGetIT")},
        "top_albums": [parsers.album_from_page(a) for a in fetch.section(data, "topAlbums") or [] if isinstance(a, dict)],
        "top_artists": [parsers.artist_from_page(a) for a in fetch.section(data, "chartArtistsGet") or []
                        if isinstance(a, dict)],
        "lyric_video_tracks": video_tracks,
    }


def get_translated(language):
    data = fetch.page("/discover/translated/" + refs.language_slug(language))["data"]
    tracks = _tracks(data, "trackTranslationSearch")
    return {"language": {"code": language["code"], "name": refs.display_language_name(language["name"])},
            "count": len(tracks), "tracks": tracks}
