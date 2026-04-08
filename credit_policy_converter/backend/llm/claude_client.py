"""
Claude API client for extracting credit policy rules from document sections.
Uses claude-opus-4-6 with adaptive thinking.
"""
import json
import os
import re
from typing import Any, Dict, List

import anthropic

from .prompts import (
    get_classify_sections_prompt,
    get_eligibility_prompt,
    get_go_no_go_prompt,
    get_scorecard_prompt,
    get_surrogate_policy_prompt,
)


class ClaudeClient:
    def __init__(self, api_key: str = "") -> None:
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "No Anthropic API key provided. Set ANTHROPIC_API_KEY in .env "
                "or supply it via the UI settings."
            )
        self.client = anthropic.AsyncAnthropic(api_key=resolved_key)
        self.model = "claude-opus-4-6"

    # ─────────────────────────────────────────────────────────────────
    # Core API call
    # ─────────────────────────────────────────────────────────────────

    async def _call(self, prompt: str, max_tokens: int = 4096) -> str:
        """Send a prompt to Claude and return the text response."""
        # Extended thinking: budget_tokens must be < max_tokens.
        # Use 40% of max_tokens as the thinking budget (min 1024).
        thinking_budget = max(1024, int(max_tokens * 0.4))
        effective_max = thinking_budget + max_tokens  # total token envelope

        try:
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=effective_max,
                thinking={"type": "enabled", "budget_tokens": thinking_budget},
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception:
            # Fallback: call without extended thinking
            response = await self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )

        return next((b.text for b in response.content if b.type == "text"), "")

    # ─────────────────────────────────────────────────────────────────
    # JSON extraction helpers
    # ─────────────────────────────────────────────────────────────────

    def _parse_json(self, text: str) -> Any:
        """Robustly extract JSON from an LLM response."""
        text = text.strip()

        # 1. Direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 2. Markdown code block
        for pattern in [r"```json\s*([\s\S]+?)\s*```", r"```\s*([\s\S]+?)\s*```"]:
            m = re.search(pattern, text)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass

        # 3. First JSON array
        m = re.search(r"(\[[\s\S]+\])", text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        # 4. First JSON object
        m = re.search(r"(\{[\s\S]+\})", text)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass

        return []

    # ─────────────────────────────────────────────────────────────────
    # Name-based section classification fallback
    # ─────────────────────────────────────────────────────────────────

    def _classify_by_name(self, sections: List[Dict]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for s in sections:
            nl = s["name"].lower()
            if any(k in nl for k in ["go no go", "go/no", "gng", "go_no_go"]):
                result[s["name"]] = "go_no_go"
            elif "surrogate" in nl:
                result[s["name"]] = "surrogate_policy"
            elif "eligib" in nl and "surrogate" not in nl:
                result[s["name"]] = "eligibility"
            elif any(k in nl for k in ["scorecard", "score card"]):
                result[s["name"]] = "scorecard"
            elif any(k in nl for k in ["change", "history", "log", "version"]):
                result[s["name"]] = "change_history"
            elif any(k in nl for k in ["pre-read", "pre_read", "preread", "pre read", "introduction"]):
                result[s["name"]] = "pre_read"
            elif any(k in nl for k in ["exposure", "limit"]):
                result[s["name"]] = "exposure"
            elif any(k in nl for k in ["common", "shared"]):
                result[s["name"]] = "common_rules"
            else:
                result[s["name"]] = "metadata"
        return result

    # ─────────────────────────────────────────────────────────────────
    # Main extraction pipeline
    # ─────────────────────────────────────────────────────────────────

    async def extract_all_sections(self, sections: List[Dict]) -> Dict[str, Any]:
        """
        Classify sections and extract rules / expressions from each.

        Returns:
            {
                "go_no_go_rules": [...],
                "surrogate_rules": [...],
                "eligibility_expressions": [...],
                "scorecard_expressions": [...],
            }
        """
        result: Dict[str, Any] = {
            "go_no_go_rules": [],
            "surrogate_rules": [],
            "eligibility_expressions": [],
            "scorecard_expressions": [],
        }

        # Step 1 — classify sections
        summary_lines = []
        for s in sections:
            h_preview = ", ".join(str(h) for h in s.get("headers", [])[:6])
            summary_lines.append(
                f"- {s['name']}: {s.get('row_count', 0)} rows"
                + (f", headers: {h_preview}" if h_preview else "")
            )

        try:
            classify_resp = await self._call(
                get_classify_sections_prompt("\n".join(summary_lines)), max_tokens=1024
            )
            section_types = self._parse_json(classify_resp)
            if not isinstance(section_types, dict):
                section_types = self._classify_by_name(sections)
        except Exception:
            section_types = self._classify_by_name(sections)

        # Step 2 — process each section
        skip_types = {"metadata", "pre_read", "change_history", "exposure"}

        for section in sections:
            name = section["name"]
            stype = section_types.get(name, "metadata")
            text = section.get("text", "")

            if not text or stype in skip_types:
                continue

            # Truncate to avoid exceeding context limits
            text = text[:8000]

            try:
                if stype == "go_no_go":
                    raw = await self._call(get_go_no_go_prompt(text), max_tokens=4096)
                    rules = self._parse_json(raw)
                    if isinstance(rules, list):
                        result["go_no_go_rules"].extend(rules)

                elif stype == "surrogate_policy":
                    raw = await self._call(get_surrogate_policy_prompt(text), max_tokens=4096)
                    rules = self._parse_json(raw)
                    if isinstance(rules, list):
                        result["surrogate_rules"].extend(rules)

                elif stype == "eligibility":
                    raw = await self._call(get_eligibility_prompt(text), max_tokens=4096)
                    exprs = self._parse_json(raw)
                    if isinstance(exprs, list):
                        result["eligibility_expressions"].extend(exprs)

                elif stype == "scorecard":
                    raw = await self._call(get_scorecard_prompt(text), max_tokens=8192)
                    exprs = self._parse_json(raw)
                    if isinstance(exprs, list):
                        result["scorecard_expressions"].extend(exprs)

                elif stype == "common_rules":
                    # Treat shared rules as go_no_go
                    raw = await self._call(get_go_no_go_prompt(text), max_tokens=4096)
                    rules = self._parse_json(raw)
                    if isinstance(rules, list):
                        result["go_no_go_rules"].extend(rules)

            except Exception as exc:
                print(f"[warn] Error processing section '{name}': {exc}")
                continue

        return result
