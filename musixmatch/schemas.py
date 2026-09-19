"""Marshmallow request schemas for every /musixmatch/* route.

Generic fields live in the shared top-level schema_fields.py; this module
adds the Musixmatch resolvers (refs.py) and the per-route schemas. Every
schema's load() output is the kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair): `track` accepts a track id, an Artist/Track vanity id, a
musixmatch.com lyrics link, an ISRC or a Spotify track id/link; `artist`,
`album` and `creator` accept an id or vanity id or a musixmatch.com link;
`language` an ISO 639-1 code or an English language name; `genre` a genre
id or name.
"""
from marshmallow import ValidationError, fields, validates_schema

from schema_fields import (BaseSchema, ChoiceField, CountryCodeField, Flag, PageField, PageSizeField,
                           QueryField, RefField)
from musixmatch import refs
from musixmatch.search import MAX_PAGE

BATCH_MAX = 20


# ---- id-or-link fields ---------------------------------------------------------------------

class TrackRefField(RefField):
    resolver = staticmethod(refs.resolve_track)


class ArtistRefField(RefField):
    resolver = staticmethod(refs.resolve_artist)


class AlbumRefField(RefField):
    resolver = staticmethod(refs.resolve_album)


class CreatorRefField(RefField):
    resolver = staticmethod(refs.resolve_creator)


class LanguageField(RefField):
    resolver = staticmethod(refs.resolve_language)


class TranslationLanguageField(RefField):
    resolver = staticmethod(refs.resolve_translation_language)


class GenreField(RefField):
    resolver = staticmethod(refs.resolve_genre)


class TrackListField(fields.Field):
    """Comma-separated track refs (ids, vanity ids, ISRCs, Spotify ids or
    links), trimmed and deduplicated, at most BATCH_MAX."""

    def _deserialize(self, value, attr, data, **kwargs):
        items = [part.strip() for part in str(value).split(",") if part.strip()]
        if not items:
            raise ValidationError("Must list at least one track.")
        if len(items) > BATCH_MAX:
            raise ValidationError(f"At most {BATCH_MAX} tracks per call.")
        out, seen = [], set()
        for item in items:
            try:
                ref = refs.resolve_track(item)
            except ValueError as e:
                raise ValidationError(f"{item!r}: {e}")
            key = (ref["kind"], ref["value"])
            if key not in seen:
                seen.add(key)
                out.append(ref)
        return out


def _page():
    return PageField(max_page=MAX_PAGE)


def _page_size(default=20):
    return PageSizeField(default=default, max_size=100)


def _text(max_length=200):
    return QueryField(required=False, load_default=None, max_length=max_length)


# ---- search --------------------------------------------------------------------------------

class SearchTracksSchema(BaseSchema):
    query = _text()
    title = _text()
    artist = _text()
    lyrics = _text(max_length=500)
    writer = _text()
    genre = GenreField(required=False, load_default=None)
    language = LanguageField(required=False, load_default=None)
    has_lyrics = Flag()
    instrumental = ChoiceField(["only", "exclude"])
    sort = ChoiceField(list(refs.TRACK_SORTS))
    page = _page()
    page_size = _page_size()

    @validates_schema
    def _needs_a_term(self, data, **kwargs):
        if not any(data.get(k) for k in ("query", "title", "artist", "lyrics", "writer", "genre", "language")):
            raise ValidationError("Pass at least one of query, title, artist, lyrics, writer, genre or language.",
                                  "query")


class SearchArtistsSchema(BaseSchema):
    query = QueryField()
    page = _page()
    page_size = _page_size()


# ---- tracks -------------------------------------------------------------------------------

class TrackSchema(BaseSchema):
    track = TrackRefField()


class TrackBatchSchema(BaseSchema):
    tracks = TrackListField(required=True)


class TrackTranslationSchema(TrackSchema):
    language = TranslationLanguageField()


# ---- artists ------------------------------------------------------------------------------

class ArtistSchema(BaseSchema):
    artist = ArtistRefField()


class ArtistAlbumsSchema(ArtistSchema):
    type = ChoiceField(list(refs.ALBUM_TYPES))
    sort = ChoiceField(list(refs.ALBUM_SORTS), load_default="newest")
    group_editions = Flag(load_default=True)
    page = _page()
    page_size = _page_size()


class ArtistTracksSchema(ArtistSchema):
    sort = ChoiceField(["popularity", "newest", "oldest"], load_default="popularity")
    has_lyrics = Flag()
    page = _page()
    page_size = _page_size()


# ---- albums / creators ----------------------------------------------------------------------

class AlbumSchema(BaseSchema):
    album = AlbumRefField()


class CreatorSchema(BaseSchema):
    creator = CreatorRefField()


# ---- charts / discover / reference --------------------------------------------------------

class ChartTracksSchema(BaseSchema):
    country = CountryCodeField(load_default="US")
    chart = ChoiceField(list(refs.CHART_NAMES), load_default="top")
    has_lyrics = Flag()
    page = PageField(max_page=10)
    page_size = _page_size()


class ChartArtistsSchema(BaseSchema):
    country = CountryCodeField(load_default="US")
    page = PageField(max_page=10)
    page_size = _page_size()


class TranslationLanguageSchema(BaseSchema):
    language = TranslationLanguageField()


class EmptySchema(BaseSchema):
    pass

