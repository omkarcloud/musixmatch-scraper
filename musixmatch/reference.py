"""/musixmatch/{genres,languages,countries}/list — the reference tables the
other routes' params take (genre ids for search, language codes for
translations and search, country codes for charts), served live from
music.genres.get / languages.get / countries.get."""
from musixmatch import fetch, parsers


def list_genres():
    body = fetch.api_body("music.genres.get", {})
    genres = [parsers.genre_list_item(g) for g in parsers._items(body.get("music_genre_list"), "music_genre")]
    genres = [g for g in genres if g["id"]]
    genres.sort(key=lambda g: (g["full_name"] or g["name"] or "").lower())
    return {"count": len(genres), "genres": genres}


def list_languages():
    body = fetch.api_body("languages.get", {})
    languages = [parsers.language_item(entry) for entry in body.get("language_list") or [] if isinstance(entry, dict)]
    languages = [lang for lang in languages if lang["code"]]
    languages.sort(key=lambda lang: (lang["name"] or "").lower())
    return {"count": len(languages), "languages": languages}


def list_countries():
    body = fetch.api_body("countries.get", {})
    countries = [parsers.country_item(c) for c in body.get("countries_list") or [] if isinstance(c, dict)]
    countries = [c for c in countries if c["code"]]
    countries.sort(key=lambda c: c["name"] or "")
    return {"count": len(countries), "countries": countries}
