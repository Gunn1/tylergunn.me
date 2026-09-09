#!/usr/bin/env python3
"""
Pull real CTF results from the CTFtime API and write them into index.html.

CTFtime has no endpoint that lists the events a team played — /teams/{id}/
returns aggregate rating only. The event list has to be recovered by scanning
/results/{year}/, which contains every event's full scoreboard, and picking out
rows whose team_id is ours. That is what this script does.

Caveats worth remembering, because they affect what the numbers mean:

  * CTFtime tracks TEAMS, not individuals. These are events the team scored in;
    it has no idea which ones any one member actually played.
  * Only rated events where the organisers submitted results appear at all.
  * The `participants` field on an event is CTFtime *registrations*, not the
    scoreboard size. Percentiles here use len(scores), which is the real
    number of teams that scored.
  * The API returns 403 without a browser User-Agent.

Usage:
    python3 ctftime.py                 fetch, write cache, update index.html
    python3 ctftime.py --offline       rebuild HTML from the cached JSON
    python3 ctftime.py --dry-run       print the results, change nothing
    python3 ctftime.py --since 2022    earliest year to scan (default 2022)
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CACHE = ROOT / "content" / "ctf.json"
INDEX = ROOT / "index.html"

# Teams to include. Add or remove entries here and re-run — the numeric ID is
# the last part of the team's CTFtime URL (ctftime.org/team/<id>).
# Removing a team drops its events from the site on the next run, including
# from the cached --offline path.
TEAMS: dict[int, str] = {
    183633: "StormChasers",
    370924: "Drop Tables Crew",
}

# CTFtime rejects requests without a browser-shaped User-Agent.
UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
TIMEOUT = 90

LIST_START, LIST_END = "<!-- ctf:start -->", "<!-- ctf:end -->"
STAT_START, STAT_END = "<!-- ctf:stat:start -->", "<!-- ctf:stat:end -->"

# A finish inside this fraction of the field gets the accent badge.
TOP_TIER = 0.10
GOOD_TIER = 0.25


class CTFError(Exception):
    pass


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        raise CTFError(f"{url}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CTFError(f"{url}: {exc}") from exc


def fetch(since: int, verbose: bool = True) -> list[dict]:
    this_year = dt.date.today().year
    events: dict[str, dict] = {}
    rows: list[dict] = []

    for year in range(since, this_year + 1):
        try:
            results = get_json(f"https://ctftime.org/api/v1/results/{year}/")
        except CTFError as exc:
            print(f"  {year}: skipped ({exc})", file=sys.stderr)
            continue

        found = 0
        for event_id, event in results.items():
            scores = event.get("scores") or []
            for row in scores:
                if row.get("team_id") not in TEAMS:
                    continue
                found += 1

                if event_id not in events:
                    try:
                        events[event_id] = get_json(
                            f"https://ctftime.org/api/v1/events/{event_id}/"
                        )
                    except CTFError:
                        events[event_id] = {}

                meta = events[event_id]
                start = (meta.get("start") or "")[:10] or f"{year}-01-01"
                rows.append(
                    {
                        "event_id": int(event_id),
                        "date": start,
                        "title": (event.get("title") or meta.get("title") or "").strip(),
                        "team": TEAMS[row["team_id"]],
                        "team_id": row["team_id"],
                        "place": row.get("place"),
                        "scored": len(scores),
                        "weight": round(float(meta.get("weight") or 0), 2),
                        "url": f"https://ctftime.org/event/{event_id}",
                    }
                )

        if verbose:
            print(f"  {year}: {len(results):>4} events scanned, {found} of ours")

    if not rows:
        raise CTFError(
            "no participations found — check the team IDs in TEAMS, or widen --since"
        )

    rows.sort(key=lambda r: (r["date"], r["title"]), reverse=True)
    return rows


def tier(place: int, scored: int) -> str:
    if not scored or not place:
        return "none"
    frac = place / scored
    if frac <= TOP_TIER:
        return "top"
    if frac <= GOOD_TIER:
        return "good"
    return "none"


def slug(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[-\s]+", "-", text) or "event"


def render_rows(rows: list[dict]) -> str:
    out = []
    for r in rows:
        pct = f"top {r['place'] / r['scored'] * 100:.0f}%" if r["scored"] else "—"
        weight = f" · weight {r['weight']:.0f}" if r["weight"] else ""
        out.append(
            f"""      <li class="ctf" data-node="{slug(r['title'])}" data-node-href="{r['url']}">
        <a class="ctf__row" href="{r['url']}" rel="noopener">
          <span class="ctf__place">{r['place']}<span class="ctf__of">/{r['scored']}</span></span>
          <span class="ctf__body">
            <span class="ctf__title">{html.escape(r['title'])}</span>
            <span class="ctf__meta">{r['date']} · {html.escape(r['team'])}{weight}</span>
          </span>
          <span class="ctf__pct" data-tier="{tier(r['place'], r['scored'])}">{pct}</span>
        </a>
      </li>"""
        )
    return "\n".join(out)


def splice(text: str, start: str, end: str, replacement: str, indent: str = "      ") -> str:
    if start not in text or end not in text:
        raise CTFError(f"index.html is missing the {start} / {end} markers")
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    return f"{head}{start}\n{replacement}\n{indent}{end}{tail}"


def update_index(rows: list[dict]) -> bool:
    text = original = INDEX.read_text(encoding="utf-8")
    text = splice(text, LIST_START, LIST_END, render_rows(rows))
    stat = f'        <dd class="stat__value" data-count="{len(rows)}">{len(rows)}</dd>'
    text = splice(text, STAT_START, STAT_END, stat, indent="        ")
    if text == original:
        return False
    INDEX.write_text(text, encoding="utf-8")
    return True


def summarise(rows: list[dict]) -> None:
    print(f"\n{'DATE':<12} {'PLACE':>6} {'OF':>6} {'TOP':>6} {'WT':>4}  EVENT")
    print("-" * 84)
    for r in rows:
        pct = f"{r['place'] / r['scored'] * 100:.0f}%" if r["scored"] else "?"
        print(
            f"{r['date']:<12} {r['place']:>6} {r['scored']:>6} {pct:>6} "
            f"{r['weight']:>4.0f}  {r['title']}"
        )

    by_team: dict[str, list[dict]] = {}
    for r in rows:
        by_team.setdefault(r["team"], []).append(r)

    print()
    for team, rs in by_team.items():
        best = min(rs, key=lambda r: r["place"])
        print(f"  {team}: {len(rs)} events · best {best['place']} at {best['title']}")
    print(f"\n  {len(rows)} events total, {rows[-1]['date']} .. {rows[0]['date']}")


def main() -> int:
    ap = argparse.ArgumentParser(description="Sync CTFtime results into index.html.")
    ap.add_argument("--since", type=int, default=2022, help="earliest year to scan")
    ap.add_argument("--offline", action="store_true", help="use the cached JSON")
    ap.add_argument("--dry-run", action="store_true", help="print only, write nothing")
    args = ap.parse_args()

    try:
        if args.offline:
            if not CACHE.exists():
                raise CTFError(f"no cache at {CACHE} — run without --offline first")
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
            # Re-apply the team filter, so dropping a team from TEAMS takes
            # effect offline too rather than silently reusing stale rows.
            rows = [r for r in cached if r.get("team_id") in TEAMS]
            dropped = len(cached) - len(rows)
            print(
                f"loaded {len(rows)} cached result(s)"
                + (f" ({dropped} filtered out — not in TEAMS)" if dropped else "")
            )
            if not rows:
                raise CTFError("no cached results match TEAMS — re-run without --offline")
        else:
            print(f"scanning CTFtime results {args.since}..{dt.date.today().year}")
            rows = fetch(args.since)

        summarise(rows)

        if args.dry_run:
            print("\ndry run — nothing written")
            return 0

        if not args.offline:
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
            print(f"\nwrote {CACHE.relative_to(ROOT)}")

        print("updated index.html" if update_index(rows) else "index.html already current")

    except CTFError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
