# ff-news-calendar

Forex Factory's weekly calendar, filtered to **medium + high impact USD** events.
Each event's description includes forecast, previous, and a rule-of-thumb XAUUSD reading.
A GitHub Action refreshes it every hour.

Subscribe in Apple Calendar (File → New Calendar Subscription), one calendar per color:

- Red (high impact): https://abdul-moiz16.github.io/ff-news-calendar/ff_usd_high.ics
- Orange (medium impact): https://abdul-moiz16.github.io/ff-news-calendar/ff_usd_medium.ics
- Both in one calendar: https://abdul-moiz16.github.io/ff-news-calendar/ff_usd_eur.ics

Change the filter by editing `KEEP` / `FEEDS` in `filter.py`.
