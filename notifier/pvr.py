"""Fetch and parse shows from the shared PVR Cinemas & INOX Movies public API.

Both pvrcinemas.com and inoxmovies.com read from `api3.pvrcinemas.com/api/`.
`msessions` returns all PVR and INOX venues in a city for one movie and date.
Showtimes are already in IST; exact seat counts are not exposed there, so
status 1/2 ("Available" / "Filling Up Fast") maps to avail=1, and 0/3
("Lapsed" / "Housefull") maps to avail=0.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime

from .models import BlockedError, Show

API_BASE = "https://api3.pvrcinemas.com/api/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")


def post_json(endpoint: str, body: dict, city: str, timeout: int = 20, retries: int = 2) -> dict:
    headers = {
        "User-Agent": UA,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": "Bearer ",
        "chain": "PVR",
        "city": city,
        "appVersion": "1.0",
        "platform": "WEBSITE",
        "country": "INDIA",
        "Origin": "https://www.pvrcinemas.com",
        "Referer": "https://www.pvrcinemas.com/",
    }
    data = json.dumps(body).encode()
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(API_BASE + endpoint, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise BlockedError(f"HTTP {e.code} from PVR API ({endpoint})") from e
            last = e
        except Exception as e:
            last = e
        time.sleep(3 * (attempt + 1))
    raise BlockedError(f"Failed PVR API ({endpoint}): {last!r}")


def find_movie_ids(city: str, name_regex: str, fallback_ids: list[str]) -> list[str]:
    """Find matching movie IDs in `search` (in case IMAX/4DX gets a separate ID)."""
    try:
        res = post_json("v1/booking/content/search",
                        {"city": city, "lat": "0.000", "lng": "0.000", "type": "HOME"}, city)
        ns = (res.get("output") or {}).get("ns") or []
        ids = [str(m["id"]) for m in ns
               if m.get("id") and re.search(name_regex, m.get("n") or m.get("filmName") or "", re.I)]
        return list(dict.fromkeys(ids + fallback_ids))
    except BlockedError:
        raise
    except Exception:
        return fallback_ids


def parse_msessions(payload: dict, languages: list[str], dates: set[str]) -> list[Show]:
    if payload.get("code") == 12001:  # "No Record Found" — no shows yet for this date
        return []
    if payload.get("result") != "success":
        raise BlockedError(f"PVR API error: {payload.get('msg') or payload.get('code')}")
    wanted_langs = {l.lower() for l in languages}
    shows: list[Show] = []
    out = payload.get("output") or {}
    for mc in out.get("movieCinemaSessions") or []:
        cinema = mc.get("cinema") or {}
        cid = str(cinema.get("theatreId") or "?")
        cname = cinema.get("name") or "?"
        for exp in mc.get("experienceSessions") or []:
            exp_name = (exp.get("experience") or "").strip()
            for s in exp.get("shows") or []:
                lang = (s.get("language") or "").strip()
                if lang.lower() not in wanted_langs:
                    continue
                date_str = s.get("showDateStr") or s.get("showDate") or ""
                time_str = s.get("showTime") or ""
                if not date_str or not time_str:
                    continue
                try:
                    dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M %p")
                except ValueError:
                    continue
                ist_time = dt.strftime("%Y-%m-%dT%H:%M")
                if ist_time[:10] not in dates:
                    continue
                fmt = (s.get("filmFormat") or s.get("movieFormat") or "").strip()
                screen_type = (s.get("screenType") or exp_name).strip()
                if screen_type and screen_type.lower() not in fmt.lower():
                    fmt = f"{fmt} · {screen_type}" if fmt else screen_type
                status = s.get("status")
                avail = 1 if status in (1, 2) else 0
                enc = s.get("encrypted") or ""
                url = (f"https://www.pvrcinemas.com/seatlayout/{enc}"
                       if enc else "https://www.pvrcinemas.com/")
                shows.append(Show(
                    cinema_id=cid,
                    cinema_name=cname,
                    session_id=str(s.get("sessionId")),
                    show_time=ist_time,
                    fmt=fmt,
                    language=lang,
                    avail=avail,
                    total=0,
                    booking_url=url,
                    source="PVR/INOX",
                ))
    return shows


def fetch_all_shows(city: str, movie_id: str, name_regex: str, languages: list[str],
                    dates: list[str], delay: float = 1.5) -> list[Show]:
    mids = find_movie_ids(city, name_regex, [movie_id] if movie_id else [])
    wanted_dates = set(dates)
    out: dict[str, Show] = {}
    for mid in mids:
        for d in dates:
            time.sleep(delay)
            payload = post_json("v1/booking/content/msessions", {
                "city": city, "mid": mid, "dated": d, "lat": "0.000", "lng": "0.000",
            }, city)
            for show in parse_msessions(payload, languages, wanted_dates):
                out[show.key] = show
    return list(out.values())
