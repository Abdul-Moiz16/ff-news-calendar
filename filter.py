"""Filter the Forex Factory weekly calendar to USD, medium + high impact.

Apple Calendar colors whole calendars, not single events, so red and orange
news go into separate feeds:
  ff_usd_high.ics    red (high impact)
  ff_usd_medium.ics  orange (medium impact)
  ff_usd_eur.ics     both, in one calendar (old link, kept so it keeps working)

Forex Factory's feed has no actual results, so actuals come from biquote.io's
free calendar API, matched to each event by release time and name. Once an
actual is out, the description shows it and whether it reads bullish or
bearish for gold (XAUUSD). Before release it shows how to read the number.

Each file is only rewritten when its events actually change.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

FF_SOURCE = "https://nfs.faireconomy.media/ff_calendar_thisweek.ics"
ACTUALS_API = "https://biquote.io/api/calendar?countries=US&from={start}&to={end}"
USER_AGENT = "ff-news-calendar (github.com/Abdul-Moiz16/ff-news-calendar)"
DIR = Path(__file__).parent
CACHE = DIR / "cache" / "ff_thisweek.ics"  # last good Forex Factory feed
NY = ZoneInfo("America/New_York")

KEEP = {"US"}  # USD only
HIGH, MEDIUM = "⁂", "⁑"  # Forex Factory impact markers

# file name -> (impacts, calendar name, Apple calendar color)
FEEDS = {
    "ff_usd_high.ics": ({HIGH}, "FF USD High Impact", "#E5262C"),
    "ff_usd_medium.ics": ({MEDIUM}, "FF USD Medium Impact", "#FF9500"),
    "ff_usd_eur.ics": ({HIGH, MEDIUM}, "FF News USD", "#E5262C"),
}

# Releases where a LOWER number is good for USD (so the gold reading flips).
LOWER_IS_BETTER = ("unemployment claims", "unemployment rate", "jobless", "continuing claims")

# Forex Factory wording -> biquote wording, applied before name matching.
ALIASES = {
    "philly": "philadelphia",
    "uom": "michigan",
    "unemployment claims": "initial jobless claims",
    "fed chairman": "fed chair",
}
SUFFIX = {"thousands": "K", "millions": "M", "billions": "B"}

# Forex Factory uses TZID=America/New_York but ships no VTIMEZONE block.
VTIMEZONE = """BEGIN:VTIMEZONE
TZID:America/New_York
BEGIN:DAYLIGHT
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
TZNAME:EDT
DTSTART:20070311T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
END:DAYLIGHT
BEGIN:STANDARD
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
TZNAME:EST
DTSTART:20071104T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
END:STANDARD
END:VTIMEZONE
"""


def header(name: str, color: str) -> str:
    return f"""BEGIN:VCALENDAR
PRODID:-//ff-news-calendar//EN
VERSION:2.0
CALSCALE:GREGORIAN
X-WR-CALNAME:{name}
X-WR-CALDESC:Forex Factory USD events. Actuals from biquote.io
X-APPLE-CALENDAR-COLOR:{color}
COLOR:{color}
REFRESH-INTERVAL;VALUE=DURATION:PT5M
X-PUBLISHED-TTL:PT5M
{VTIMEZONE}"""


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read()


def fetch_ff() -> str:
    """Fetch the Forex Factory feed, falling back to the last good copy."""
    try:
        text = get(FF_SOURCE).decode("utf-8").replace("\r\n", "\n")
        if "BEGIN:VCALENDAR" not in text:
            raise ValueError("not a calendar")
    except (urllib.error.URLError, ValueError) as e:
        if not CACHE.exists():
            sys.exit(f"Forex Factory feed unavailable ({e}) and no cached copy.")
        print(f"Forex Factory feed unavailable ({e}); using cached copy.")
        return CACHE.read_text(encoding="utf-8")
    old = CACHE.read_text(encoding="utf-8") if CACHE.exists() else ""
    if strip_stamps(old) != strip_stamps(text):  # avoid a commit on every run
        CACHE.parent.mkdir(exist_ok=True)
        CACHE.write_text(text, encoding="utf-8")
    return text


def fetch_actuals(start: datetime, end: datetime) -> list[dict]:
    """Released US figures from biquote; empty if the API is unavailable."""
    url = ACTUALS_API.format(start=start.date(), end=(end + timedelta(days=1)).date())
    try:
        rows = json.loads(get(url))
    except (urllib.error.URLError, ValueError) as e:
        print(f"Actuals unavailable ({e}); publishing without them.")
        return []
    for r in rows:
        r["when"] = datetime.fromisoformat(r["time"].replace("Z", "+00:00"))
    return [r for r in rows if r.get("actual") is not None]


def words(name: str) -> set[str]:
    name = name.lower()
    for old, new in ALIASES.items():
        name = name.replace(old, new)
    return set(re.findall(r"[a-z0-9/]+", name)) - {"prelim", "revised", "flash", "final", "speaks"}


def match(title: str, when: datetime, actuals: list[dict]) -> dict | None:
    """The biquote release at the same time whose name best fits the FF title."""
    best, best_score = None, 0.4  # minimum name overlap to accept a match
    ff = words(title)
    for r in actuals:
        if abs(r["when"] - when) > timedelta(minutes=10):
            continue
        bq = words(r["name"])
        score = len(ff & bq) / len(ff | bq)
        if score > best_score:
            best, best_score = r, score
    return best


def parse_value(s: str) -> tuple[float, str] | None:
    """'198K' -> (198.0, 'K'), '0.4%' -> (0.4, '%'), '' -> None."""
    m = re.fullmatch(r"\s*(-?[\d.]+)\s*([%KMBT]?)\s*", s or "")
    return (float(m[1]), m[2]) if m else None


def fmt(r: dict, key: str) -> tuple[float, str] | None:
    v = r.get(key)
    if v is None:
        return None
    return float(v), "%" if r.get("unit") == "percent" else SUFFIX.get(r.get("multiplier"), "")


def show(v: tuple[float, str]) -> str:
    return f"{v[0]:g}{v[1]}"


def verdict(title: str, actual: tuple[float, str], refs: list[tuple[str, tuple | None]]) -> tuple[str, str]:
    """Compare the actual with the first usable reference; return (note, title tag)."""
    for label, ref in refs:
        if ref is None or ref[1] != actual[1]:
            continue  # missing, or not on the same scale
        diff = actual[0] - ref[0]
        if diff == 0:
            return (f"RESULT: actual {show(actual)} = {label} {show(ref)}, in line. "
                    "XAUUSD: little reaction expected (neutral).", "in line")
        lower_good = any(k in title.lower() for k in LOWER_IS_BETTER)
        usd_good = (diff < 0) if lower_good else (diff > 0)
        side = "above" if diff > 0 else "below"
        if usd_good:
            return (f"RESULT: actual {show(actual)} {side} {label} {show(ref)} -> good for USD "
                    "-> XAUUSD BEARISH.", "gold bearish")
        return (f"RESULT: actual {show(actual)} {side} {label} {show(ref)} -> bad for USD "
                "-> XAUUSD BULLISH.", "gold bullish")
    return f"RESULT: actual {show(actual)} (nothing comparable to judge it against).", ""


def gold_rule(title: str, ref: str | None) -> str:
    """Rule-of-thumb XAUUSD reading before the release (not a prediction)."""
    if ref is None:
        return ("XAUUSD: no number to compare. Hawkish tone (rates higher for longer) "
                "-> USD up, gold bearish. Dovish tone -> gold bullish.")
    good, bad = ("BELOW", "ABOVE") if any(k in title.lower() for k in LOWER_IS_BETTER) else ("ABOVE", "BELOW")
    return (f"XAUUSD: actual {good} {ref} -> USD stronger, gold bearish. "
            f"Actual {bad} {ref} -> USD weaker, gold bullish.")


def fold(line: str) -> str:
    """Fold an iCalendar content line to 75 octets."""
    out, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not out else 74):
            out.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    out.append(cur.decode("utf-8"))
    return "\n ".join(out) + "\n"


def prop(lines: list[str], name: str) -> str:
    return next((l.split(":", 1)[1] for l in lines if l.split(":", 1)[0].split(";")[0] == name), "")


def build_event(block: str, actuals: list[dict]) -> str:
    lines = block.replace("\n ", "").splitlines()
    summary = prop(lines, "SUMMARY")
    title = summary.split(" ", 2)[2]  # drop impact marker and country code
    desc = prop(lines, "DESCRIPTION").split("\\n\\n")
    field = {k: v for k, _, v in (p.partition(": ") for p in desc)}
    forecast, previous = field.get("Forecast", ""), field.get("Previous", "")
    when = datetime.strptime(prop(lines, "DTSTART"), "%Y%m%dT%H%M%S").replace(tzinfo=NY)

    parts = [f"Impact: {field.get('Impact', '')}"]
    tag = ""
    hit = match(title, when.astimezone(timezone.utc), actuals)
    if hit:
        actual = fmt(hit, "actual")
        parts.append(f"Actual: {show(actual)}")
    if forecast:
        parts.append(f"Forecast: {forecast}")
    elif hit and fmt(hit, "forecast"):
        parts.append(f"Forecast: {show(fmt(hit, 'forecast'))} (biquote)")
    if previous:
        parts.append(f"Previous: {previous}")
    if hit:
        note, tag = verdict(title, actual, [
            ("forecast", parse_value(forecast)),
            ("forecast", fmt(hit, "forecast")),
            ("previous", parse_value(previous)),
            ("previous", fmt(hit, "previous")),
        ])
        parts.append(note)
    else:
        parts.append(gold_rule(title, "forecast" if forecast else "previous" if previous else None))
    if "View Event" in field:
        parts.append(f"View Event: {field['View Event']}")
    if hit:
        parts.append("Actual from biquote.io")

    out = []
    for l in lines:
        key = l.split(":", 1)[0].split(";")[0]
        if key == "SUMMARY" and tag:
            l = f"SUMMARY:{summary} | {tag}"
        elif key == "DESCRIPTION":
            l = "DESCRIPTION:" + "\\n\\n".join(parts)
        elif key == "END" and l == "END:VEVENT" and hit:
            out.append("SEQUENCE:1\n")  # nudge clients to pick up the update
        out.append(fold(l))
    return "".join(out)


def parse(text: str) -> list[tuple[str, str, str]]:
    """Return (impact marker, raw event block) for every USD event."""
    events = []
    for block in re.findall(r"BEGIN:VEVENT\n.*?END:VEVENT\n", text, re.S):
        m = re.search(r"^SUMMARY:(\S+)\s+([A-Z]{2})\s", block.replace("\n ", ""), re.M)
        if m and m[2] in KEEP:
            events.append((m[1], block))
    return events


def start_times(events: list[tuple[str, str]]) -> list[datetime]:
    stamps = [re.search(r"DTSTART;TZID=America/New_York:(\S+)", b)[1] for _, b in events]
    return [datetime.strptime(s, "%Y%m%dT%H%M%S").replace(tzinfo=NY) for s in stamps]


def strip_stamps(s: str) -> str:
    return re.sub(r"DTSTAMP:\S+", "", s)


def main() -> None:
    events = [(i, b) for i, b in parse(fetch_ff()) if i in (HIGH, MEDIUM)]
    times = start_times(events) or [datetime.now(NY)]
    actuals = fetch_actuals(min(times), max(times))
    built = [(i, build_event(b, actuals)) for i, b in events]
    print(f"{sum('Actual:' in b for _, b in built)} of {len(built)} events have actuals.")

    for name, (impacts, calname, color) in FEEDS.items():
        kept = [b for i, b in built if i in impacts]
        body = (header(calname, color) + "".join(kept) + "END:VCALENDAR\n").replace("\n", "\r\n")
        out = DIR / name
        old = out.open(encoding="utf-8", newline="").read() if out.exists() else ""
        if strip_stamps(old) == strip_stamps(body):
            print(f"{name}: no change ({len(kept)} events).")
            continue
        with out.open("w", encoding="utf-8", newline="") as f:
            f.write(body)
        print(f"{name}: updated, {len(kept)} events.")


if __name__ == "__main__":
    main()
