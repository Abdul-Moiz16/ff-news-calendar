"""Filter the Forex Factory weekly calendar to USD + EUR, medium + high impact.

Apple Calendar colors whole calendars, not single events, so red and orange
news go into separate feeds:
  ff_usd_eur_high.ics    red (high impact)
  ff_usd_eur_medium.ics  orange (medium impact)
  ff_usd_eur.ics         both, in one calendar
Each file is only rewritten when its events actually change.
"""

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCE = "https://nfs.faireconomy.media/ff_calendar_thisweek.ics"
DIR = Path(__file__).parent

KEEP = {"US", "EZ", "GE", "FR", "IT", "ES"}  # USD + EUR
HIGH, MEDIUM = "⁂", "⁑"  # Forex Factory impact markers

# file name -> (impacts, calendar name, Apple calendar color)
FEEDS = {
    "ff_usd_eur_high.ics": ({HIGH}, "FF High Impact", "#E5262C"),
    "ff_usd_eur_medium.ics": ({MEDIUM}, "FF Medium Impact", "#FF9500"),
    "ff_usd_eur.ics": ({HIGH, MEDIUM}, "FF News USD+EUR", "#E5262C"),
}

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
X-WR-CALDESC:Forex Factory USD and EUR events
X-APPLE-CALENDAR-COLOR:{color}
COLOR:{color}
REFRESH-INTERVAL;VALUE=DURATION:PT1H
X-PUBLISHED-TTL:PT1H
{VTIMEZONE}"""


def fetch() -> str:
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "ff-news-calendar"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8").replace("\r\n", "\n")


def parse(text: str) -> list[tuple[str, str]]:
    """Return (impact marker, event block) for every USD/EUR event."""
    if "BEGIN:VCALENDAR" not in text:
        sys.exit("Upstream did not return a calendar; keeping the old files.")
    events = []
    for block in re.findall(r"BEGIN:VEVENT\n.*?END:VEVENT\n", text, re.S):
        m = re.search(r"^SUMMARY:(\S+)\s+([A-Z]{2})\s", block.replace("\n ", ""), re.M)
        if m and m[2] in KEEP:
            events.append((m[1], block))
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
