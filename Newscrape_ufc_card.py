"""
Tool: scrape_ufc_card.py
Purpose: Scrape the next upcoming UFC event from ufcstats.com and return
         the full fight card as a structured dict.

Part of the WAT framework — deterministic execution layer.

Usage:
  python tools/scrape_ufc_card.py             # prints next event + fights
  python tools/scrape_ufc_card.py --debug     # also prints raw FireCrawl markdown
"""

import os
import re
import sys
import time
import json

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

from dotenv import load_dotenv
load_dotenv()

from firecrawl import Firecrawl

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
if not FIRECRAWL_API_KEY:
    raise EnvironmentError("FIRECRAWL_API_KEY not found in .env")

app = Firecrawl(api_key=FIRECRAWL_API_KEY)
DELAY = 2  # seconds between FireCrawl requests


# ── FireCrawl helper ──────────────────────────────────────────────────────────

def firecrawl_get(url: str) -> str:
    """Scrape a URL with FireCrawl and return markdown. Retries once on 429."""
    try:
        result = app.scrape(url, formats=["markdown"])
        return result.markdown or ""
    except Exception as e:
        err = str(e)
        if "429" in err or "rate" in err.lower():
            print("  Rate limited. Waiting 10s then retrying...")
            time.sleep(10)
            result = app.scrape(url, formats=["markdown"])
            return result.markdown or ""
        raise


# ── Upcoming events page parser ───────────────────────────────────────────────

def parse_upcoming_event(markdown: str, debug: bool = False) -> tuple[str, str, str, str]:
    """
    Parse the first upcoming event from the events list page.
    Returns (event_name, date, location, event_url).

    Confirmed ufcstats upcoming events page format (FireCrawl markdown):
      | _[Event Name](http://www.ufcstats.com/event-details/UUID)_<br>_Date_ | Location |
    Event name + date are in the SAME cell, separated by <br>.
    Location is in the second column.
    """
    if debug:
        print("\n--- RAW UPCOMING EVENTS MARKDOWN (first 5000 chars) ---")
        print(markdown[:5000])
        print("--- END ---\n")

    # Combined pattern: captures event name, URL, date, and location from one row
    row_pattern = re.compile(
        r'\|\s*_?\[([^\]]+)\]\((http://www\.ufcstats\.com/event-details/[a-f0-9]+)\)_?'
        r'<br>_([^_\n|]+)_?\s*\|\s*([^|\n]+?)\s*\|',
        re.IGNORECASE
    )

    m = row_pattern.search(markdown)
    if not m:
        raise ValueError(
            "No upcoming event found on ufcstats.com/statistics/events/upcoming.\n"
            "Run with --debug to inspect the raw markdown."
        )

    event_name = re.sub(r'[_*`]', '', m.group(1)).strip()
    event_url  = m.group(2).strip()
    date       = re.sub(r'[_*`]', '', m.group(3)).strip()
    location   = re.sub(r'[_*`]', '', m.group(4)).strip()

    return event_name, date, location, event_url


# ── Event details page parser ─────────────────────────────────────────────────

def parse_fight_card(markdown: str, debug: bool = False) -> list[dict]:
    """
    Parse all fights from an event details page.
    Returns list of {fighter1, fighter2, weight_class} dicts.

    ufcstats event page fight row structure (inferred from site conventions):
      | [Fighter1](fighter_url)<br>[Fighter2](fighter_url) | kd | str | td | sub |
        [Event](url) | METHOD | Round | Time | Weight class |
    OR fights may be listed differently — debug output will confirm.
    """
    if debug:
        print("\n--- RAW EVENT DETAILS MARKDOWN (first 8000 chars) ---")
        print(markdown[:8000])
        print("--- END ---\n")

    fights = []

    # Strategy 1: look for rows containing two fighter-details links separated by <br>
    # This matches the pattern confirmed in fight history parsing
    fighter_pair_pattern = re.compile(
        r'\[([^\]]+)\]\(http://www\.ufcstats\.com/fighter-details/[a-f0-9]+\)'
        r'<br>'
        r'\[([^\]]+)\]\(http://www\.ufcstats\.com/fighter-details/[a-f0-9]+\)',
        re.IGNORECASE
    )

    # Also try to extract weight class from the same row
    # Weight class typically appears somewhere in the row
    weight_classes = [
        "Strawweight", "Flyweight", "Bantamweight", "Featherweight",
        "Lightweight", "Welterweight", "Middleweight", "Light Heavyweight",
        "Heavyweight", "Women's Strawweight", "Women's Flyweight",
        "Women's Bantamweight", "Women's Featherweight"
    ]
    weight_pattern = re.compile(
        r'(' + '|'.join(re.escape(w) for w in weight_classes) + r')',
        re.IGNORECASE
    )

    # Find all lines containing a fighter pair
    lines = markdown.split('\n')
    for line in lines:
        m = fighter_pair_pattern.search(line)
        if not m:
            continue

        f1 = re.sub(r'[_*`]', '', m.group(1)).strip()
        f2 = re.sub(r'[_*`]', '', m.group(2)).strip()

        # Skip header rows or empty names
        if not f1 or not f2 or f1.lower() == f2.lower():
            continue

        # Look for weight class in this line
        wm = weight_pattern.search(line)
        weight_class = wm.group(1) if wm else "N/A"

        fights.append({
            "fighter1": f1,
            "fighter2": f2,
            "weight_class": weight_class,
        })

    # Strategy 2 fallback: if no <br> pairs found, try vs-pattern in plain text
    if not fights:
        vs_pattern = re.compile(
            r'\[([^\]]+)\]\(http://www\.ufcstats\.com/fighter-details/[a-f0-9]+\)'
            r'[^\n]{0,30}'
            r'\[([^\]]+)\]\(http://www\.ufcstats\.com/fighter-details/[a-f0-9]+\)',
            re.IGNORECASE
        )
        seen = set()
        for m in vs_pattern.finditer(markdown):
            f1 = re.sub(r'[_*`]', '', m.group(1)).strip()
            f2 = re.sub(r'[_*`]', '', m.group(2)).strip()
            key = (f1.lower(), f2.lower())
            if key in seen or not f1 or not f2 or f1.lower() == f2.lower():
                continue
            seen.add(key)
            fights.append({"fighter1": f1, "fighter2": f2, "weight_class": "N/A"})

    return fights


# ── Main scrape function ──────────────────────────────────────────────────────

def scrape_upcoming_card(debug: bool = False) -> dict:
    """
    Scrape the next upcoming UFC event from ufcstats.com.
    Returns a dict with event info and the full fight card.
    """
    print("Fetching upcoming UFC event list...")
    events_url = "http://www.ufcstats.com/statistics/events/upcoming"
    events_md = firecrawl_get(events_url)
    time.sleep(DELAY)

    event_name, date, location, event_url = parse_upcoming_event(events_md, debug=debug)
    print(f"  Found: {event_name} — {date}")
    print(f"  URL: {event_url}")

    print(f"Fetching fight card...")
    card_md = firecrawl_get(event_url)
    time.sleep(DELAY)

    fights = parse_fight_card(card_md, debug=debug)
    print(f"  Parsed {len(fights)} fights")

    return {
        "event_name": event_name,
        "date": date,
        "location": location,
        "event_url": event_url,
        "fights": fights,
    }


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    debug_mode = "--debug" in sys.argv

    card = scrape_upcoming_card(debug=debug_mode)

    print()
    print(f"=== {card['event_name']} ===")
    print(f"Date:     {card['date']}")
    print(f"Location: {card['location']}")
    print()
    for i, fight in enumerate(card["fights"], 1):
        wc = f" [{fight['weight_class']}]" if fight['weight_class'] != "N/A" else ""
        print(f"  {i:2}. {fight['fighter1']} vs {fight['fighter2']}{wc}")

    if not card["fights"]:
        print("  (no fights parsed — run with --debug to inspect raw markdown)")
