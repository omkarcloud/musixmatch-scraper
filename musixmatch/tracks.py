"""/musixmatch/tracks/* — one track, by any of its ids.

API-backed (signed /ws/1.1): details (track.get), batch (tracks.get),
lyrics (track.lyrics.get + track.snippet.get), writers (track.writers.get),
structure (crowd.track.metadata.get). Every track method accepts track_id,
commontrack_vanity_id, track_isrc or track_spotify_id (validated
2026-09-19), so the ref goes straight upstream.

Page-backed (the lyrics page's __NEXT_DATA__, addressed by vanity id):
credits (roles + categories), analysis (Musixmatch's AI "lens": meaning,
moods, themes, content rating), contributions (community edit history +
the credited transcriber) and translation (/translation/<language>, the
crowd translation mapped back onto the lyrics in song order). The
equivalent API methods (crowd.track.translations.get, ...) are the ones the
WAF gates behind a browser token, so the pages are the curl-only route.
"""
from musixmatch import fetch, lookup, parsers, refs

BATCH_MAX = 20


def _track_summary_api(track_ref):
    return parsers.track_summary(parsers.track_from_api(lookup.track_object(track_ref)))


def get_details(track):
    return {"track": parsers.track_from_api(lookup.track_object(track))}


def get_batch(tracks):
    """Up to 20 refs of mixed kinds -> tracks in the order asked. Track ids
    and ISRCs go through one tracks.get call each; vanity ids and Spotify
    ids (which tracks.get does not take) through parallel track.get calls."""
    found = {}

    def by_list(kind, param):
        values = [r["value"] for r in tracks if r["kind"] == kind]
        if not values:
            return
        try:
            body = fetch.api_body("tracks.get", {param: ",".join(str(v) for v in dict.fromkeys(values))})
        except fetch.MusixmatchNotFound:
            return   # none of these ids exist: they are reported in not_found, not a 404 for the batch
        for t in parsers._items(body.get("track_list"), "track"):
            if kind == "track_id":
                found[("track_id", parsers.positive(t.get("track_id")))] = t
            else:
                # an ISRC may be the track's own or any version's of the song
                isrcs = {str(t.get("track_isrc") or "").upper()}
                isrcs.update(str(i).upper() for i in parsers._flatten(t.get("commontrack_isrcs")))
                for isrc in values:
                    if isrc in isrcs and ("isrc", isrc) not in found:
                        found[("isrc", isrc)] = t

    singles = [r for r in tracks if r["kind"] in ("vanity", "spotify_id")]
    calls = [lambda: by_list("track_id", "track_ids"), lambda: by_list("isrc", "track_isrcs")]
    calls += [fetch.optional(lambda r=r: found.__setitem__((r["kind"], r["value"]), lookup.track_object(r)))
              for r in singles]
    fetch.run_parallel(calls)

    out, missing = [], []
    for r in tracks:
        raw = found.get((r["kind"], r["value"]))
        if raw:
            out.append(parsers.track_from_api(raw))
        else:
            missing.append(str(r["value"]))
    return {"count": len(out), "tracks": out, "not_found": missing}


def get_lyrics(track):
    track_raw, lyrics_body, snippet_body = fetch.run_parallel([
        lambda: lookup.track_object(track),
        fetch.optional(lambda: fetch.api_body("track.lyrics.get", refs.track_api_params(track))),
        fetch.optional(lambda: fetch.api_body("track.snippet.get", refs.track_api_params(track))),
    ])
    parsed = parsers.track_from_api(track_raw)
    raw_lyrics = (lyrics_body or {}).get("lyrics")
    return {
        "track": parsers.track_summary(parsed),
        "has_lyrics": bool(raw_lyrics and raw_lyrics.get("lyrics_body")),
        "lyrics": parsers.lyrics(raw_lyrics, (snippet_body or {}).get("snippet")) if raw_lyrics else None,
    }


def get_writers(track):
    summary, body = fetch.run_parallel([
        lambda: _track_summary_api(track),
        fetch.optional(lambda: fetch.api_body("track.writers.get", refs.track_api_params(track))),
    ])
    writers = parsers.writers((body or {}).get("writer_list"))
    return {"track": summary, "count": len(writers), "writers": writers}


def get_structure(track):
    summary, body = fetch.run_parallel([
        lambda: _track_summary_api(track),
        fetch.optional(lambda: fetch.api_body("crowd.track.metadata.get", refs.track_api_params(track))),
    ])
    sections = parsers.structure((body or {}).get("metadata"))
    return {"track": summary, "count": len(sections), "sections": sections}


# ---- lyrics-page routes ------------------------------------------------------------------

def _page_track(page_data):
    track, lyrics, info = lookup.track_info(page_data)
    return parsers.track_from_page(track), lyrics, info


def get_credits(track):
    data = lookup.lyrics_page(track)["data"]
    parsed, _, _ = _page_track(data)
    credits = [parsers.credit(c) for c in fetch.section(data, "creditsTrackCollaboratorsGet") or []
               if isinstance(c, dict)]
    return {"track": parsers.track_summary(parsed), "count": len(credits), "credits": credits}


def get_analysis(track):
    data = lookup.lyrics_page(track)["data"]
    raw_track, _, _ = lookup.track_info(data)
    lens = raw_track.get("lens") if isinstance(raw_track.get("lens"), dict) else None
    analysis = parsers.lens(lens)
    return {
        "track": parsers.track_summary(parsers.track_from_page(raw_track)),
        "is_available": bool(lens and (analysis["meaning"] or analysis["moods"] or analysis["themes"])),
        **analysis,
    }


def get_contributions(track):
    data = lookup.lyrics_page(track)["data"]
    parsed, lyrics, _ = _page_track(data)
    history = [parsers.contribution(h) for h in fetch.section(data, "crowdTrackHistoryGet") or []
               if isinstance(h, dict)]
    return {
        "track": parsers.track_summary(parsed),
        "lyrics_verified_by": parsers.text(lyrics.get("verifier")),
        "transcriber": parsers.transcriber(lyrics.get("lyricsUser")),
        "count": len(history),
        "contributions": history,
    }


def get_translation(track, language):
    data = lookup.lyrics_page(track, "/translation/" + refs.language_slug(language))["data"]
    parsed, lyrics, _ = _page_track(data)
    mapping = fetch.section(data, "crowdTranslationGet")
    lines = parsers.translation_lines(lyrics.get("body"), mapping if isinstance(mapping, dict) else {})
    translated = [line for line in lines if line["translated"]]
    return {
        "track": parsers.track_summary(parsed),
        "language": {"code": language["code"], "name": refs.display_language_name(language["name"])},
        "original_language": refs.language_record(parsers.text(lyrics.get("language"))),
        "is_available": bool(translated),
        "line_count": len(lines),
        "translated_line_count": len(translated),
        "lines": lines if translated else [],
    }
