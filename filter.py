"""Filter the Forex Factory weekly calendar to USD, medium + high impact.

Apple Calendar colors whole calendars, not single events, so red and orange
news go into separate feeds:
  ff_usd_high.ics    red (high impact)
  ff_usd_medium.ics  orange (medium impact)
  ff_usd_eur.ics     both, in one calendar (old link, kept so it keeps working)
Each event's description gets a rule-of-thumb note on what it means for gold.
Each file is only rewritten when its events actually change.
"""

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCE = "https://nfs.faireconomy.media/ff_calendar_thisweek.ics"
DIR = Path(__file__).parent

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
X-WR-CALDESC:Forex Factory USD events
X-APPLE-CALENDAR-COLOR:{color}
COLOR:{color}
REFRESH-INTERVAL;VALUE=DURATION:PT1H
X-PUBLISHED-TTL:PT1H
{VTIMEZONE}"""


def fetch() -> str:
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "ff-news-calendar"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8").replace("\r\n", "\n")


def gold_note(title: str, desc: str) -> str:
    """Rule-of-thumb XAUUSD reading for a USD release (not a prediction)."""
    ref = "forecast" if "Forecast:" in desc else "previous" if "Previous:" in desc else None
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


def annotate(block: str) -> str:
    """Add the gold note to the event's DESCRIPTION."""
    lines = block.replace("\n ", "").splitlines()
    title = next(l for l in lines if l.startswith("SUMMARY:"))
    body = []
    for l in lines:
        if l.startswith("DESCRIPTION:"):
            note = gold_note(title, l)
            l = l.replace("\\n\\nView Event:", f"\\n\\n{note}\\n\\nView Event:", 1)
        body.append(fold(l))
    return "".join(body)


def parse(text: str) -> list[tuple[str, str]]:
    """Return (impact marker, annotated event block) for every USD event."""
    if "BEGIN:VCALENDAR" not in text:
        sys.exit("Upstream did not return a calendar; keeping the old files.")
    events = []
    for block in re.findall(r"BEGIN:VEVENT\n.*?END:VEVENT\n", text, re.S):
        m = re.search(r"^SUMMARY:(\S+)\s+([A-Z]{2})\s", block.replace("\n ", ""), re.M)
        if m and m[2] in KEEP:
            events.append((m[1], annotate(block)))
    return events


def strip_stamps(s: str) -> str:
    return re.sub(r"DTSTAMP:\S+", "", s)


def main() -> None:
    try:
        text = fetch()
    except urllib.error.HTTPError as e:
        if e.code == 429:  # rate limited; try again next run
            print("Rate limited by upstream; keeping the old files.")
            return
        raise
    events = parse(text)
    for name, (impacts, calname, color) in FEEDS.items():
        kept = [block for impact, block in events if impact in impacts]
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
