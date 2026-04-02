"""
UFC Matchup Analyzer — Streamlit Web App
Scrapes ufcstats.com for fighter data, then uses Claude to generate
a full matchup analysis with fighter profiles and fight ending predictions.
"""

import os
import sys
import streamlit as st
from dotenv import load_dotenv

# ── Load API keys ─────────────────────────────────────────────────────────────
# On Streamlit Cloud: keys come from the Secrets manager (st.secrets)
# Locally: keys come from .env
if "FIRECRAWL_API_KEY" in st.secrets:
    os.environ["FIRECRAWL_API_KEY"] = st.secrets["FIRECRAWL_API_KEY"]
    os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
else:
    load_dotenv()

# ── Imports ───────────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tools"))
from scrape_ufc_fighter import scrape_fighter
import anthropic

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="UFC Matchup Analyzer",
    page_icon="🥊",
    layout="centered",
)

st.title("🥊 UFC Matchup Analyzer")
st.caption("Pulls live stats from ufcstats.com · Analysis powered by Claude AI")
st.divider()

# ── Fighter input ─────────────────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    fighter1 = st.text_input("Fighter 1", placeholder="e.g. Jon Jones")
with col2:
    fighter2 = st.text_input("Fighter 2", placeholder="e.g. Stipe Miocic")

analyze = st.button("⚡ Analyze Matchup", type="primary", use_container_width=True)

# ── Prompt helpers ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert UFC analyst with deep knowledge of mixed martial arts, fighter styles, and matchup dynamics. You analyze fighter statistics and fight histories to produce accurate, insightful matchup breakdowns.

When given two fighters' data:
1. Identify each fighter's true fighting style from their stats and history — not just their listed stance or reputation
2. Assess real strengths and weaknesses based on numbers, not hype
3. Identify how the styles interact — where each fighter has the edge and where they're vulnerable
4. Predict the most likely fight outcomes based on statistical probability and stylistic logic

Be specific and cite statistics. Avoid generic MMA commentary. If a stat shows "N/A", acknowledge the gap rather than inventing data."""


def format_fighter_block(f: dict) -> str:
    r  = f["record"]
    s  = f["striking"]
    g  = f["grappling"]
    wm = f["win_methods"]
    wm_note = wm.get("note", "")

    history_lines = []
    for fight in f["fight_history"]:
        line = f"  {fight['result']} vs {fight['opponent']} — {fight['method']}"
        if fight.get("round") and fight["round"] != "N/A":
            line += f", R{fight['round']}"
        if fight.get("time") and fight["time"] != "N/A":
            line += f" ({fight['time']})"
        history_lines.append(line)

    history_text = (
        "\n".join(history_lines) if history_lines
        else "  (No fight history parsed)"
    )

    return f"""=== {f['name'].upper()} ===
Record: {r['wins']}-{r['losses']}-{r['draws']}
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


def stream_analysis(f1: dict, f2: dict):
    """Generator that yields Claude's analysis text chunk by chunk."""
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    prompt = build_prompt(f1, f2)
    with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        for text in stream.text_stream:
            yield text


# ── Fighter stat cards ────────────────────────────────────────────────────────

def show_fighter_card(f: dict):
    r = f["record"]
    s = f["striking"]
    g = f["grappling"]

    st.markdown(f"### {f['name']}")
    st.markdown(
        f"**Record:** {r['wins']}-{r['losses']}-{r['draws']} &nbsp;|&nbsp; "
        f"**Height:** {f['height']} &nbsp;|&nbsp; "
        f"**Weight:** {f['weight']} &nbsp;|&nbsp; "
        f"**Reach:** {f['reach']} &nbsp;|&nbsp; "
        f"**Stance:** {f['stance']}"
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Striking**")
        st.markdown(
            f"- Landed/min: **{s['slpm']}**\n"
            f"- Accuracy: **{s['str_acc']}**\n"
            f"- Absorbed/min: **{s['sapm']}**\n"
            f"- Defense: **{s['str_def']}**"
        )
    with c2:
        st.markdown("**Grappling**")
        st.markdown(
            f"- TD avg: **{g['td_avg']}**/15min\n"
            f"- TD accuracy: **{g['td_acc']}**\n"
            f"- TD defense: **{g['td_def']}**\n"
            f"- Sub avg: **{g['sub_avg']}**/15min"
        )

    with st.expander("Recent fight history"):
        for fight in f["fight_history"]:
            emoji = "✅" if fight["result"] == "WIN" else ("❌" if fight["result"] == "LOSS" else "⚪")
            round_time = ""
            if fight.get("round") and fight["round"] != "N/A":
                round_time = f" R{fight['round']}"
                if fight.get("time") and fight["time"] != "N/A":
                    round_time += f" ({fight['time']})"
            st.markdown(f"{emoji} **{fight['opponent']}** — {fight['method']}{round_time}")


# ── Main analysis flow ────────────────────────────────────────────────────────

if analyze:
    if not fighter1.strip() or not fighter2.strip():
        st.error("Please enter both fighter names.")
        st.stop()

    if not os.environ.get("FIRECRAWL_API_KEY"):
        st.error("FIRECRAWL_API_KEY not configured. Check your Streamlit secrets.")
        st.stop()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        st.error("ANTHROPIC_API_KEY not configured. Check your Streamlit secrets.")
        st.stop()

    f1_data = None
    f2_data = None

    # Scrape both fighters
    with st.status("Fetching fighter data...", expanded=True) as status:
        try:
            st.write(f"Looking up **{fighter1}** on ufcstats.com...")
            f1_data = scrape_fighter(fighter1.strip())
            st.write(f"✅ Found {f1_data['name']} ({f1_data['record']['wins']}-{f1_data['record']['losses']}-{f1_data['record']['draws']})")

            st.write(f"Looking up **{fighter2}** on ufcstats.com...")
            f2_data = scrape_fighter(fighter2.strip())
            st.write(f"✅ Found {f2_data['name']} ({f2_data['record']['wins']}-{f2_data['record']['losses']}-{f2_data['record']['draws']})")

            status.update(label="Data fetched!", state="complete")
        except SystemExit:
            status.update(label="Fighter not found", state="error")
            st.error(
                f"Could not find one of the fighters on ufcstats.com. "
                f"Check the spelling and try the full name (e.g., 'Jon Jones' not 'Jones')."
            )
            st.stop()
        except Exception as e:
            status.update(label="Error fetching data", state="error")
            st.error(f"Error: {e}")
            st.stop()

    # Show stat cards
    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        show_fighter_card(f1_data)
    with col2:
        show_fighter_card(f2_data)

    # Stream Claude analysis
    st.divider()
    st.markdown("## ⚡ AI Analysis")
    try:
        st.write_stream(stream_analysis(f1_data, f2_data))
    except anthropic.AuthenticationError:
        st.error("Invalid Anthropic API key. Check your Streamlit secrets.")
    except Exception as e:
        st.error(f"Analysis error: {e}")
