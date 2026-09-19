"""/musixmatch/creators/* — Musixmatch Pro songwriter / producer profiles
(/creator/<vanity>): biography, roles, socials, the artists they wrote for
and their track credits. The page renders a 200 even for an unknown vanity
(with an empty profile), which is a NotFound here. The `vanity_id` of every
person in /tracks/credits and /artists/collaborators is a creator ref."""
from musixmatch import fetch, parsers, refs


def _creator_page(creator):
    data = fetch.page("/creator/" + refs.quote_vanity(creator))["data"]
    profile = fetch.section(data, "professionalProfileGet")
    if not isinstance(profile, dict) or not (profile.get("name") or profile.get("id")):
        raise fetch.MusixmatchNotFound("creator not found")
    return data, profile


def get_details(creator):
    data, profile = _creator_page(creator)
    parsed = parsers.creator_profile(profile)
    artists = [parsers.creator_artist(a) for a in fetch.section(data, "professionalArtistsGet") or []
               if isinstance(a, dict)]
    parsed["artist_count"] = len(artists)
    parsed["artists"] = artists
    return {"creator": parsed}


def get_credits(creator):
    data, profile = _creator_page(creator)
    parsed = parsers.creator_profile(profile)
    credits = [parsers.creator_credit(c) for c in fetch.section(data, "professionalCreditsGet") or []
               if isinstance(c, dict)]
    return {
        "creator": {key: parsed[key] for key in ("id", "name", "link", "vanity_id", "image")},
        "count": len(credits),
        "credits": credits,
    }
