"""Fetch and parse Avengers: Doomsday shows from District (district.in).

District server-renders each movie page with a Next.js `__NEXT_DATA__` JSON
blob containing every cinema and session for one language/format group and
one date. We read that public page the same way a browser does: plain GETs,
a few seconds apart. If District ever answers with a bot challenge instead of
data, we raise `BlockedError` and stop -- we never try to get around it.
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class BlockedError(Exception):
    """District returned something other than the normal page (blocked / changed)."""


@dataclass(frozen=True)
class Show:
    cinema_id: str
    cinema_name: str
    session_id: str
    show_time: str  # local IST, e.g. "2026-12-17T07:35"
    fmt: str
    language: str
    avail: int
    total: int
    booking_url: str

    @property
    def key(self) -> str:
        return f"{self.cinema_id}:{self.session_id}"

    @property
    def date(self) -> str:
        return self.show_time[:10]

    @property
    def hour(self) -> int:
        return int(self.show_time[11:13])

    def to_dict(self) -> dict:
        return asdict(self)


def fetch(url: str, timeout: int = 20, retries: int = 2) -> str:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise BlockedError(f"HTTP {e.code} from {url}") from e
            last = e
        except Exception as e:  # network hiccup
            last = e
        time.sleep(3 * (attempt + 1))
    raise BlockedError(f"Failed to fetch {url}: {last!r}")


def parse_next_data(html: str) -> dict:
    m = NEXT_DATA_RE.search(html)
    if not m:
        hint = "bot challenge" if re.search(r"just a moment|captcha|challenge", html, re.I) else "page changed"
        raise BlockedError(f"No __NEXT_DATA__ in page ({hint})")
    try:
        return json.loads(m.group(1))["props"]["pageProps"]["data"]["serverState"]
    except (KeyError, json.JSONDecodeError) as e:
        raise BlockedError(f"Unexpected page structure: {e!r}") from e


def format_groups(server_state: dict) -> tuple[list[dict], list[str]]:
    """Return (language/format groups, available session dates)."""
    contents = next(iter(server_state.get("movieContents", {}).values()), {})
    groups = contents.get("languageFormatGroups") or []
    dates: list[str] = []
    for ms in server_state.get("movieSessions", {}).values():
        dates = (ms.get("data") or {}).get("sessionDates") or []
        if dates:
            break
    return groups, dates


def parse_shows(server_state: dict, language: str, content_id: str) -> list[Show]:
    shows: list[Show] = []
    for ms in server_state.get("movieSessions", {}).values():
        for cinema in ms.get("arrangedSessions") or []:
            cname = cinema.get("entityName") or (cinema.get("data") or {}).get("name", "?")
            cid = str(cinema.get("entityCode") or (cinema.get("data") or {}).get("id", "?"))
            for s in cinema.get("sessions") or []:
                url = (f"https://www.district.in/movies/seat-layout/{s.get('mcd', '')}"
                       f"?encsessionid={s.get('encSessionId', '')}&freeseating=false"
                       f"&fromsessions=true&type=MOVIES&contentid={content_id}")
                shows.append(Show(
                    cinema_id=cid,
                    cinema_name=cname,
                    session_id=str(s.get("sid")),
                    show_time=s.get("showTime", ""),
                    fmt=s.get("scrnFmt") or "",
                    language=language,
                    avail=int(s.get("avail") or 0),
                    total=int(s.get("total") or 0),
                    booking_url=url,
                ))
    return shows


def fetch_all_shows(movie_url: str, content_id: str, languages: list[str],
                    dates: list[str], delay: float = 2.0) -> list[Show]:
    """All shows for the wanted languages on the wanted dates (one page per group x date)."""
    base = parse_next_data(fetch(movie_url))
    groups, available = format_groups(base)
    wanted_langs = {l.lower() for l in languages}
    wanted_dates = [d for d in dates if d in available]
    out: dict[str, Show] = {}
    for g in groups:
        lang = g.get("language") or g.get("lang") or ""
        if lang.lower() not in wanted_langs:
            continue
        fmt_id = (g.get("fmtGrpId") or g.get("format") or "").lower()
        for d in wanted_dates:
            time.sleep(delay)
            state = parse_next_data(fetch(f"{movie_url}?frmtid={fmt_id}&fromdate={d}"))
            for show in parse_shows(state, lang, content_id):
                if show.date == d:
                    out[show.key] = show
    return list(out.values())
