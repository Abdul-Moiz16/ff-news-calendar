// Cloudflare Worker: Forex Factory USD news for Apple Calendar, with actual
// results and a rule-of-thumb XAUUSD reading.
//
//   /high.ics    red    (high impact)
//   /medium.ics  orange (medium impact)
//   /all.ics     both
//
// The calendar is built on every request, so actuals show up on the next
// refresh after a release. Forex Factory's feed has no actuals; those come
// from biquote.io (free, keyless), matched by release time and name.
// Forex Factory rate-limits hard, so its feed is kept in KV and refetched at
// most every FF_MAX_AGE_MS; if a refetch fails, the last good copy is used.

const FF_SOURCE = "https://nfs.faireconomy.media/ff_calendar_thisweek.ics";
const ACTUALS_API = "https://biquote.io/api/calendar?countries=US";
const USER_AGENT = "ff-news-calendar (github.com/Abdul-Moiz16/ff-news-calendar)";
const FF_MAX_AGE_MS = 30 * 60 * 1000;

const KEEP = new Set(["US"]); // USD only
const HIGH = "⁂", MEDIUM = "⁑"; // Forex Factory impact markers

// path -> [impacts, calendar name, Apple calendar color]
const FEEDS = {
  "/high.ics": [[HIGH], "FF USD High Impact", "#E5262C"],
  "/medium.ics": [[MEDIUM], "FF USD Medium Impact", "#FF9500"],
  "/all.ics": [[HIGH, MEDIUM], "FF News USD", "#E5262C"],
};

// Releases where a LOWER number is good for USD (so the gold reading flips).
const LOWER_IS_BETTER = ["unemployment claims", "unemployment rate", "jobless", "continuing claims"];

// Forex Factory wording -> biquote wording, applied before name matching.
const ALIASES = [
  ["philly", "philadelphia"],
  ["uom", "michigan"],
  ["unemployment claims", "initial jobless claims"],
  ["fed chairman", "fed chair"],
];
const IGNORED_WORDS = new Set(["prelim", "revised", "flash", "final", "speaks"]);
const SUFFIX = { thousands: "K", millions: "M", billions: "B" };

// Forex Factory uses TZID=America/New_York but ships no VTIMEZONE block.
const VTIMEZONE = `BEGIN:VTIMEZONE
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
`;

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    const feed = FEEDS[path === "/" ? "/all.ics" : path];
    if (!feed) {
      return new Response("Subscribe to /high.ics, /medium.ics or /all.ics\n", { status: 404 });
    }

    let ffText;
    try {
      ffText = await getForexFactory(env);
    } catch (e) {
      return new Response(`Forex Factory feed unavailable: ${e.message}\n`, { status: 503 });
    }
    const events = parseEvents(ffText);
    const actuals = await getActuals(events.map((e) => e.when));

    const [impacts, name, color] = feed;
    const body = header(name, color) +
      events.filter((e) => impacts.includes(e.impact)).map((e) => buildEvent(e, actuals)).join("") +
      "END:VCALENDAR\n";

    return new Response(body.replace(/\n/g, "\r\n"), {
      headers: {
        "Content-Type": "text/calendar; charset=utf-8",
        "Cache-Control": "public, max-age=120",
      },
    });
  },
};

async function get(url) {
  const res = await fetch(url, { headers: { "User-Agent": USER_AGENT } });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.text();
}

// Forex Factory feed from KV, refreshed at most every FF_MAX_AGE_MS.
async function getForexFactory(env) {
  const stored = await env.FF.get("thisweek", "json");
  if (stored && Date.now() - stored.fetchedAt < FF_MAX_AGE_MS) return stored.text;
  try {
    const text = (await get(FF_SOURCE)).replace(/\r\n/g, "\n");
    if (!text.includes("BEGIN:VCALENDAR")) throw new Error("not a calendar");
    await env.FF.put("thisweek", JSON.stringify({ fetchedAt: Date.now(), text }));
    return text;
  } catch (e) {
    if (stored) return stored.text; // rate-limited or down: use last good copy
    throw e;
  }
}

// Released US figures from biquote for the feed's week; empty if unavailable.
async function getActuals(times) {
  if (!times.length) return [];
  const day = (t) => new Date(t).toISOString().slice(0, 10);
  const from = day(Math.min(...times));
  const to = day(Math.max(...times) + 86400000);
  try {
    const rows = JSON.parse(await get(`${ACTUALS_API}&from=${from}&to=${to}`));
    return rows
      .filter((r) => r.actual !== null && r.actual !== undefined)
      .map((r) => ({ ...r, when: Date.parse(r.time) }));
  } catch {
    return [];
  }
}

function parseEvents(text) {
  const events = [];
  for (const block of text.match(/BEGIN:VEVENT\n[\s\S]*?END:VEVENT\n/g) || []) {
    const lines = block.replace(/\n /g, "").split("\n").filter(Boolean);
    const summary = prop(lines, "SUMMARY");
    const m = summary.match(/^(\S+)\s+([A-Z]{2})\s+(.*)$/);
    if (!m || !KEEP.has(m[2]) || ![HIGH, MEDIUM].includes(m[1])) continue;
    events.push({ impact: m[1], title: m[3], summary, lines, when: nyToUtc(prop(lines, "DTSTART")) });
  }
  return events;
}

function prop(lines, name) {
  for (const l of lines) {
    const i = l.indexOf(":");
    if (l.slice(0, i).split(";")[0] === name) return l.slice(i + 1);
  }
  return "";
}

// "20261125T083000" in New York time -> epoch ms (US DST rules since 2007).
function nyToUtc(stamp) {
  const [y, mo, d, h, mi] = [0, 4, 6, 9, 11].map((i, k) => +stamp.slice(i, i + (k ? 2 : 4)));
  const nthSunday = (month, n) => {
    const first = new Date(Date.UTC(y, month, 1)).getUTCDay();
    return 1 + ((7 - first) % 7) + 7 * (n - 1);
  };
  const local = Date.UTC(y, mo - 1, d, h, mi);
  const dstStart = Date.UTC(y, 2, nthSunday(2, 2), 2);
  const dstEnd = Date.UTC(y, 10, nthSunday(10, 1), 2);
  const offsetHours = local >= dstStart && local < dstEnd ? 4 : 5;
  return local + offsetHours * 3600000;
}

function words(name) {
  let s = name.toLowerCase();
  for (const [from, to] of ALIASES) s = s.replaceAll(from, to);
  return new Set((s.match(/[a-z0-9/]+/g) || []).filter((w) => !IGNORED_WORDS.has(w)));
}

// The biquote release at the same time whose name best fits the FF title.
function match(title, when, actuals) {
  let best = null, bestScore = 0.4; // minimum name overlap to accept a match
  const ff = words(title);
  for (const r of actuals) {
    if (Math.abs(r.when - when) > 10 * 60000) continue;
    const bq = words(r.name);
    const common = [...ff].filter((w) => bq.has(w)).length;
    const score = common / new Set([...ff, ...bq]).size;
    if (score > bestScore) [best, bestScore] = [r, score];
  }
  return best;
}

// "198K" -> [198, "K"], "0.4%" -> [0.4, "%"], "" -> null
function parseValue(s) {
  const m = (s || "").match(/^\s*(-?[\d.]+)\s*([%KMBT]?)\s*$/);
  return m ? [parseFloat(m[1]), m[2]] : null;
}

function fmt(r, key) {
  if (r[key] === null || r[key] === undefined) return null;
  return [Number(r[key]), r.unit === "percent" ? "%" : SUFFIX[r.multiplier] || ""];
}

const show = (v) => `${v[0]}${v[1]}`;

// Compare the actual with the first usable reference -> [note, title tag].
function verdict(title, actual, refs) {
  for (const [label, ref] of refs) {
    if (!ref || ref[1] !== actual[1]) continue; // missing, or not on the same scale
    const diff = actual[0] - ref[0];
    if (diff === 0) {
      return [`RESULT: actual ${show(actual)} = ${label} ${show(ref)}, in line. ` +
        "XAUUSD: little reaction expected (neutral).", "in line"];
    }
    const lowerGood = LOWER_IS_BETTER.some((k) => title.toLowerCase().includes(k));
    const usdGood = lowerGood ? diff < 0 : diff > 0;
    const side = diff > 0 ? "above" : "below";
    return usdGood
      ? [`RESULT: actual ${show(actual)} ${side} ${label} ${show(ref)} -> good for USD -> XAUUSD BEARISH.`, "gold bearish"]
      : [`RESULT: actual ${show(actual)} ${side} ${label} ${show(ref)} -> bad for USD -> XAUUSD BULLISH.`, "gold bullish"];
  }
  return [`RESULT: actual ${show(actual)} (nothing comparable to judge it against).`, ""];
}

// Rule-of-thumb XAUUSD reading before the release (not a prediction).
function goldRule(title, ref) {
  if (!ref) {
    return "XAUUSD: no number to compare. Hawkish tone (rates higher for longer) " +
      "-> USD up, gold bearish. Dovish tone -> gold bullish.";
  }
  const lowerGood = LOWER_IS_BETTER.some((k) => title.toLowerCase().includes(k));
  const [good, bad] = lowerGood ? ["BELOW", "ABOVE"] : ["ABOVE", "BELOW"];
  return `XAUUSD: actual ${good} ${ref} -> USD stronger, gold bearish. ` +
    `Actual ${bad} ${ref} -> USD weaker, gold bullish.`;
}

function buildEvent(event, actuals) {
  const { title, summary, lines, when } = event;
  const field = {};
  for (const part of prop(lines, "DESCRIPTION").split("\\n\\n")) {
    const i = part.indexOf(": ");
    if (i > 0) field[part.slice(0, i)] = part.slice(i + 2);
  }
  const forecast = field.Forecast || "", previous = field.Previous || "";

  const parts = [`Impact: ${field.Impact || ""}`];
  let tag = "";
  const hit = match(title, when, actuals);
  const actual = hit && fmt(hit, "actual");
  if (hit) parts.push(`Actual: ${show(actual)}`);
  if (forecast) parts.push(`Forecast: ${forecast}`);
  else if (hit && fmt(hit, "forecast")) parts.push(`Forecast: ${show(fmt(hit, "forecast"))} (biquote)`);
  if (previous) parts.push(`Previous: ${previous}`);
  if (hit) {
    let note;
    [note, tag] = verdict(title, actual, [
      ["forecast", parseValue(forecast)],
      ["forecast", fmt(hit, "forecast")],
      ["previous", parseValue(previous)],
      ["previous", fmt(hit, "previous")],
    ]);
    parts.push(note);
  } else {
    parts.push(goldRule(title, forecast ? "forecast" : previous ? "previous" : null));
  }
  if (field["View Event"]) parts.push(`View Event: ${field["View Event"]}`);
  if (hit) parts.push("Actual from biquote.io");

  const out = [];
  for (const l of lines) {
    const key = l.slice(0, l.indexOf(":")).split(";")[0];
    if (key === "SUMMARY" && tag) out.push(fold(`SUMMARY:${summary} | ${tag}`));
    else if (key === "DESCRIPTION") out.push(fold("DESCRIPTION:" + parts.join("\\n\\n")));
    else if (l === "END:VEVENT" && hit) {
      // Tell calendar apps the event changed so they pick up the actual.
      out.push("SEQUENCE:1\n", `LAST-MODIFIED:${icsUtc(when)}\n`, "END:VEVENT\n");
    } else out.push(fold(l));
  }
  return out.join("");
}

const icsUtc = (ms) => new Date(ms).toISOString().replace(/[-:]/g, "").slice(0, 15) + "Z";

// Fold an iCalendar content line to 75 octets.
const encoder = new TextEncoder();
function fold(line) {
  const out = [];
  let cur = "", len = 0;
  for (const ch of line) {
    const n = encoder.encode(ch).length;
    if (len + n > (out.length ? 74 : 75)) {
      out.push(cur);
      cur = "";
      len = 0;
    }
    cur += ch;
    len += n;
  }
  out.push(cur);
  return out.join("\n ") + "\n";
}

function header(name, color) {
  return `BEGIN:VCALENDAR
PRODID:-//ff-news-calendar//EN
VERSION:2.0
CALSCALE:GREGORIAN
X-WR-CALNAME:${name}
X-WR-CALDESC:Forex Factory USD events. Actuals from biquote.io
X-APPLE-CALENDAR-COLOR:${color}
COLOR:${color}
REFRESH-INTERVAL;VALUE=DURATION:PT5M
X-PUBLISHED-TTL:PT5M
${VTIMEZONE}`;
}
