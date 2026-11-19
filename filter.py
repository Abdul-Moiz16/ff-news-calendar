"""Filter the Forex Factory weekly calendar to USD + EUR, medium + high impact.

Writes ff_usd_eur.ics, which Apple Calendar subscribes to via GitHub Pages.
The file is only rewritten when the events actually change.
"""

import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

SOURCE = "https://nfs.faireconomy.media/ff_calendar_thisweek.ics"
OUT = Path(__file__).parent / "ff_usd_eur.ics"

KEEP = {"US", "EZ", "GE", "FR", "IT", "ES"}  # USD + EUR
IMPACTS = {"⁑", "⁂"}  # medium (orange), high (red)

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

HEADER = f"""BEGIN:VCALENDAR
PRODID:-//ff-news-calendar//EN
VERSION:2.0
CALSCALE:GREGORIAN
X-WR-CALNAME:FF News USD+EUR
X-WR-CALDESC:Forex Factory medium + high impact USD and EUR events
REFRESH-INTERVAL;VALUE=DURATION:PT1H
X-PUBLISHED-TTL:PT1H
{VTIMEZONE}"""


def fetch() -> str:
    req = urllib.request.Request(SOURCE, headers={"User-Agent": "ff-news-calendar"})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8").replace("\r\n", "\n")


def build(text: str) -> tuple[str, int]:
    kept = []
    for block in re.findall(r"BEGIN:VEVENT\n.*?END:VEVENT\n", text, re.S):
        m = re.search(r"^SUMMARY:(\S+)\s+([A-Z]{2})\s", block.replace("\n ", ""), re.M)
        if m and m[1] in IMPACTS and m[2] in KEEP:
            kept.append(block)
    if "BEGIN:VCALENDAR" not in text:
        sys.exit("Upstream did not return a calendar; keeping the old file.")
    body = HEADER + "".join(kept) + "END:VCALENDAR\n"
    return body.replace("\n", "\r\n"), len(kept)


def strip_stamps(s: str) -> str:
    return re.sub(r"DTSTAMP:\S+", "", s)


def main() -> None:
    try:
        text = fetch()
    except urllib.error.HTTPError as e:
        if e.code == 429:  # rate limited; try again next run
            print("Rate limited by upstream; keeping the old file.")
            return
        raise
    body, count = build(text)
    old = OUT.read_text(encoding="utf-8", newline="") if OUT.exists() else ""
    if strip_stamps(old) == strip_stamps(body):
        print(f"No change ({count} events).")
        return
    OUT.write_text(body, encoding="utf-8", newline="")
    print(f"Updated: {count} events.")


if __name__ == "__main__":
    main()
