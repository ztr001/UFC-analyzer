"""
Tool: compare_fighters.py
Purpose: Given two UFC fighter names, scrape their stats from ufcstats.com,
         send the data to Claude, and stream a full matchup analysis to the terminal.

Part of the WAT framework — deterministic execution layer.

Usage:
  python tools/compare_fighters.py "Jon Jones" "Stipe Miocic"
  python tools/compare_fighters.py "Jon Jones" "Stipe Miocic" --debug   # also prints raw markdown
"""

import os
import sys

# Force UTF-8 output on Windows to avoid charmap encoding errors
if sys.stdout.encoding != "utf-8":
    sys.stdout = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1)

from dotenv import load_dotenv
load_dotenv()

# ── Validate environment before doing anything expensive ─────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
if not ANTHROPIC_API_KEY:
    print("ERROR: ANTHROPIC_API_KEY not found in .env")
    print()
    print("To fix:")
    print("  1. Get a key at console.anthropic.com")
    print("  2. Open your .env file and add:")
    print("       ANTHROPIC_API_KEY=sk-ant-...your-key-here...")
    sys.exit(1)

# Import scraper from same tools/ directory
sys.path.insert(0, os.path.dirname(__file__))
from scrape_ufc_fighter import scrape_fighter

import anthropic

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Prompt construction ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert UFC analyst with deep knowledge of mixed martial arts, fighter styles, and matchup dynamics. You analyze fighter statistics and fight histories to produce accurate, insightful matchup breakdowns.

When given two fighters' data:
1. Identify each fighter's true fighting style from their stats and history — not just their listed stance or reputation
2. Assess real strengths and weaknesses based on numbers, not hype
3. Identify how the styles interact — where each fighter has the edge and where they're vulnerable
4. Predict the most likely fight outcomes based on statistical probability and stylistic logic

Be specific and cite statistics. Avoid generic MMA commentary. If a stat shows "N/A", acknowledge the gap rather than inventing data."""


def format_fighter_block(f: dict) -> str:
    """Format a fighter's stats into a clean text block for the Claude prompt."""
    r  = f["record"]
    s  = f["striking"]
    g  = f["grappling"]
    wm = f["win_methods"]

    # Format fight history lines
    history_lines = []
    for fight in f["fight_history"]:
        line = f"  {fight['result']} vs {fight['opponent']} — {fight['method']}"
        if fight.get("round") and fight["round"] != "N/A":
            line += f", R{fight['round']}"
        if fight.get("time") and fight["time"] != "N/A":
            line += f" ({fight['time']})"
        history_lines.append(line)

    history_text = (
        "\n".join(history_lines)
        if history_lines
        else "  (No fight history parsed — check ufcstats.com manually)"
    )

    record_str = f"{r['wins']}-{r['losses']}-{r['draws']}"
    wm_note = wm.get("note", "")

    return f"""=== {f['name'].upper()} ===
Record: {record_str}
Height: {f['height']} | Weight: {f['weight']} | Reach: {f['reach']} | Stance: {f['stance']}

Striking (career averages):
  {s['slpm']} sig. strikes landed/min | {s['sapm']} absorbed/min
  {s['str_acc']} striking accuracy | {s['str_def']} strike defense

Grappling (career averages):
  {g['td_avg']} takedowns/15min | {g['td_acc']} TD accuracy | {g['td_def']} TD defense
  {g['sub_avg']} submission attempts/15min

Win methods {wm_note}: {wm['ko']} KO/TKO | {wm['sub']} Submissions | {wm['dec']} Decisions

Recent fight history (most recent first):
{history_text}"""


def build_prompt(f1: dict, f2: dict) -> str:
    """Assemble the full user prompt from both fighters' data."""
    return f"""{format_fighter_block(f1)}

{format_fighter_block(f2)}

---

Produce the following analysis in this exact format:

## {f1['name']} — Fighting Style & Profile
[3-4 paragraphs: how they actually fight, what their stats reveal about their style, their best weapons, tendencies under pressure, and notable patterns from fight history]

## {f2['name']} — Fighting Style & Profile
[same structure as above]

## Head-to-Head: Strengths & Weaknesses
[2-3 paragraphs analyzing how these styles interact. Where does each fighter have the edge? What are the critical exchanges that will decide this fight? Be specific about which stats matter most in this matchup.]

## 3 Most Likely Fight Endings (Ranked by Probability)

**#1 — [Specific description, e.g., "Jon Jones wins by TKO, Round 3"]**
Probability: [High / Medium / Low]
Why: [2-3 sentences of specific reasoning]

**#2 — [Specific description]**
Probability: [High / Medium / Low]
Why: [2-3 sentences of specific reasoning]

**#3 — [Specific description]**
Probability: [High / Medium / Low]
Why: [2-3 sentences of specific reasoning]"""


# ── Main analysis runner ──────────────────────────────────────────────────────

def run_analysis(fighter1_name: str, fighter2_name: str, debug: bool = False):
    """Scrape both fighters and stream the Claude matchup analysis to the terminal."""

    print()
    f1 = scrape_fighter(fighter1_name, debug=debug)

    print()
    f2 = scrape_fighter(fighter2_name, debug=debug)

    print()
    print("Sending to Claude for analysis...")
    print("=" * 60)
    print()

    prompt = build_prompt(f1, f2)

    if debug:
        print("--- PROMPT SENT TO CLAUDE ---")
        print(prompt)
        print("--- END PROMPT ---\n")

    try:
        with client.messages.stream(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        ) as stream:
            for text in stream.text_stream:
                print(text, end="", flush=True)
    except anthropic.AuthenticationError:
        print("\nERROR: Invalid Anthropic API key.")
        print("Check your ANTHROPIC_API_KEY in .env — make sure it starts with 'sk-ant-'")
        sys.exit(1)
    except anthropic.APIError as e:
        print(f"\nERROR: Anthropic API error: {e}")
        sys.exit(1)

    print()
    print()
    print("=" * 60)
    print("Analysis complete.")


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print('Usage: python tools/compare_fighters.py "Fighter One" "Fighter Two" [--debug]')
        print()
        print('Examples:')
        print('  python tools/compare_fighters.py "Jon Jones" "Stipe Miocic"')
        print('  python tools/compare_fighters.py "Islam Makhachev" "Charles Oliveira" --debug')
        sys.exit(1)

    f1 = sys.argv[1]
    f2 = sys.argv[2]
    debug = "--debug" in sys.argv

    run_analysis(f1, f2, debug=debug)
