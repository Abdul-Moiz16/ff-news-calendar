# ff-news-calendar

Forex Factory's weekly calendar, filtered to **medium + high impact USD** events.
Each event's description includes forecast and previous. Once the number is out, it adds the
actual (from [biquote](https://biquote.io)) and whether it reads bullish or bearish for XAUUSD;
the event title gets a "| gold bullish / gold bearish / in line" tag.
A GitHub Action refreshes it every 5 minutes.

The gold reading is a rule of thumb (better-than-expected US data -> stronger USD -> gold down),
not a prediction. Market data by [biquote](https://biquote.io).

Subscribe in Apple Calendar (File → New Calendar Subscription), one calendar per color:

- Red (high impact): https://abdul-moiz16.github.io/ff-news-calendar/ff_usd_high.ics
- Orange (medium impact): https://abdul-moiz16.github.io/ff-news-calendar/ff_usd_medium.ics
- Both in one calendar: https://abdul-moiz16.github.io/ff-news-calendar/ff_usd_eur.ics

Change the filter by editing `KEEP` / `FEEDS` in `filter.py`.
