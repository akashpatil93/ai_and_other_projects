"""
Claude API client for extracting credit policy rules from document sections.
Uses claude-opus-4-6 with adaptive thinking.
"""
import asyncio
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
        # Strip leading numeric prefix (e.g. "1_core_..." → "core_...")
        name = _re.sub(r'^\d+_', '', name)
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
                result[s["name"]] = "modelset"
            elif any(k in nl for k in ["offer decision", "offer calc", "offer table",
                                        "warranty", "product offer", "rate card", "fee table",
                                        "pricing", "credit strategy decision", "interest rate matrix"]):
                result[s["name"]] = "modelset"
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
        print(f"[debug] extract_all_sections: {len(sections)} sections")
        for s in sections:
            print(f"[debug]   section: '{s['name']}' ({s.get('row_count', 0)} rows, {len(s.get('text',''))} chars)")

        # Single-section PDF/DOCX fallback: the parser returned the whole document as one
        # unnamed section. Bypass LLM classification — the section name ("Policy Document"
        # or "Document") looks like metadata to the classifier, causing it to be skipped.
        is_single_fallback = (
            len(sections) == 1
            and sections[0]["name"] in ("Policy Document", "Document")
        )

        if is_single_fallback:
            section_types = {sections[0]["name"]: "go_no_go"}
            print(f"[debug] single-fallback section — forcing go_no_go, skipping classify call")
        else:
            summary_lines = []
            for s in sections:
                h_preview = ", ".join(str(h) for h in s.get("headers", [])[:6])
                summary_lines.append(
                    f"- {s['name']}: {s.get('row_count', 0)} rows"
                    + (f", headers: {h_preview}" if h_preview else "")
                )
            try:
                classify_resp = await self._call(
                    get_classify_sections_prompt("\n".join(summary_lines)), max_tokens=2048
                )
                raw_types = self._parse_json(classify_resp)
                if not isinstance(raw_types, dict):
                    print(f"[debug] classify LLM returned non-dict, using name-based fallback")
                    section_types = self._classify_by_name(sections)
                else:
                    print(f"[debug] classify LLM result: {raw_types}")
                    raw_lower = {k.lower().strip(): v for k, v in raw_types.items()}
                    section_types = {
                        s["name"]: raw_types.get(
                            s["name"],
                            raw_lower.get(s["name"].lower().strip(), "")
                        )
                        for s in sections
                    }
                    name_fallback = self._classify_by_name(sections)
                    for s in sections:
                        if not section_types.get(s["name"]):
                            section_types[s["name"]] = name_fallback.get(s["name"], "go_no_go")
            except Exception as e:
                print(f"[debug] classify failed ({e}), using name-based fallback")
                section_types = self._classify_by_name(sections)

        print(f"[debug] final section_types: {section_types}")

        # Step 2 — process all sections in parallel (semaphore caps concurrency at 5)
        skip_types = {"metadata", "pre_read", "change_history"}

        # ~24k chars ≈ 6k tokens — well within Claude's context window
        MAX_SECTION_CHARS = 24_000

        semaphore = asyncio.Semaphore(5)

        async def _process_section(section: Dict) -> Dict:
            name = section["name"]
            stype = section_types.get(name, "go_no_go")
            text = section.get("text", "")

            if not text or stype in skip_types:
                return {}

            text = text[:MAX_SECTION_CHARS]
            rs_key = self._sanitize_name(name)

            def _inject(prompt: str) -> str:
                return prompt + context_block

            async with semaphore:
                try:
                    if stype in BUREAU_CATEGORY_TYPES or stype in {"go_no_go", "surrogate_policy", "common_rules"}:
                        if stype in BUREAU_CATEGORY_TYPES:
                            prompt = get_bureau_ruleset_prompt(text, stype)
                        elif stype == "surrogate_policy":
                            prompt = get_surrogate_policy_prompt(text)
                        else:
                            prompt = get_go_no_go_prompt(text)
                        raw = await self._call(_inject(prompt), max_tokens=4096)
                        rules = self._parse_json(raw)
                        print(f"[debug] section '{name}' (type={stype}): Claude returned {type(rules).__name__} len={len(rules) if isinstance(rules, list) else 'N/A'}")
                        if isinstance(rules, list) and rules:
                            # Single-fallback: also extract eligibility from the same text so
                            # offer/FOIR computations aren't silently dropped.
                            if is_single_fallback and len(text) > 4000:
                                try:
                                    elig_raw = await self._call(_inject(get_eligibility_prompt(text)), max_tokens=16384)
                                    elig_exprs = self._parse_json(elig_raw)
                                    if isinstance(elig_exprs, list) and elig_exprs:
                                        print(f"[debug] single-fallback eligibility: {len(elig_exprs)} expressions")
                                        return {"type": "ruleset_with_eligibility", "key": rs_key, "data": rules, "eligibility": elig_exprs}
                                except Exception as elig_exc:
                                    print(f"[warn] single-fallback eligibility extraction failed: {elig_exc}")
                            return {"type": "ruleset", "key": rs_key, "data": rules}

                    elif stype == "modelset":
                        raw = await self._call(_inject(get_modelset_prompt(text, rs_key)), max_tokens=16384)
                        exprs = self._parse_json(raw)
                        print(f"[debug] section '{name}' (type=modelset): Claude returned {type(exprs).__name__} len={len(exprs) if isinstance(exprs, list) else 'N/A'}")
                        if isinstance(exprs, list) and exprs:
                            return {"type": "modelset", "key": rs_key, "data": exprs}

                    elif stype == "eligibility":
                        raw = await self._call(_inject(get_eligibility_prompt(text)), max_tokens=16384)
                        exprs = self._parse_json(raw)
                        print(f"[debug] section '{name}' (type=eligibility): Claude returned {type(exprs).__name__} len={len(exprs) if isinstance(exprs, list) else 'N/A'}")
                        if isinstance(exprs, list):
                            return {"type": "eligibility", "data": exprs}

                    elif stype == "scorecard":
                        raw = await self._call(_inject(get_scorecard_prompt(text)), max_tokens=16384)
                        exprs = self._parse_json(raw)
                        print(f"[debug] section '{name}' (type=scorecard): Claude returned {type(exprs).__name__} len={len(exprs) if isinstance(exprs, list) else 'N/A'}")
                        if isinstance(exprs, list):
                            return {"type": "scorecard", "data": exprs}

                    else:
                        print(f"[debug] section '{name}' (type={stype}): SKIPPED (no handler)")

                except Exception as exc:
                    print(f"[warn] Error processing section '{name}': {exc}")

            return {}

        # Fire all sections concurrently; gather preserves list order (important for rulesets)
        section_results = await asyncio.gather(
            *[_process_section(s) for s in sections],
            return_exceptions=False,
        )

        for res in section_results:
            if not res:
                continue
            t = res["type"]
            if t in ("ruleset", "ruleset_with_eligibility"):
                named_ruleset_map.setdefault(res["key"], []).extend(res["data"])
                if t == "ruleset_with_eligibility":
                    result["eligibility_expressions"].extend(res["eligibility"])
            elif t == "modelset":
                named_modelset_map.setdefault(res["key"], []).extend(res["data"])
            elif t == "eligibility":
                result["eligibility_expressions"].extend(res["data"])
            elif t == "scorecard":
                result["scorecard_expressions"].extend(res["data"])

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
