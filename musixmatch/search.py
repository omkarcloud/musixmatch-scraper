"""/musixmatch/search/* — track and artist search over the signed API.

track.search takes per-field terms (q_track, q_artist, q_track_artist,
q_lyrics, q_writer), filters (f_music_genre_id, f_lyrics_language,
f_has_lyrics, f_is_instrumental) and sorts (s_track_rating,
s_track_release_date). header.available is the total (capped at 10000);
the upstream serves pages 1-100 at up to 100 items each (page 101 -> 400,
validated 2026-09-19).

Ordering, measured 2026-09-19: the upstream's unsorted "relevance" order
buries the canonical recording under covers and remixes ("halo" + beyonce
-> "Halo (Mixed)", a club mix, ...; "yellow coldplay" -> karaoke covers),
while s_track_rating=desc puts it first ("Halo" 88, "Yellow" 76, Queen's
"Bohemian Rhapsody" 90). For lyric-phrase searches it is the reverse: the
rating sort drops the phrase match entirely. So the default is popularity,
except relevance when `lyrics` is searched. Free-text `query` maps to
q_track_artist (title + artist words); the bare `q` param matched almost
nothing useful and ignored its terms under the rating sort.
"""
from musixmatch import fetch, parsers, refs

MAX_PAGE = 100


def search_tracks(query=None, title=None, artist=None, lyrics=None, writer=None, genre=None, language=None,
                  has_lyrics=None, instrumental=None, sort=None, page=1, page_size=20):
    if sort is None:
        sort = "relevance" if lyrics else "popularity"
    params = {
        "q_track_artist": query, "q_track": title, "q_artist": artist, "q_lyrics": lyrics, "q_writer": writer,
        "f_music_genre_id": genre,
        "f_lyrics_language": language["code"] if language else None,
        "f_has_lyrics": 1 if has_lyrics else None,
        "f_is_instrumental": {"only": 1, "exclude": 0}.get(instrumental),
        "page": page, "page_size": page_size,
    }
    order = refs.TRACK_SORTS.get(sort)
    if order:
        params[order[0]] = order[1]
    result = fetch.api("track.search", params)
    tracks = [parsers.track_from_api(t) for t in parsers._items(result["body"].get("track_list"), "track")]
    total = parsers.integer(result["header"].get("available"))
    return {
        "pagination": parsers.pagination(page, page_size, total, len(tracks), cap=MAX_PAGE * page_size),
        "tracks": tracks,
    }


UPSTREAM_BLOCK = 100


def search_artists(query, page=1, page_size=20):
    """artist.search orders results differently per page_size: at 100 the
    exact-name artists lead ("coldplay" -> the Coldplay profiles, "taylor
    swift" -> Taylor Swift), at 5 collaborations lead ("The Chainsmokers
    feat. Coldplay"), validated 2026-09-19. So the upstream is always read in
    blocks of 100 and the requested page is sliced out, which keeps the
    order identical for every page_size. s_artist_rating is required: the
    unsorted order starts with empty duplicate profiles."""
    start = (page - 1) * page_size
    first_block = start // UPSTREAM_BLOCK + 1
    last_block = (start + page_size - 1) // UPSTREAM_BLOCK + 1
    results = fetch.run_parallel([
        (lambda b=b: fetch.api("artist.search", {"q_artist": query, "s_artist_rating": "desc",
                                                 "page": b, "page_size": UPSTREAM_BLOCK}))
        for b in range(first_block, last_block + 1)
    ])
    raw = []
    for result in results:
        raw.extend(parsers._items(result["body"].get("artist_list"), "artist"))
    offset = start - (first_block - 1) * UPSTREAM_BLOCK
    artists = [parsers.artist_from_api(a) for a in raw[offset:offset + page_size]]
    total = parsers.integer(results[0]["header"].get("available")) if results else None
    return {
        "pagination": parsers.pagination(page, page_size, total, len(artists), cap=MAX_PAGE * page_size),
        "artists": artists,
    }
