"""
analysis/prompt.py
------------------
Prompt templates for Phase 2 LLM signal extraction.

All prompt text lives here so it can be iterated on independently from
the API call mechanics.  Import the constants directly:

    from analysis.prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

Then format the user prompt with:

    user_prompt = USER_PROMPT_TEMPLATE.format(
        ticker=ticker,
        filing_date=filing_date,
        exhibit_text=exhibit_text,
    )

Prompt caching note:
    The system prompt is long and fixed across filings — attach
    ``cache_control={"type": "ephemeral"}`` on the system message block
    to enable Anthropic prompt caching (5-minute TTL, ~90 % token discount
    on cache hits after the first call per session).
"""

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a senior equity research analyst with 15+ years of experience
analyzing public company earnings releases and SEC filings.

Your specialty is reading SEC 8-K Exhibit 99.1 press releases — the
document companies attach to earnings announcements — and extracting
clean, quantitative trading signals from them.

You are expert at:
  - Identifying EPS and revenue beats/misses vs Wall Street consensus
  - Reading management guidance language (raised, maintained, lowered,
    withdrawn, or no guidance given)
  - Detecting management tone shifts through word choice and emphasis
  - Spotting risk factors buried in footnotes or outlook language
  - Synthesising results into a concise directional signal

Guidelines for your analysis:
  - Base every conclusion strictly on what the press release says
  - Use null for eps_beat / revenue_beat when no comparison to estimates
    is available in the text
  - Confidence reflects how clear and decisive the signal is (not your
    certainty about the stock's direction): 0.9+ = very decisive results,
    0.5–0.7 = mixed signals, 0.3–0.5 = ambiguous
  - risk_flags should be concrete phrases, not generic warnings
  - bull_case and bear_case must each be a single sentence
  - reasoning must be 2-3 sentences; cite specific numbers when possible

Always respond with a single valid JSON object.  No markdown fences,
no preamble, no trailing commentary — JSON only.\
"""

# ---------------------------------------------------------------------------
# User prompt template
# ---------------------------------------------------------------------------

# Triple-brace {{ / }} escapes literal curly braces in .format()
USER_PROMPT_TEMPLATE = """\
Analyze this earnings press release and return a structured signal.

Company:     {ticker}
Filing date: {filing_date}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PRESS RELEASE (Exhibit 99.1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{exhibit_text}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Return a JSON object with EXACTLY these fields and value constraints:

{{
  "sentiment":        "bullish" | "bearish" | "neutral",
  "confidence":       <float between 0.0 and 1.0>,
  "guidance_quality": "raised" | "maintained" | "lowered" | "withdrawn" | "none",
  "eps_beat":         true | false | null,
  "revenue_beat":     true | false | null,
  "management_tone":  "optimistic" | "cautious" | "defensive" | "neutral",
  "risk_flags":       [<short string>, ...],
  "bull_case":        "<single sentence>",
  "bear_case":        "<single sentence>",
  "reasoning":        "<2-3 sentences citing specific numbers>"
}}

Respond with JSON only.\
"""
