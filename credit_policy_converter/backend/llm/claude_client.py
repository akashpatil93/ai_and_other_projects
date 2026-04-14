"""
Claude API client for extracting credit policy rules from document sections.
Uses claude-opus-4-6 with adaptive thinking.
"""
import json
import re
from typing import Any, Dict, List

import anthropic

from .prompts import (
    BUREAU_CATEGORY_DESCRIPTIONS,
    get_bureau_ruleset_prompt,
    get_classify_sections_prompt,
    get_eligibility_prompt,
    get_go_no_go_prompt,
    get_modelset_prompt,
    get_scorecard_prompt,
    get_surrogate_policy_prompt,
)

# Section types that map to named bureau-category rulesets
BUREAU_CATEGORY_TYPES = set(BUREAU_CATEGORY_DESCRIPTIONS.keys())


class ClaudeClient:
    def __init__(self, api_key: str = "") -> None:
        if not api_key:
            raise ValueError(
                "No Anthropic API key provided. Enter your key via the app UI."
            )
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
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
    # Helpers
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Convert a section heading into a valid snake_case node name.

        "Go No Go Checks"  → "go_no_go_checks"
        "DPD Rules Q1"     → "dpd_rules_q1"
        """
        import re as _re
        name = name.lower().strip()
        name = _re.sub(r'[^a-z0-9]+', '_', name)
        name = name.strip('_')
        return name or "policy_checks"

    # ─────────────────────────────────────────────────────────────────
    # Name-based section classification fallback
    # ─────────────────────────────────────────────────────────────────

    def _classify_by_name(self, sections: List[Dict]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for s in sections:
            nl = s["name"].lower()
            if any(k in nl for k in ["dpd", "days past due"]):
                result[s["name"]] = "dpd_checks"
            elif any(k in nl for k in ["bureau score", "cibil score", "credit score", "score check",
                                        "individual bureau", "bureau check"]):
                result[s["name"]] = "bureau_score_checks"
            elif any(k in nl for k in ["outstanding", "overdue", "balance"]):
                result[s["name"]] = "outstanding_balance_checks"
            elif any(k in nl for k in ["enquir", "inquiry"]):
                result[s["name"]] = "enquiry_checks"
            elif any(k in nl for k in ["written off", "write off", "written-off", "settlement", "dbt", "lss"]):
                result[s["name"]] = "written_off_settlement_checks"
            elif any(k in nl for k in ["suit filed", "wilful", "default flag"]):
                result[s["name"]] = "delinquency_flag_checks"
            elif any(k in nl for k in ["credit card", "cc check"]):
                result[s["name"]] = "credit_card_checks"
            elif any(k in nl for k in ["new account", "account opening", "account count"]):
                result[s["name"]] = "account_opening_checks"
            elif any(k in nl for k in ["go no go", "go/no", "gng", "go_no_go"]):
                result[s["name"]] = "go_no_go"
            elif "surrogate" in nl:
                result[s["name"]] = "surrogate_policy"
            elif "eligib" in nl and "surrogate" not in nl:
                result[s["name"]] = "eligibility"
            elif any(k in nl for k in ["scorecard", "score card"]):
                result[s["name"]] = "scorecard"
            elif any(k in nl for k in ["change", "history", "log", "version"]):
                result[s["name"]] = "change_history"
            elif any(k in nl for k in ["pre-read", "pre_read", "preread", "pre read",
                                        "introduction", "input payload", "1.1 "]):
                result[s["name"]] = "pre_read"
            elif any(k in nl for k in ["exposure", "limit"]):
                result[s["name"]] = "exposure"
            elif any(k in nl for k in ["common", "shared"]):
                result[s["name"]] = "common_rules"
            # Explicit skip types
            elif any(k in nl for k in ["change history", "version history", "revision"]):
                result[s["name"]] = "change_history"
            else:
                # For policy documents, unknown sections are most likely rule sections.
                # Default to go_no_go so they are extracted rather than silently dropped.
                result[s["name"]] = "go_no_go"
        return result

    # ─────────────────────────────────────────────────────────────────
    # Main extraction pipeline
    # ─────────────────────────────────────────────────────────────────

    async def extract_all_sections(self, sections: List[Dict], context: str = "") -> Dict[str, Any]:
        """
        Classify sections and extract rules / expressions from each.

        Args:
            sections: Parsed document sections.
            context:  Optional free-text context from the user (e.g. loan type,
                      key thresholds, special instructions) injected into every
                      extraction prompt so Claude can follow specific guidance.

        Returns:
            {
                "go_no_go_rules": [...],          # backward-compat generic go/no-go rules
                "surrogate_rules": [...],
                "eligibility_expressions": [...],
                "scorecard_expressions": [...],
                "named_rulesets": [               # categorized bureau rulesets (preferred)
                    {"name": "dpd_checks", "rules": [...]},
                    {"name": "bureau_score_checks", "rules": [...]},
                    ...
                ],
            }
        """
        result: Dict[str, Any] = {
            "go_no_go_rules": [],
            "surrogate_rules": [],
            "eligibility_expressions": [],
            "scorecard_expressions": [],
            "named_rulesets": [],
            "named_modelsets": [],
        }

        # Accumulate rules per named ruleset (maintains insertion order)
        named_ruleset_map: Dict[str, List[Dict]] = {}
        named_modelset_map: Dict[str, List[Dict]] = {}

        # Build context prefix to prepend to every extraction prompt
        context_block = (
            f"\n\nUSER-PROVIDED CONTEXT (follow these instructions while extracting rules):\n{context.strip()}\n"
            if context and context.strip()
            else ""
        )

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

            def _inject(prompt: str) -> str:
                """Append the user context block to a prompt string."""
                return prompt + context_block

            # Ruleset key = sanitized section heading (e.g. "DPD Rules" → "dpd_rules")
            rs_key = self._sanitize_name(name)

            try:
                if stype in BUREAU_CATEGORY_TYPES or stype in {"go_no_go", "surrogate_policy", "common_rules"}:
                    # Pick the right extraction prompt based on section type
                    if stype in BUREAU_CATEGORY_TYPES:
                        prompt = get_bureau_ruleset_prompt(text, stype)
                    elif stype == "surrogate_policy":
                        prompt = get_surrogate_policy_prompt(text)
                    else:
                        prompt = get_go_no_go_prompt(text)

                    raw = await self._call(_inject(prompt), max_tokens=4096)
                    rules = self._parse_json(raw)
                    if isinstance(rules, list) and rules:
                        named_ruleset_map.setdefault(rs_key, []).extend(rules)

                elif stype == "modelset":
                    raw = await self._call(_inject(get_modelset_prompt(text, rs_key)), max_tokens=16384)
                    exprs = self._parse_json(raw)
                    if isinstance(exprs, list) and exprs:
                        named_modelset_map.setdefault(rs_key, []).extend(exprs)

                elif stype == "eligibility":
                    raw = await self._call(_inject(get_eligibility_prompt(text)), max_tokens=16384)
                    exprs = self._parse_json(raw)
                    if isinstance(exprs, list):
                        result["eligibility_expressions"].extend(exprs)

                elif stype == "scorecard":
                    raw = await self._call(_inject(get_scorecard_prompt(text)), max_tokens=16384)
                    exprs = self._parse_json(raw)
                    if isinstance(exprs, list):
                        result["scorecard_expressions"].extend(exprs)

            except Exception as exc:
                print(f"[warn] Error processing section '{name}': {exc}")
                continue

        # Build ordered lists from accumulated maps
        result["named_rulesets"] = [
            {"name": rs_name, "rules": rules}
            for rs_name, rules in named_ruleset_map.items()
        ]
        result["named_modelsets"] = [
            {"name": ms_name, "expressions": exprs}
            for ms_name, exprs in named_modelset_map.items()
        ]

        return result
