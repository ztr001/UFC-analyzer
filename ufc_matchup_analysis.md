# Workflow: UFC Matchup Analysis

## Objective

Given two UFC fighter names, scrape their stats from ufcstats.com and generate a full AI-powered matchup analysis: individual fighter profiles, head-to-head strengths/weaknesses, and the three most likely fight endings ranked by probability.

---

## Required Setup (One-Time)

Before running this workflow for the first time:

**1. Install the Anthropic SDK:**
```
pip install anthropic
```

**2. Add your Anthropic API key to `.env`:**
Open `.env` and change this line:
```
# ANTHROPIC_API_KEY=
```
To:
```
ANTHROPIC_API_KEY=sk-ant-...your-key-here...
```
Get a key at: console.anthropic.com

Your `.env` already has `FIRECRAWL_API_KEY` set — no changes needed there.

---

## Inputs Required

- Fighter 1 name (string)
- Fighter 2 name (string)
- `FIRECRAWL_API_KEY` in `.env` (already configured)
- `ANTHROPIC_API_KEY` in `.env` (must be added per setup above)

---

## How to Run

Single command from the project root:

```
python tools/compare_fighters.py "Fighter One" "Fighter Two"
```

**Examples:**
```
python tools/compare_fighters.py "Jon Jones" "Stipe Miocic"
python tools/compare_fighters.py "Islam Makhachev" "Charles Oliveira"
python tools/compare_fighters.py "Alex Pereira" "Magomed Ankalaev"
```

**Debug mode** (prints raw FireCrawl markdown — useful for tuning or troubleshooting):
```
python tools/compare_fighters.py "Jon Jones" "Stipe Miocic" --debug
```

**Test scraper only** (scrape one fighter, print JSON, no Claude call):
```
python tools/scrape_ufc_fighter.py "Jon Jones"
python tools/scrape_ufc_fighter.py "Jon Jones" --debug
```

---

## What the Output Shows

1. **Fighter Profile** (for each fighter)
   - How they actually fight, what their stats reveal about their style
   - Best weapons, tendencies under pressure, patterns from fight history

2. **Head-to-Head: Strengths & Weaknesses**
   - Where each fighter has the edge
   - Critical exchanges that will decide the fight
   - Specific stat comparisons that matter in this matchup

3. **3 Most Likely Fight Endings (Ranked)**
   - Each with: specific description, probability rating (High/Medium/Low), and reasoning

---

## Data Source

All stats scraped from **ufcstats.com**:
- Bio: height, weight, reach, stance, date of birth
- Record: W-L-D
- Striking: SLpM, accuracy %, SApM, defense %
- Grappling: TD avg, TD accuracy, TD defense, sub attempt avg
- Fight history: last 10 fights (result, opponent, method, round, time)

**Note:** Team/gym affiliation is not listed on ufcstats.com and shows as "N/A". If team is important for analysis, look it up manually on Wikipedia or the UFC site.

**Note:** Win method counts (KO/TKO, Submission, Decision) are counted from the last 10 fights, not career totals. This is intentional — recent patterns are more predictive than career-long aggregates.

---

## Tools Used

| Tool | File | Purpose |
|------|------|---------|
| Scraper | `tools/scrape_ufc_fighter.py` | Fetch and parse fighter stats from ufcstats.com |
| Comparator | `tools/compare_fighters.py` | Orchestrate both scrapes + Claude API call + output |

---

## Edge Cases

**Fighter name not found:**
- Check spelling — ufcstats.com uses the fighter's official name (e.g., "Stipe Miocic" not "Stipe")
- Try the full name (first + last)
- Use `--debug` to inspect the raw search page and see what names are available

**Common last names (Jackson, Santos, Silva, Garcia):**
- The scraper picks the first matching fighter. If you get the wrong fighter, try adding the first name
- Example: "Paulo Costa" not just "Costa"

**Fighter not on ufcstats.com:**
- Very early career or non-UFC fighters won't be listed
- Check ufcstats.com directly to confirm they're listed

**Missing stats (shows "N/A"):**
- Fighters with few fights may not have all stats populated on ufcstats.com
- Claude will acknowledge the missing data rather than invent numbers

**Rate limiting:**
- The scraper waits 2 seconds between FireCrawl requests and retries once on 429 errors
- If you hit persistent rate limits, wait 30 seconds and try again

**Encoding errors on Windows:**
- Both tools have the UTF-8 stdout fix at the top — this handles fighter names with accents (Aljamain Sterling, José Aldo, etc.)

---

## Self-Improvement Notes

*Update this section when you discover new quirks, fix parsing issues, or improve the workflow.*

- **2026-04-02:** Initial build. FireCrawl markdown structure confirmed for ufcstats.com fighter profiles:
  - Stats use `_Label:_\nvalue` format (italic label, value on next line)
  - Fight rows use `[_win_](url)` for result, `<br>` separator between fighters in same cell
  - Nickname is linked to same URL as name — scraper takes only first 2 name parts
  - Win by section not reliably parsed from markdown — using fight history counts instead
