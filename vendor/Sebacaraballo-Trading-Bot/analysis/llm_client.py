"""
analysis/llm_client.py
----------------------
Anthropic Claude API client for earnings signal extraction.

Model:   claude-haiku-4-5-20251001  (~$0.01/filing at 4 000-word exhibits)
Cost:    $0.80 / M input tokens | $4.00 / M output tokens
Caching: System prompt is marked ephemeral — 90 % discount on cache hits.

Setup:
  1. Create a .env file with:  ANTHROPIC_API_KEY=sk-ant-...
  2. python-dotenv loads it automatically on import.

Structured output strategy:
  We ask the model to return raw JSON (no markdown fences).  If the model
  wraps the output in a code block anyway, the parser strips it with a
  regex fallback before raising.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

import anthropic
from dotenv import load_dotenv

from analysis.prompt import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL = "claude-haiku-4-5-20251001"
_MAX_WORDS = 4_000        # Truncate exhibit before sending (cost control)
_MAX_TOKENS = 1_024       # JSON signal is ~300-500 tokens; 1k gives headroom

# Valid enum values (used for defensive normalisation)
_VALID_SENTIMENT = {"bullish", "bearish", "neutral"}
_VALID_GUIDANCE  = {"raised", "maintained", "lowered", "withdrawn", "none"}
_VALID_TONE      = {"optimistic", "cautious", "defensive", "neutral"}


# ---------------------------------------------------------------------------
# Signal dataclass
# ---------------------------------------------------------------------------

@dataclass
class EarningsSignal:
    """
    Structured trading signal extracted from an earnings press release.

    All nullable ``bool`` fields use ``None`` when the information is not
    available in the filing (e.g. no consensus estimates were mentioned).
    """

    # ── Core signal ──────────────────────────────────────────────────────
    sentiment: str                 # "bullish" | "bearish" | "neutral"
    confidence: float              # 0.0–1.0
    guidance_quality: str          # "raised" | "maintained" | "lowered" | "withdrawn" | "none"
    eps_beat: Optional[bool]       # True = beat, False = miss, None = unknown
    revenue_beat: Optional[bool]
    management_tone: str           # "optimistic" | "cautious" | "defensive" | "neutral"
    risk_flags: list[str]          # e.g. ["margin compression", "macro headwinds"]
    bull_case: str                 # One sentence
    bear_case: str                 # One sentence
    reasoning: str                 # 2-3 sentences

    # ── API metadata ─────────────────────────────────────────────────────
    model: str = _MODEL
    prompt_tokens: int = 0
    completion_tokens: int = 0
    raw_response: str = ""

    # ── Derived ──────────────────────────────────────────────────────────
    @property
    def direction(self) -> str:
        """Map sentiment → DB direction enum (LONG / SHORT / NEUTRAL)."""
        return {
            "bullish": "LONG",
            "bearish": "SHORT",
            "neutral": "NEUTRAL",
        }.get(self.sentiment, "NEUTRAL")


# ---------------------------------------------------------------------------
# LLM client
# ---------------------------------------------------------------------------

class LLMClient:
    """
    Thin wrapper around the Anthropic Python SDK for earnings analysis.

    Args:
        api_key: Anthropic API key.  Falls back to ``ANTHROPIC_API_KEY``
                 environment variable (loaded from ``.env`` via dotenv).
    """

    def __init__(self, api_key: Optional[str] = None) -> None:
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set.\n"
                "  1. Go to https://console.anthropic.com/settings/keys\n"
                "  2. Create an API key\n"
                "  3. Add it to a .env file:  ANTHROPIC_API_KEY=sk-ant-...\n"
            )
        self._client = anthropic.Anthropic(api_key=key)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_exhibit(
        self,
        ticker: str,
        filing_date: str,
        exhibit_text: str,
    ) -> EarningsSignal:
        """
        Send an earnings press release to Claude and return a structured signal.

        The exhibit text is truncated to ``_MAX_WORDS`` before sending.
        The system prompt uses prompt caching (ephemeral) to reduce cost
        on repeated calls within the same 5-minute cache window.

        Args:
            ticker:       Stock ticker (e.g. ``"AAPL"``).
            filing_date:  ISO date string of the 8-K filing.
            exhibit_text: Cleaned plain text of Exhibit 99.1.

        Returns:
            Populated :class:`EarningsSignal`.

        Raises:
            ValueError:          If the response cannot be parsed as JSON.
            anthropic.APIError:  On API-level failures (caller should handle).
        """
        truncated = self._truncate(exhibit_text, ticker)

        user_prompt = USER_PROMPT_TEMPLATE.format(
            ticker=ticker,
            filing_date=filing_date,
            exhibit_text=truncated,
        )

        logger.info(
            "Calling %s for %s filing %s (%d words)",
            _MODEL, ticker, filing_date, len(truncated.split()),
        )

        response = self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            # System prompt with prompt caching — major cost saving on repeated calls
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_prompt}],
        )

        raw_text = response.content[0].text
        usage = response.usage

        logger.debug(
            "Usage: %d prompt tokens (%d cached), %d completion tokens",
            usage.input_tokens,
            getattr(usage, "cache_read_input_tokens", 0),
            usage.output_tokens,
        )

        data = self._parse_json(raw_text, ticker)
        return self._build_signal(data, response)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _truncate(text: str, ticker: str) -> str:
        """Truncate text to _MAX_WORDS, logging if truncation occurs."""
        words = text.split()
        if len(words) <= _MAX_WORDS:
            return text
        logger.debug(
            "Truncating exhibit text from %d → %d words for %s",
            len(words), _MAX_WORDS, ticker,
        )
        return " ".join(words[:_MAX_WORDS]) + "\n\n[... text truncated at 4 000 words ...]"

    @staticmethod
    def _parse_json(raw_text: str, ticker: str) -> dict:
        """
        Parse JSON from the raw LLM response.

        Handles two cases:
          1. Clean JSON string (expected).
          2. JSON wrapped in markdown fences (fallback).

        Raises:
            ValueError: If no valid JSON object can be extracted.
        """
        text = raw_text.strip()

        # Fast path: direct JSON parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Fallback: extract first {...} block (handles ```json ... ``` wrapping)
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        raise ValueError(
            f"Could not parse LLM response as JSON for {ticker}.\n"
            f"Raw (first 500 chars): {raw_text[:500]}"
        )

    @staticmethod
    def _build_signal(data: dict, response: anthropic.types.Message) -> EarningsSignal:
        """
        Construct an :class:`EarningsSignal` from parsed JSON + API metadata.

        Applies defensive normalisation: unknown enum values fall back to
        ``"neutral"`` / ``"none"`` rather than propagating bad data.
        """
        usage = response.usage

        sentiment = data.get("sentiment", "neutral").lower()
        if sentiment not in _VALID_SENTIMENT:
            sentiment = "neutral"

        guidance = data.get("guidance_quality", "none").lower()
        if guidance not in _VALID_GUIDANCE:
            guidance = "none"

        tone = data.get("management_tone", "neutral").lower()
        if tone not in _VALID_TONE:
            tone = "neutral"

        # eps_beat / revenue_beat: accept true/false/null
        def _bool_or_none(val) -> Optional[bool]:
            if val is None:
                return None
            return bool(val)

        return EarningsSignal(
            sentiment=sentiment,
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
            guidance_quality=guidance,
            eps_beat=_bool_or_none(data.get("eps_beat")),
            revenue_beat=_bool_or_none(data.get("revenue_beat")),
            management_tone=tone,
            risk_flags=list(data.get("risk_flags", [])),
            bull_case=str(data.get("bull_case", "")),
            bear_case=str(data.get("bear_case", "")),
            reasoning=str(data.get("reasoning", "")),
            model=response.model,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            raw_response=response.content[0].text,
        )
