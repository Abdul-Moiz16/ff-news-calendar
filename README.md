# ff-news-calendar

Forex Factory's weekly calendar, filtered to **medium + high impact USD** events, for Apple Calendar.
Each event's description includes forecast and previous. Once the number is out, it adds the
actual (from [biquote](https://biquote.io)) and whether it reads bullish or bearish for XAUUSD;
the event title gets a "| gold bullish / gold bearish / in line" tag.

The gold reading is a rule of thumb (better-than-expected US data -> stronger USD -> gold down),
not a prediction. Market data by [biquote](https://biquote.io).

## Subscribe (Apple Calendar → File → New Calendar Subscription)

Served live by a Cloudflare Worker (`worker/`), built fresh on every refresh:

- Red (high impact): https://ff-news-calendar.abdul-moiz16.workers.dev/high.ics
- Orange (medium impact): https://ff-news-calendar.abdul-moiz16.workers.dev/medium.ics
- Both in one calendar: https://ff-news-calendar.abdul-moiz16.workers.dev/all.ics

Deploy changes with `cd worker && npx wrangler deploy`.

## Old GitHub Pages version

`filter.py` + the GitHub Action did the same thing on a schedule, but GitHub's free scheduler
ran only a few times a day, so it's disabled. Re-enable with
`gh workflow enable update.yml` if ever needed.
