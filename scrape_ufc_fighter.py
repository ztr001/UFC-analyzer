"""
Tool: scrape_ufc_fighter.py
Purpose: Given a UFC fighter's name, search ufcstats.com, find their profile,
         and return structured stats data as a dict (or JSON if run directly).

Part of the WAT framework — deterministic execution layer.

Usage:
  python tools/scrape_ufc_fighter.py "Jon Jones"
  python tools/scrape_ufc_fighter.py "Jon Jones" --debug   # prints raw FireCrawl markdown
"""

import os
import re
import sys
import time
import json
from firecrawl import Firecrawl
from dotenv import load_dotenv

# Force UTF-8 output on Windows to avoid charmap encoding errors with fighter names
if sys.stdout.encoding != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

# ── Config ──────────────────────────────────────────────────────────────────
load_dotenv()

FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")
if not FIRECRAWL_API_KEY:
    raise EnvironmentError("FIRECRAWL_API_KEY not found in .env")

app = Firecrawl(api_key=FIRECRAWL_API_KEY)
DELAY = 2  # seconds between FireCrawl requests


# ── FireCrawl helper ─────────────────────────────────────────────────────────

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


# ── Fighter search ───────────────────────────────────────────────────────────

def find_fighter_url(name: str, debug: bool = False) -> tuple[str, str]:
    """
    Search ufcstats.com for a fighter by name.
    Returns (profile_url, matched_full_name).
    Raises ValueError if not found.

    ufcstats search page structure (as FireCrawl markdown):
      | [FirstName](http://www.ufcstats.com/fighter-details/ID) |
      | [LastName](http://www.ufcstats.com/fighter-details/ID)  |
      | [Nickname](http://www.ufcstats.com/fighter-details/ID)  |  ← same URL, skip this
    We only take the first 2 unique parts per URL (first + last name).
    """
    parts = name.strip().split()
    last_initial = parts[-1][0].lower() if parts else "a"

    search_url = f"http://www.ufcstats.com/statistics/fighters?char={last_initial}&page=all"
    print(f"  Searching: {search_url}")

    markdown = firecrawl_get(search_url)
    time.sleep(DELAY)

    if debug:
        print("\n--- RAW SEARCH MARKDOWN (first 3000 chars) ---")
        print(markdown[:3000])
        print("--- END ---\n")

    if not markdown:
        raise ValueError(f'Fighter "{name}": empty response from ufcstats.com search page.')

    # ufcstats links first name, last name, AND nickname to the same profile URL.
    # We collect all linked text parts per URL, then take only the first 2 (first + last name).
    link_pattern = re.compile(
        r'\[([^\]]+)\]\((http://www\.ufcstats\.com/fighter-details/[a-f0-9]+)\)',
        re.IGNORECASE
    )

    url_to_parts: dict[str, list[str]] = {}
    for m in link_pattern.finditer(markdown):
        part = m.group(1).strip()
        url = m.group(2).strip()
        if url not in url_to_parts:
            url_to_parts[url] = []
        if part not in url_to_parts[url]:
            url_to_parts[url].append(part)

    if not url_to_parts:
        raise ValueError(
            f'Fighter "{name}" not found — no fighter links parsed from search page.\n'
            f'Run with --debug to inspect raw markdown.'
        )

    # Take only first 2 parts (first + last name), ignoring any nickname links
    candidates = [(url, " ".join(parts_list[:2])) for url, parts_list in url_to_parts.items()]

    name_lower = name.strip().lower()
    input_words = set(name_lower.split())

    # 1. Exact match
    for url, full in candidates:
        if full.lower() == name_lower:
            return url, full

    # 2. All input words present in candidate name (handles nick variations)
    partial = [(url, full) for url, full in candidates
               if input_words.issubset(set(full.lower().split()))]
    if len(partial) == 1:
        return partial[0]
    if len(partial) > 1:
        return min(partial, key=lambda x: len(x[1]))  # shortest = most specific

    # 3. Last name fuzzy match
    last = parts[-1].lower()
    fuzzy = [(url, full) for url, full in candidates if last in full.lower()]
    if fuzzy:
        return fuzzy[0]

    raise ValueError(
        f'Fighter "{name}" not found on ufcstats.com.\n'
        f'Tip: check spelling, try full name (e.g., "Jon Jones"), or use --debug to inspect markdown.'
    )


# ── Stat parsing helpers ──────────────────────────────────────────────────────

def parse_stat(markdown: str, *labels) -> str:
    """
    Extract a labeled stat from ufcstats.com profile markdown.

    Actual format observed (FireCrawl output):
      - _Height:_
      6' 4"

      - _SLpM:_

      4.38

    The label is wrapped in _ underscores, followed by one or more newlines, then the value.
    """
    for label in labels:
        escaped = re.escape(label)
        # Match _Label:_ followed by the value on the next non-empty line
        pattern = re.compile(
            rf'_{escaped}_\s*[\r\n]+\s*([\S][^\r\n]*)',
            re.IGNORECASE
        )
        m = pattern.search(markdown)
        if m:
            val = m.group(1).strip()
            if val and val not in ('--', '-', ''):
                return val
    return "N/A"


def parse_record(markdown: str) -> dict:
    """
    Parse W-L-D record from the profile heading.
    ufcstats shows: ## Jon Jones     Record: 28-1-0 (1 NC)
    """
    # Look for "Record: W-L-D" first (most reliable)
    m = re.search(r'Record:\s*(\d+)-(\d+)-(\d+)', markdown, re.IGNORECASE)
    if m:
        return {"wins": m.group(1), "losses": m.group(2), "draws": m.group(3)}
    # Fallback: first W-L-D pattern in file
    m = re.search(r'\b(\d+)-(\d+)-(\d+)\b', markdown)
    if m:
        return {"wins": m.group(1), "losses": m.group(2), "draws": m.group(3)}
    return {"wins": "N/A", "losses": "N/A", "draws": "N/A"}


def count_win_methods(fight_history: list[dict]) -> dict:
    """
    Count wins by method from the parsed fight history.
    More reliable than scraping the career win-by section (which varies in page placement)
    and more relevant for analysis — recent patterns matter most for betting.
    """
    ko = sub = dec = 0
    for f in fight_history:
        if f["result"] != "WIN":
            continue
        method = f.get("method", "").upper()
        if "KO" in method or "TKO" in method:
            ko += 1
        elif "SUB" in method:
            sub += 1
        elif "DEC" in method:
            dec += 1
    n = len([f for f in fight_history if f["result"] == "WIN"])
    label = f"(last {len(fight_history)} fights)"
    return {
        "ko":  str(ko),
        "sub": str(sub),
        "dec": str(dec),
        "note": f"Counted from {label}",
    }


def parse_fight_history(markdown: str, limit: int = 10) -> list[dict]:
    """
    Parse recent fight history from the profile page markdown.

    Actual fight row format observed (FireCrawl output):
      | [_win_](fight_url) | [Jon Jones](fighter_url)<br>[Opponent Name](opponent_url) |
        KD | STR | TD | SUB | [Event](event_url)<br>![](belt_img)<br>Date |
        METHOD<br>![](img)<br>Technique | Round | Time |

    Key points:
    - Result is link text: [_win_], [_loss_], [_nc_]
    - Fighter + Opponent in same cell separated by <br>
    - Method cell may contain <br> and image tags
    - Round and Time are the last two columns
    """
    fights = []

    # Match fight rows: | [_result_](url) | [Fighter](url)<br>[Opponent](url) | ... | METHOD | R | T |
    fight_pattern = re.compile(
        r'\|\s*\[_(win|loss|draw|nc)_\]\([^)]+\)\s*\|'   # [_result_](fight_url)
        r'\s*\[[^\]]+\]\([^)]+\)'                          # [Fighter](url) — skip (it's the profiled fighter)
        r'<br>\[([^\]]+)\]\([^)]+\)'                       # <br>[Opponent Name](url)
        r'(?:<br>[^|]*)?\s*\|'                             # rest of fighter cell (ignore)
        r'(?:[^|]*\|){4}'                                  # kd | str | td | sub (skip)
        r'\s*(?:\[[^\]]*\]\([^)]*\))?(?:<br>[^|]*)?\s*\|' # event cell (skip)
        r'\s*([^\n<|]+)',                                   # METHOD — first text before <br> or |
        re.IGNORECASE
    )

    # Also need round and time — extract them from the full row
    # Approach: find full rows first, then parse each piece
    full_row_pattern = re.compile(
        r'(\|\s*\[_(win|loss|draw|nc)_\]\([^)]+\)\s*\|[^\n]+)',
        re.IGNORECASE
    )

    for row_match in full_row_pattern.finditer(markdown):
        row = row_match.group(1)

        # Extract result
        result_m = re.search(r'\[_(win|loss|draw|nc)_\]', row, re.IGNORECASE)
        result = result_m.group(1).upper() if result_m else "N/A"

        # Extract opponent (second fighter link, after first <br>)
        fighter_links = re.findall(r'\[([^\]]+)\]\(http://www\.ufcstats\.com/fighter-details/[^)]+\)', row)
        opponent = fighter_links[1].strip() if len(fighter_links) >= 2 else "N/A"

        # Extract method: first text segment in method cell (before any <br> or ![)
        # Method is typically after the event cell — find it by splitting on |
        # Strip markdown links and image tags from the row first
        clean_row = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', row)       # remove images
        clean_row = re.sub(r'\[[^\]]+\]\([^)]+\)', r'LINK', clean_row)  # replace links with placeholder
        cells = [c.strip() for c in clean_row.split('|') if c.strip()]

        # cells structure: [result_link, fighter_cell, kd, str, td, sub, event, method, round, time]
        # After link replacement: ['LINK', 'LINK<br>LINK', kd, str, td, sub, event, method, round, time]
        method = "N/A"
        round_num = "N/A"
        time_str = "N/A"

        if len(cells) >= 4:
            # Time is last non-empty cell
            time_str = cells[-1].strip() if re.match(r'\d+:\d+', cells[-1]) else "N/A"
            # Round is second-to-last if it's a single digit
            if len(cells) >= 5 and re.match(r'^\d$', cells[-2]):
                round_num = cells[-2]
            # Method is typically at index 7 (0-indexed) — look for known method strings
            for cell in cells:
                cell_clean = re.sub(r'<br>.*', '', cell).strip()  # take text before <br>
                if re.match(r'(KO|TKO|SUB|U-DEC|S-DEC|M-DEC|Decision|Overturned|DQ|NC)', cell_clean, re.IGNORECASE):
                    method = cell_clean
                    break

        # Clean up opponent name (strip markdown formatting)
        opponent = re.sub(r'[_*`]', '', opponent).strip()

        if opponent and opponent != "N/A":
            fights.append({
                "result":   result,
                "opponent": opponent,
                "method":   method,
                "round":    round_num,
                "time":     time_str,
            })

        if len(fights) >= limit:
            break

    return fights


# ── Main scrape function ──────────────────────────────────────────────────────

def scrape_fighter(name: str, debug: bool = False) -> dict:
    """
    Given a fighter name, scrape ufcstats.com and return a structured stats dict.
    This is the primary import target for compare_fighters.py.
    """
    print(f"Fetching data for {name}...")

    # Step 1: find the profile URL via the alphabetical search page
    profile_url, matched_name = find_fighter_url(name, debug=debug)
    print(f"  Found profile: {profile_url}")

    # Step 2: scrape the fighter's profile page
    print(f"  Scraping stats...")
    markdown = firecrawl_get(profile_url)
    time.sleep(DELAY)

    if debug:
        print(f"\n--- RAW PROFILE MARKDOWN (first 8000 chars) ---")
        print(markdown[:8000])
        print("--- END ---\n")

    record = parse_record(markdown)
    fight_history = parse_fight_history(markdown)

    data = {
        "name":        matched_name,
        "profile_url": profile_url,
        "height":      parse_stat(markdown, "Height:"),
        "weight":      parse_stat(markdown, "Weight:"),
        "reach":       parse_stat(markdown, "Reach:"),
        "stance":      parse_stat(markdown, "STANCE:", "Stance:"),
        "dob":         parse_stat(markdown, "DOB:"),
        "team":        "N/A — not listed on ufcstats.com",
        "record":      record,
        "win_methods": count_win_methods(fight_history),
        "striking": {
            "slpm":    parse_stat(markdown, "SLpM:"),
            "str_acc": parse_stat(markdown, "Str. Acc.:"),
            "sapm":    parse_stat(markdown, "SApM:"),
            "str_def": parse_stat(markdown, "Str. Def:"),
        },
        "grappling": {
            "td_avg":  parse_stat(markdown, "TD Avg.:"),
            "td_acc":  parse_stat(markdown, "TD Acc.:"),
            "td_def":  parse_stat(markdown, "TD Def.:"),
            "sub_avg": parse_stat(markdown, "Sub. Avg.:"),
        },
        "fight_history": fight_history,
    }

    wins   = record["wins"]   if record["wins"]   != "N/A" else "?"
    losses = record["losses"] if record["losses"] != "N/A" else "?"
    draws  = record["draws"]  if record["draws"]  != "N/A" else "?"
    print(f"  Scraped: {wins}-{losses}-{draws} record, {len(fight_history)} fights parsed")

    return data


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print('Usage: python tools/scrape_ufc_fighter.py "Fighter Name" [--debug]')
        sys.exit(1)

    fighter_name = sys.argv[1]
    debug_mode = "--debug" in sys.argv

    result = scrape_fighter(fighter_name, debug=debug_mode)
    print()
    print(json.dumps(result, indent=2, ensure_ascii=False))
