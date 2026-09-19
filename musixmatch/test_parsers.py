"""Offline tests for the Musixmatch scraper — no network.

Every fixture in musixmatch/fixtures/ is a real upstream payload captured on
2026-09-19: the signed API's message.body verbatim (lists trimmed to a few
items) and the data sections lifted out of the pages' __NEXT_DATA__. The
assertions pin the field mapping decoded from live data, so a silent
upstream rename shows up here rather than as nulls in a customer's response.
The endpoint tests monkeypatch fetch.api / fetch.page to those fixtures.

    python -m pytest musixmatch/test_parsers.py -q
"""
import datetime
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from schema_fields import load_query  # noqa: E402
from musixmatch import (albums, artists, charts, creators, discover, fetch, lookup,  # noqa: E402
                        parsers as P, refs, schemas, search, tracks)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    with open(os.path.join(FIXTURES, name + ".json"), encoding="utf-8") as handle:
        return json.load(handle)


# ---- refs ----------------------------------------------------------------------------------

def test_track_ref_forms():
    assert refs.resolve_track("461806032") == {"kind": "track_id", "value": 461806032}
    assert refs.resolve_track("Coldplay/Yellow") == {"kind": "vanity", "value": "Coldplay/Yellow"}
    assert refs.resolve_track("https://www.musixmatch.com/lyrics/Coldplay/Yellow/translation/french")["value"] \
        == "Coldplay/Yellow"
    assert refs.resolve_track("https://www.musixmatch.com/es/letras/Coldplay/Yellow")["value"] == "Coldplay/Yellow"
    assert refs.resolve_track("https://www.musixmatch.com/credits/461806032") == {"kind": "track_id",
                                                                                 "value": 461806032}
    assert refs.resolve_track("gbaye0000267") == {"kind": "isrc", "value": "GBAYE0000267"}
    assert refs.resolve_track("3AJwUDP919kvQ9QcozQPxg") == {"kind": "spotify_id", "value": "3AJwUDP919kvQ9QcozQPxg"}
    assert refs.resolve_track("spotify:track:3AJwUDP919kvQ9QcozQPxg")["kind"] == "spotify_id"
    assert refs.resolve_track("https://open.spotify.com/intl-de/track/3AJwUDP919kvQ9QcozQPxg?si=x")["kind"] \
        == "spotify_id"
    assert refs.resolve_track("https://www.musixmatch.com/lyrics/AD%C3%89LA-23/Track-2")["value"] == "ADÉLA-23/Track-2"


@pytest.mark.parametrize("bad", ["https://example.com/lyrics/a/b", "https://www.musixmatch.com/artist/Coldplay",
                                 "a/b/c", "yellow coldplay", "https://open.spotify.com/album/x"])
def test_track_ref_rejects(bad):
    with pytest.raises(ValueError):
        refs.resolve_track(bad)


def test_other_refs():
    assert refs.resolve_artist("1039") == {"kind": "artist_id", "value": 1039}
    assert refs.resolve_artist("https://www.musixmatch.com/artist/Coldplay/albums")["value"] == "Coldplay"
    assert refs.resolve_album("Coldplay/Parachutes") == {"kind": "vanity", "value": "Coldplay/Parachutes"}
    assert refs.resolve_album("https://www.musixmatch.com/album/Coldplay/Parachutes")["value"] == "Coldplay/Parachutes"
    assert refs.resolve_creator("https://www.musixmatch.com/creator/Chris-Martin-3") == "Chris-Martin-3"
    with pytest.raises(ValueError):
        refs.resolve_artist("Taylor Swift")
    with pytest.raises(ValueError):
        refs.resolve_creator("Chris Martin")


def test_languages_and_genres():
    assert refs.resolve_language("ES")["code"] == "es"
    assert refs.resolve_language("haitian creole")["code"] == "ht"
    assert refs.resolve_translation_language("zh")["slug"] == "chinese"
    assert refs.resolve_translation_language("chinese-trad")["code"] == "z1"
    assert refs.resolve_translation_language("arabic")["slug"] == "arab"      # API name -> site slug
    assert refs.resolve_translation_language("fi")["slug"] == "suomi"
    with pytest.raises(ValueError):
        refs.resolve_translation_language("klingon")
    assert refs.resolve_genre("14") == 14
    assert refs.resolve_genre("Pop-Pop-Rock") == 1133
    with pytest.raises(ValueError):
        refs.resolve_genre("not a genre")


# ---- schemas -------------------------------------------------------------------------------

def test_search_schema_needs_a_term_and_rejects_unknown_params():
    data, err = load_query(schemas.SearchTracksSchema, {"page": "2"})
    assert data is None and "query" in err["errors"]
    data, err = load_query(schemas.SearchTracksSchema, {"title": "yellow", "foo": "x"})
    assert data is None and "foo" in err["errors"]
    data, err = load_query(schemas.SearchTracksSchema, {"genre": "Latin", "language": "spanish", "page": "3"})
    assert err is None and data["genre"] == refs.resolve_genre("Latin") and data["language"]["code"] == "es"
    data, err = load_query(schemas.SearchTracksSchema, {"title": "x", "page": "101"})
    assert data is None and "page" in err["errors"]


def test_batch_schema_dedupes_and_limits():
    data, err = load_query(schemas.TrackBatchSchema, {"tracks": "1, 1 ,GBAYE0000267,Coldplay/Yellow"})
    assert err is None and [r["kind"] for r in data["tracks"]] == ["track_id", "isrc", "vanity"]
    data, err = load_query(schemas.TrackBatchSchema, {"tracks": ",".join(str(i) for i in range(1, 30))})
    assert data is None


# ---- value helpers ---------------------------------------------------------------------------

def test_value_helpers():
    assert P.date("2000-07-10T00:00:00Z") == "2000-07-10"
    assert P.date("1996-09-00") == "1996-09"
    assert P.date("0000-00-00") is None
    assert P.date(963187200000) == "2000-07-10"
    assert P.timestamp("2024-11-28T21:02:03+00:00") == "2024-11-28T21:02:03Z"
    assert P.image("https://s.mxmcdn.net/images-storage/albums/nocover.png") is None
    assert P.flag("1") is True and P.flag(0) is False and P.flag(None) is None


def test_signing_is_deterministic_and_key_extractable():
    now = datetime.datetime(2026, 9, 19, tzinfo=datetime.timezone.utc)
    url = fetch.build_api_url("track.get", {"track_id": 1, "empty": "", "skip": None})
    assert url.endswith("track.get?app_id=community-app-v1.0&format=json&track_id=1")
    signed = fetch.sign_url(url, key="k", now=now)
    assert signed.startswith(url + "&signature=") and signed.endswith("&signature_protocol=sha256")
    bundle = 'x=a.from("=MmNyQ2MiZDZiZWMzATMkZ2YxE2M0EmY2cTM2EDM5AjZ".split("").reverse().join(""),"base64")'
    assert fetch.extract_client_key(bundle) == fetch.DEFAULT_CLIENT_KEY


# ---- API parsers -------------------------------------------------------------------------------

def test_track_from_api():
    t = P.track_from_api(load("api_track_get")["track"])
    assert (t["id"], t["common_id"], t["name"]) == (461806032, 288342521, "Yellow")
    assert t["link"] == "https://www.musixmatch.com/lyrics/Coldplay/Yellow"
    assert t["artist"] == {"id": 1039, "name": "Coldplay", "link": "https://www.musixmatch.com/artist/Coldplay",
                           "vanity_id": "Coldplay"}
    assert t["album"]["name"] == "Parachutes" and t["album"]["cover_images"]["size_500"].endswith("_500_500.jpg")
    assert t["release_date"] == "2000-07-10" and t["duration_seconds"] == 267
    assert t["has_synced_lyrics"] is True and t["is_explicit"] is False
    assert t["external_ids"]["isrc"] == "GBAYE0000267" and "3AJwUDP919kvQ9QcozQPxg" in t["external_ids"]["spotify_ids"]
    assert [g["name"] for g in t["genres"]] == ["Alternative", "Pop"] and t["genres"][0]["is_primary"] is True


def test_lyrics_and_restricted_lyrics():
    lyr = P.lyrics(load("api_track_lyrics")["lyrics"], load("api_track_snippet")["snippet"])
    assert lyr["lines"][0] == "Look at the stars" and lyr["line_count"] == len(lyr["lines"])
    assert lyr["language"] == {"code": "en", "name": "English"} and lyr["snippet"]
    assert len(lyr["stanzas"]) > 1 and lyr["copyright"].startswith("Writer(s):")
    restricted = P.lyrics(load("api_track_lyrics_restricted")["lyrics"])
    assert restricted["is_restricted"] is True and restricted["text"] is None and restricted["copyright"] is None


def test_writers_structure():
    ws = P.writers(load("api_track_writers")["writer_list"])
    assert ws[0] == {"id": 949, "name": "Christopher Anthony John Martin", "role": None}
    sections = P.structure(load("api_track_metadata")["metadata"])
    assert [s["position"] for s in sections] == list(range(1, len(sections) + 1))
    assert sections[0]["type"] == "verse" and sections[0]["lines"][0] == "Look at the stars"


def test_artist_album_parsers():
    macro = load("api_artist_image_macro")
    a = P.artist_from_api(macro["artist.get"]["message"]["body"]["artist"], macro["final_url"])
    assert (a["id"], a["country"], a["formed_date"], a["disbanded_date"]) == (1039, "GB", "1996-09", None)
    assert a["image"] and a["external_links"]["bandsintown"] == "https://www.bandsintown.com/a/99"
    assert a["external_ids"]["musicbrainz_id"] == "cc197bad-dc9c-440d-a5b5-d52ba2e14234"
    assert a["name_translations"][0] == {"language": "ja", "name": "コールドプレイ"}
    al = P.album_from_api(load("api_album_get")["album"])
    assert (al["name"], al["label"], al["release_type"]) == ("Parachutes", "Parlophone UK", "album")
    assert al["artist"]["vanity_id"] == "Coldplay" and al["phonographic_copyright"].startswith("℗")


def test_reference_items():
    g = [P.genre_list_item(x) for x in P._items(load("api_genres")["music_genre_list"], "music_genre")]
    assert g[0]["id"] == 34 and g[0]["parent_id"] is None
    lang = P.language_item(load("api_languages")["language_list"][1])
    assert lang == {"code": "aa", "iso_639_3": "aar", "name": "Afar"}
    c = P.country_item(load("api_countries")["countries_list"][0])
    assert c == {"code": "AD", "name": "Andorra", "continent": {"code": "EU", "name": "Europe"}}


# ---- page parsers ----------------------------------------------------------------------------

def test_page_track_matches_api_shape():
    info = load("page_lyrics")["trackInfo"]["data"]
    page_track = P.track_from_page(info["track"])
    api_track = P.track_from_api(load("api_track_get")["track"])
    assert set(page_track) == set(api_track)
    assert page_track["common_id"] == 288342521 and page_track["artists"][0]["is_featured"] is False
    assert page_track["album"]["cover_images"]["size_500"].endswith("_500_500.jpg")


def test_credits_lens_contributions():
    data = load("page_lyrics")
    c = P.credit(data["creditsTrackCollaboratorsGet"]["data"][0])
    assert c["link"] == "https://www.musixmatch.com/creator/Chris-Martin-3"
    assert c["roles"][0] == {"id": 3, "name": "Composer", "category": "Songwriter"}
    lens = P.lens(data["trackInfo"]["data"]["track"]["lens"])
    assert lens["meaning"] and lens["moods"] and lens["themes"][0]["quotes"]
    assert lens["content_rating"]["audience"] == "G"
    h = P.contribution(data["crowdTrackHistoryGet"]["data"][0])
    assert h["type"] and h["contributor"]["name"] and h["date"].endswith("Z")
    t = P.transcriber(data["trackInfo"]["data"]["lyrics"]["lyricsUser"])
    assert t["name"] and t["rank"]


def test_translation_lines_keep_song_order_and_repeats():
    data = load("page_translation")
    body = data["trackInfo"]["data"]["lyrics"]["body"]
    lines = P.translation_lines(body, data["crowdTranslationGet"]["data"])
    assert len(lines) == len(P.lyrics_lines(body))
    assert lines[0] == {"original": "Look at the stars", "translated": "Regardez les étoiles"}
    assert P.translation_lines("", {"a": "b"}) == [{"original": "a", "translated": "b"}]


def test_creator_and_discover_parsers():
    cr = load("page_creator")
    profile = P.creator_profile(cr["professionalProfileGet"]["data"])
    assert profile["biography_link"] == "https://en.wikipedia.org/wiki/Chris_Martin"
    assert {"type": "twitter", "link": "https://twitter.com/coldplay"} in profile["socials"]
    credit = P.creator_credit(cr["professionalCreditsGet"]["data"][0])
    assert credit["track"]["name"] and credit["roles"][0]["category"] == "Songwriter"
    album = P.album_from_page(load("page_discover")["topAlbums"]["data"][0])
    assert album["cover_images"]["size_100"].endswith(".jpg") and album["release_date"] == "2024-02-16"


# ---- endpoints (transport monkeypatched) --------------------------------------------------------

API_FIXTURES = {
    "track.get": "api_track_get", "track.lyrics.get": "api_track_lyrics", "track.snippet.get": "api_track_snippet",
    "track.writers.get": "api_track_writers", "crowd.track.metadata.get": "api_track_metadata",
    "macro.artist.image.get": "api_artist_image_macro", "artist.albums.get": "api_artist_albums",
    "album.get": "api_album_get", "album.tracks.get": "api_album_tracks", "track.search": "api_track_search",
    "chart.tracks.get": "api_track_search", "chart.artists.get": "api_chart_artists",
    "artist.search": "api_chart_artists", "tracks.get": "api_album_tracks",
}
PAGE_FIXTURES = {"/lyrics/Coldplay/Yellow": "page_lyrics",
                 "/lyrics/Coldplay/Yellow/translation/french": "page_translation",
                 "/artist/Coldplay": "page_artist", "/creator/Chris-Martin-3": "page_creator",
                 "/discover": "page_discover", "/discover/translated/spanish": "page_translated"}


@pytest.fixture
def calls(monkeypatch):
    log = []

    def api(method, params=None):
        log.append((method, dict(params or {})))
        if method == "artist.get":
            return {"body": {"artist": load("api_artist_image_macro")["artist.get"]["message"]["body"]["artist"]},
                    "header": {}}
        return {"body": load(API_FIXTURES[method]), "header": {"available": 250}}

    def page(path):
        log.append(("page", path))
        if path not in PAGE_FIXTURES:
            raise fetch.MusixmatchNotFound(path)
        return {"page": path, "data": load(PAGE_FIXTURES[path])}

    monkeypatch.setattr(fetch, "api", api)
    monkeypatch.setattr(fetch, "api_body", lambda m, p=None: api(m, p)["body"])
    monkeypatch.setattr(fetch, "page", page)
    monkeypatch.setattr(fetch, "memoized", lambda key, fn, ttl=0: fn())
    return log


def test_search_tracks_defaults_and_params(calls):
    out = search.search_tracks(query="shape of you", page=2, page_size=10)
    method, params = calls[-1]
    assert method == "track.search" and params["q_track_artist"] == "shape of you"
    assert params["s_track_rating"] == "desc" and params["page"] == 2
    assert out["pagination"] == {"page": 2, "items_per_page": 10, "total_pages": 25, "total_count": 250}
    search.search_tracks(lyrics="look at the stars")
    assert "s_track_rating" not in calls[-1][1]            # lyric searches keep relevance order


def test_search_artists_reads_upstream_blocks_of_100(calls):
    search.search_artists("coldplay", page=3, page_size=40)       # items 80-119 -> blocks 1 and 2
    blocks = [p["page"] for m, p in calls if m == "artist.search"]
    assert sorted(blocks) == [1, 2] and all(p["page_size"] == 100 for m, p in calls if m == "artist.search")


def test_track_routes(calls):
    ref = refs.resolve_track("Coldplay/Yellow")
    assert tracks.get_details(ref)["track"]["id"] == 461806032
    lyr = tracks.get_lyrics(ref)
    assert lyr["has_lyrics"] and lyr["lyrics"]["snippet"] and lyr["track"]["name"] == "Yellow"
    assert tracks.get_structure(ref)["count"] > 0
    credits = tracks.get_credits(ref)
    assert credits["count"] == len(credits["credits"]) and credits["track"]["common_id"] == 288342521
    assert tracks.get_analysis(ref)["is_available"] is True
    tr = tracks.get_translation(ref, refs.resolve_translation_language("fr"))
    assert tr["is_available"] and tr["original_language"]["code"] == "en" and tr["language"]["name"] == "French"


def test_page_routes_resolve_vanity_from_track_id(calls):
    tracks.get_credits(refs.resolve_track("461806032"))
    assert ("page", "/lyrics/Coldplay/Yellow") in calls
    assert any(m == "track.get" and p == {"track_id": 461806032} for m, p in calls)


def test_artist_album_creator_chart_discover_routes(calls):
    details = artists.get_details(refs.resolve_artist("Coldplay"))
    assert details["artist"]["image"] and calls[-1][1]["artist_id"] == 1039    # vanity -> id first
    assert artists.get_collaborators(refs.resolve_artist("Coldplay"))["collaborators"][0]["roles"]
    videos = artists.get_lyric_videos(refs.resolve_artist("Coldplay"))
    assert videos["total_count"] and videos["lyric_videos"][0]["video_link"].startswith("https://www.youtube.com")
    album = albums.get_details(refs.resolve_album("20908173"))["album"]
    assert album["tracks"][0]["position"] == 1
    assert creators.get_details("Chris-Martin-3")["creator"]["artist_count"] > 0
    with pytest.raises(fetch.MusixmatchNotFound):
        creators.get_details("Nobody-Xyz")
    chart = charts.get_tracks(country="GB", chart="trending", page=2, page_size=3)
    assert calls[-1][1]["chart_name"] == "hot" and calls[-1][1]["country"] == "gb"
    assert chart["tracks"][0]["rank"] == 4
    featured = discover.get_featured()
    assert featured["trending_tracks"] and set(featured["weekly_top_tracks"]) == {"us", "it"}
    assert discover.get_translated(refs.resolve_translation_language("es"))["count"] > 0


def test_batch_groups_by_kind(calls, monkeypatch):
    monkeypatch.setattr(lookup, "track_object", lambda ref: load("api_track_get")["track"])
    refs_in = [refs.resolve_track(x) for x in ("440870112", "Coldplay/Yellow", "999")]
    out = tracks.get_batch(refs_in)
    assert [m for m, p in calls] == ["tracks.get"] and calls[0][1] == {"track_ids": "440870112,999"}
    assert [t["name"] for t in out["tracks"]] == ["Don't Panic", "Yellow"] and out["not_found"] == ["999"]
