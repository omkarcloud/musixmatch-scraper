"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json.
"""
import json
import os

from musixmatch import refs
from musixmatch.search import search_tracks
from musixmatch.tracks import get_lyrics, get_translation

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a track ID, an Artist/Track name, a musixmatch.com link, an ISRC or a Spotify ID/link
    save("lyrics_anti_hero.json", get_lyrics(refs.resolve_track("Taylor-Swift/Anti-Hero")))

    # keywords, title, artist, lyric phrase, songwriter, genre or language
    save("search_blinding_lights.json", search_tracks(query="blinding lights"))

    # line-by-line translation into any of 88 languages
    save("translation_anti_hero_es.json",
         get_translation(refs.resolve_track("Taylor-Swift/Anti-Hero"), refs.resolve_translation_language("es")))
