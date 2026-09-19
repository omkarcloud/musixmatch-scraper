"""The 26 Musixmatch endpoints. Every path is served with and without the
`/musixmatch` prefix, so code generated against the hosted API on RapidAPI
(paths like /tracks/lyrics) runs unchanged against this server.

Every query is validated by the marshmallow schemas in musixmatch/schemas.py
(one param per input: `track` takes a track ID, an `Artist/Track` name, a
musixmatch.com link, an ISRC or a Spotify ID/link), then handed to the
scraper function; paginated endpoints get count / per_page / current_page /
total_pages / next / previous at the top.
"""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from musixmatch import albums, artists, charts, creators, discover, reference, schemas, search, tracks
from musixmatch.fetch import MusixmatchBadRequest, MusixmatchNotFound
from schema_fields import load_query


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Beyoncé" would arrive as "BeyoncÃ©")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(path, params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    host = request.urlparts.scheme + "://" + request.urlparts.netloc
    return f"{host}{path}?{urlencode(query)}"


def paginate(result, path, params):
    """Lift the scraper's `pagination` block into count / per_page /
    current_page / total_pages / next / previous."""
    pagination = result.pop("pagination", None) or {}
    page = int(pagination.get("page") or params.get("page") or 1)
    total_pages = int(pagination.get("total_pages") or 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(path, params, page + 1 if page < total_pages else None),
        "previous": _page_link(path, params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(path, schema, fn, paginated):
    """Validate -> run -> shared error mapping: bad params -> 400, missing
    entity -> 404, transport / blocks -> 500."""
    raw = query_dict()
    data, error = load_query(schema, raw)
    if error:
        return json_response(error, 400)
    try:
        result = fn(**data)
    except ValueError as e:                  # bad id / params
        return json_response({"error": str(e)}, 400)
    except MusixmatchBadRequest as e:        # upstream rejected the request
        return json_response({"error": f"musixmatch rejected the request: {e}"}, 400)
    except MusixmatchNotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:                   # retries exhausted / blocked
        return json_response({"error": f"musixmatch {path.strip('/')} failed: {e}"}, 500)
    if paginated:
        result = paginate(result, request.path, raw)
    return json_response(result)


def mount(path, schema, fn, paginated=False):
    """Serve a handler at /path and /musixmatch/path."""
    def handler():
        return call(path, schema, fn, paginated)
    handler.__name__ = "musixmatch_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/musixmatch" + path, method="GET")(handler)


ENDPOINTS = [
    ("/tracks/lyrics", schemas.TrackSchema, tracks.get_lyrics, False),
    ("/search/tracks", schemas.SearchTracksSchema, search.search_tracks, True),
    ("/search/artists", schemas.SearchArtistsSchema, search.search_artists, True),
    ("/tracks/details", schemas.TrackSchema, tracks.get_details, False),
    ("/tracks/translation", schemas.TrackTranslationSchema, tracks.get_translation, False),
    ("/tracks/analysis", schemas.TrackSchema, tracks.get_analysis, False),
    ("/tracks/credits", schemas.TrackSchema, tracks.get_credits, False),
    ("/tracks/writers", schemas.TrackSchema, tracks.get_writers, False),
    ("/tracks/structure", schemas.TrackSchema, tracks.get_structure, False),
    ("/tracks/contributions", schemas.TrackSchema, tracks.get_contributions, False),
    ("/tracks/batch", schemas.TrackBatchSchema, tracks.get_batch, False),
    ("/artists/details", schemas.ArtistSchema, artists.get_details, False),
    ("/artists/albums", schemas.ArtistAlbumsSchema, artists.get_albums, True),
    ("/artists/tracks", schemas.ArtistTracksSchema, artists.get_tracks, True),
    ("/artists/collaborators", schemas.ArtistSchema, artists.get_collaborators, False),
    ("/artists/lyric-videos", schemas.ArtistSchema, artists.get_lyric_videos, False),
    ("/albums/details", schemas.AlbumSchema, albums.get_details, False),
    ("/creators/details", schemas.CreatorSchema, creators.get_details, False),
    ("/creators/credits", schemas.CreatorSchema, creators.get_credits, False),
    ("/charts/tracks", schemas.ChartTracksSchema, charts.get_tracks, True),
    ("/charts/artists", schemas.ChartArtistsSchema, charts.get_artists, True),
    ("/discover/featured", schemas.EmptySchema, discover.get_featured, False),
    ("/discover/translated", schemas.TranslationLanguageSchema, discover.get_translated, False),
    ("/genres/list", schemas.EmptySchema, reference.list_genres, False),
    ("/languages/list", schemas.EmptySchema, reference.list_languages, False),
    ("/countries/list", schemas.EmptySchema, reference.list_countries, False),
]

for _path, _schema, _fn, _paginated in ENDPOINTS:
    mount(_path, _schema, _fn, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})
