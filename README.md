# 🎤 Musixmatch Scraper

Musixmatch Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Musixmatch lyrics and music data for free.

## ✨ What Can I Get?

- 🎤 **Full lyrics for 10M+ songs** — every line, stanzas, language, key line, writers & copyright
- 🌍 **Line-by-line translations in 88 languages** — Spanish, French, Japanese, Chinese & more, in song order
- 🧠 **What every song means** — AI meaning, moods, themes with quotes, and a content rating
- ✍️ **Credits, charts & catalogs** — songwriters, producers, top charts by country, artists, albums & ISRCs

## 🎥 Example: Full Lyrics for a Hit Song

```json
{
  "track": {
    "id": 248463510,
    "name": "Anti-Hero",
    "link": "https://www.musixmatch.com/lyrics/Taylor-Swift/Anti-Hero",
    "artist": { "id": 259675, "name": "Taylor Swift", "link": "https://www.musixmatch.com/artist/Taylor-Swift" },
    "album": { "id": 54683517, "name": "Midnights", "link": "https://www.musixmatch.com/album/Taylor-Swift/Midnights" }
  },
  "has_lyrics": true,
  "lyrics": {
    "language": { "code": "en", "name": "English" },
    "lines": [
      "I have this thing where I get older but just never wiser",
      "Midnights become my afternoons",
      "When my depression works the graveyard shift"
    ],
    "line_count": 52,
    "snippet": "I'm the problem, it's me",
    "copyright": "Writer(s): Taylor Swift, Jack Michael Antonoff",
    "writers": [
      { "id": 2405, "name": "Taylor Swift", "role": null },
      { "id": 231604, "name": "Jack Michael Antonoff", "role": null }
    ],
    "is_explicit": true,
    "is_restricted": false
  }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Musixmatch Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/musixmatch-scraper
cd musixmatch-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/tracks/lyrics?track=Taylor-Swift/Anti-Hero"
```

```json
{
  "track": {
    "id": 248463510,
    "common_id": 153776734,
    "name": "Anti-Hero",
    "link": "https://www.musixmatch.com/lyrics/Taylor-Swift/Anti-Hero",
    "artist": { "id": 259675, "name": "Taylor Swift", "link": "https://www.musixmatch.com/artist/Taylor-Swift" },
    "album": { "id": 54683517, "name": "Midnights", "link": "https://www.musixmatch.com/album/Taylor-Swift/Midnights" }
  },
  "has_lyrics": true,
  "lyrics": {
    "language": { "code": "en", "name": "English" },
    "line_count": 52,
    "snippet": "I'm the problem, it's me",
    "copyright": "Writer(s): Taylor Swift, Jack Michael Antonoff",
    "is_explicit": true
  }
}
```

All 26 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

26 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Track Lyrics | `/tracks/lyrics` | Full lyrics with lines, stanzas, writers and copyright |
| Search Tracks / Artists | `/search/tracks`, `/search/artists` | Songs by keywords, lyric phrase, songwriter or genre; artists by name |
| Track Details | `/tracks/details` | Album, cover art, release date, genres, ISRCs, Spotify IDs |
| Track Translation | `/tracks/translation` | Lyrics translated line by line into 88 languages |
| Track Meaning & Moods | `/tracks/analysis` | What the song means, its moods and themes |
| Track Credits / Writers | `/tracks/credits`, `/tracks/writers` | Every songwriter, producer and musician with their roles |
| Track Structure | `/tracks/structure` | Verses, choruses and bridges in order |
| Track Contributions | `/tracks/contributions` | Who transcribed and verified the lyrics |
| Tracks Batch | `/tracks/batch` | Up to 20 tracks in one call |
| Artist Details | `/artists/details` | Photo, country, genres, socials and external IDs |
| Artist Albums / Tracks | `/artists/albums`, `/artists/tracks` | Full discography and most popular songs |
| Artist Collaborators / Lyric Videos | `/artists/collaborators`, `/artists/lyric-videos` | Credited songwriters and official YouTube lyric videos |
| Album Details | `/albums/details` | Full tracklist, label and copyright |
| Songwriter Details / Credits | `/creators/details`, `/creators/credits` | Songwriter bios and every song they're credited on |
| Top Tracks / Artists Charts | `/charts/tracks`, `/charts/artists` | Top, trending and weekly charts for any country |
| Featured Music | `/discover/featured` | Trending songs, weekly tops, top albums and artists |
| Recently Translated Songs | `/discover/translated` | Songs just translated into a language |
| Genres / Languages / Countries | `/genres/list`, `/languages/list`, `/countries/list` | Every genre, language and chart country code |


## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-musixmatch-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-musixmatch-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-musixmatch-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/tracks/lyrics",
    params={"track": "Taylor-Swift/Anti-Hero"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Musixmatch Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Musixmatch%20Scraper%20API.)

[![Ask Us by Email about Musixmatch Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Musixmatch%20Scraper%20API&body=I%20need%20help%20using%20the%20Musixmatch%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/musixmatch-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/musixmatch-scraper)
