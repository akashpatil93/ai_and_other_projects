"""
Assembles the complete workflow JSON from extracted credit policy data.
Implements the standard flow:
  Start → DataSource(bureau) → [scorecard] → model
        → [muted_go_no_go] → [go_no_go]
        → [muted_surrogate] → [surrogate]
        → final_decision → [eligibility] → approved / rejected
"""
import re
import uuid
from typing import Any, Dict, List

# Fixed names for terminal nodes so switch nodes can reference them by name
END_APPROVED = "end_approved"
END_REJECTED = "end_rejected"


def _uuid() -> str:
    return str(uuid.uuid4())


# ─────────────────────────────────────────────────────────────────────────────
# Node builders
# ─────────────────────────────────────────────────────────────────────────────

def _has_cant_decide(rules: List[Dict]) -> bool:
    return any(r.get("cantDecideCondition", "").strip() for r in rules)


def _ruleset(name: str, x: int, y: int, rules: List[Dict], switch_name: str) -> Dict:
    rule_objs = [
        {
            "name": r.get("name", f"Rule_{i + 1}"),
            "id": _uuid(),
            "seqNo": i,
            "approveCondition": r.get("approveCondition", "true"),
            "cantDecideCondition": r.get("cantDecideCondition", ""),
            "muted": _is_muted(r),
            "tag": _uuid(),
        }
        for i, r in enumerate(rules)
    ]
    return {
        "type": "ruleSet",
        "name": name,
        "tag": _uuid(),
        "rules": rule_objs,
        "metadata": {"x": x, "y": y, "nodeColor": 1},
        "nextState": {"type": "switch", "name": switch_name},
    }


_EMPTY_DT: Dict[str, Any] = {"default": "", "headers": None, "rows": None}
_EMPTY_MATRIX: Dict[str, Any] = {
    "globalRowIndex": 0,
    "globalColumnIndex": 0,
    "rows": None,
    "columns": None,
    "values": None,
}


def _modelset(name: str, x: int, y: int, expressions: List[Dict], next_state: Dict) -> Dict:
    expr_objs = []
    for i, expr in enumerate(expressions):
        etype = expr.get("type", "expression")

        if etype == "matrix":
            obj: Dict[str, Any] = {
                "name": expr.get("name", f"expr_{i}"),
                "id": _uuid(),
                "seqNo": i,
                "condition": "",
                "type": "matrix",
                "decisionTableRules": _EMPTY_DT.copy(),
                "matrix": expr.get("matrix", _EMPTY_MATRIX.copy()),
                "tag": _uuid(),
            }

        elif etype == "decisionTable":
            obj = {
                "name": expr.get("name", f"expr_{i}"),
                "id": _uuid(),
                "seqNo": i,
                "condition": "",
                "type": "decisionTable",
                "decisionTableRules": expr.get("decisionTableRules", _EMPTY_DT.copy()),
                "matrix": _EMPTY_MATRIX.copy(),
                "tag": _uuid(),
            }

        else:  # expression
            obj = {
                "name": expr.get("name", f"expr_{i}"),
                "id": _uuid(),
                "seqNo": i,
                "condition": expr.get("condition", ""),
                "type": "expression",
                "decisionTableRules": _EMPTY_DT.copy(),
                "matrix": _EMPTY_MATRIX.copy(),
                "tag": _uuid(),
            }

        expr_objs.append(obj)

    return {
        "type": "modelSet",
        "name": name,
        "tag": _uuid(),
        "expressions": expr_objs,
        "metadata": {"x": x, "y": y, "nodeColor": 1},
        "nextState": next_state,
    }


def _switch(name: str, conditions: List[Dict]) -> Dict:
    return {"type": "switch", "name": name, "dataConditions": conditions}


# ─────────────────────────────────────────────────────────────────────────────
# Main assembler
# ─────────────────────────────────────────────────────────────────────────────

def _is_muted(rule: Dict) -> bool:
    """Type-safe muted check — handles bool, string 'true'/'false', int, or missing."""
    val = rule.get("muted", False)
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    return bool(val)


def assemble_workflow(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Build the complete workflow JSON from Claude-extracted data."""

    # ── Build the ordered list of rulesets ───────────────────────────
    # Each entry: {"name": str, "rules": [...all rules including muted ones...]}
    # Muted rules are identified by muted=true on the individual rule object —
    # no separate muted_<name> nodes are created.
    raw_named = extracted.get("named_rulesets", [])
    all_rulesets: List[Dict] = [
        {"name": rs.get("name", "bureau_checks"), "rules": rs.get("rules", [])}
        for rs in raw_named
        if rs.get("rules")
    ]

    # Backward-compat: absorb any generic go_no_go / surrogate rules
    all_gng = extracted.get("go_no_go_rules", [])
    if all_gng:
        all_rulesets.append({"name": "go_no_go_checks", "rules": all_gng})

    all_sp = extracted.get("surrogate_rules", [])
    if all_sp:
        all_rulesets.append({"name": "surrogate_policy_checks", "rules": all_sp})

    elig_exprs = extracted.get("eligibility_expressions", [])
    scorecard_exprs = extracted.get("scorecard_expressions", [])

    # For the final_decision approve condition, a ruleset "counts" only if it
    # has at least one non-muted rule.
    def _has_active_rules(rs: Dict) -> bool:
        return any(not _is_muted(r) for r in rs.get("rules", []))

    # ── Layout constants ──────────────────────────────────────────────
    # Switch nodes are invisible routing nodes — they carry no metadata.
    # All visible nodes sit on a horizontal rail (Y_MAIN) with per-column
    # widths computed from content so cards never overlap.
    #
    # BRE card widths (approximate pixels):
    #   start / end / dataSource  → 200 px  (narrow, fixed)
    #   modelSet / branch         → 300 px  (medium, fixed)
    #   ruleSet                   → 300 px base + 3 px per rule (cards
    #                               grow in width when rules overflow
    #                               horizontally in some BRE versions)
    #
    # We add a fixed H_GAP gutter between every pair of adjacent nodes.

    H_GAP        = 120   # minimum clear pixels between adjacent card edges
    BASE_NARROW  = 200   # start, end, dataSource
    BASE_MEDIUM  = 300   # modelSet, branch
    BASE_RULESET = 300   # ruleSet base width
    RULE_EXTRA   = 3     # extra px per rule in a ruleSet

    Y_MAIN     = 0
    Y_APPROVED = -320   # end_approved: well above main rail
    Y_REJECTED =  320   # end_rejected: well below main rail

    # x cursor — advances by (card_width + H_GAP) after each visible node
    x_cursor = 0

    def place(card_width: int) -> int:
        """Return the x for the current node, then advance x_cursor."""
        nonlocal x_cursor
        pos = x_cursor
        x_cursor += card_width + H_GAP
        return pos

    def ruleset_width(rule_list: List[Dict]) -> int:
        return BASE_RULESET + RULE_EXTRA * len(rule_list)

    nodes: List[Dict] = []

    # ── 1. Start  (x=0, y=0) ─────────────────────────────────────────
    datasource_name = "Source_Node"
    nodes.append({
        "type": "start",
        "name": "Start",
        "metadata": {"x": place(BASE_NARROW), "y": Y_MAIN, "nodeColor": 1},
        "nextState": {"name": datasource_name, "type": "dataSource"},
    })

    # ── 3–4. Scorecard + Model modelSets ─────────────────────────────
    # Scan only the approveCondition / cantDecideCondition fields of every extracted
    # rule for explicit cross-node references (model.hit_no_hit, model.age_at_maturity).
    # Searching str(extracted) is too broad — the expression names appear in prompts
    # and rule names, causing the model node to always be emitted.
    def _collect_conditions(obj: Any) -> str:
        """Recursively collect all condition strings from the extracted dict."""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, list):
            return " ".join(_collect_conditions(i) for i in obj)
        if isinstance(obj, dict):
            return " ".join(
                _collect_conditions(v)
                for k, v in obj.items()
                if k in ("approveCondition", "cantDecideCondition", "condition")
            )
        return ""

    _conditions_text = _collect_conditions(extracted)
    _has_bank_vars = bool(re.search(r"\bbank\.", _conditions_text))

    model_exprs = []
    if "model.hit_no_hit" in _conditions_text:
        model_exprs.append(
            {"name": "hit_no_hit", "condition": "bureau.bureauscore != nil", "type": "expression"}
        )
    if "model.age_at_maturity" in _conditions_text:
        model_exprs.append(
            {"name": "age_at_maturity", "condition": "input.age + 3", "type": "expression"}
        )

    def first_after_model() -> Dict:
        if all_rulesets:
            return {"name": all_rulesets[0]["name"], "type": "ruleSet"}
        return {"name": "final_decision", "type": "branch"}

    # What does the dataSource flow into?
    after_datasource = (
        {"name": "scorecard", "type": "modelSet"}
        if scorecard_exprs
        else ({"name": "model", "type": "modelSet"} if model_exprs else first_after_model())
    )

    # What does the last pre-ruleset node (scorecard or model) flow into?
    if model_exprs:
        after_scorecard = {"name": "model", "type": "modelSet"}
    else:
        after_scorecard = first_after_model()

    # ── 2. DataSource — bureau + bank (if needed) in one node ────────
    sources = [{"name": "bureau", "id": 41238, "seqNo": 0, "type": "finboxSource", "tag": _uuid()}]
    if _has_bank_vars:
        sources.append({"name": "bank", "id": 41239, "seqNo": 1, "type": "finboxSource", "tag": _uuid()})

    nodes.append({
        "type": "dataSource",
        "name": datasource_name,
        "tag": _uuid(),
        "sources": sources,
        "metadata": {"x": place(BASE_NARROW), "y": Y_MAIN, "nodeColor": 1},
        "nextState": after_datasource,
    })

    if scorecard_exprs:
        nodes.append(_modelset(
            "scorecard", place(BASE_MEDIUM), Y_MAIN, scorecard_exprs,
            next_state=after_scorecard,
        ))

    if model_exprs:
        nodes.append(_modelset("model", place(BASE_MEDIUM), Y_MAIN, model_exprs, next_state=first_after_model()))

    def _muted_switch(sw_name: str, rules: List[Dict], forward: Dict) -> Dict:
        """Muted ruleSets: pass and reject both continue forward. cantDecide too if present."""
        conditions = [
            {"name": "pass",   "nextState": forward},
            {"name": "reject", "nextState": forward},
        ]
        if _has_cant_decide(rules):
            conditions.append({"name": "cantDecide", "nextState": forward})
        return _switch(sw_name, conditions)

    def _active_switch(sw_name: str, rules: List[Dict], pass_next: Dict) -> Dict:
        """Active ruleSets: pass continues, reject/cantDecide go to end_rejected."""
        conditions = [
            {"name": "pass",   "nextState": pass_next},
            {"name": "reject", "nextState": {"name": END_REJECTED, "type": "end"}},
        ]
        if _has_cant_decide(rules):
            conditions.append({"name": "cantDecide", "nextState": {"name": END_REJECTED, "type": "end"}})
        return _switch(sw_name, conditions)

    # ── 5–8. Chain all rulesets in order ─────────────────────────────
    for i, rs in enumerate(all_rulesets):
        rs_name = rs["name"]
        rules = rs["rules"]
        sw = f"{rs_name}-switch"

        # Determine what comes after this ruleset
        if i + 1 < len(all_rulesets):
            next_node = {"name": all_rulesets[i + 1]["name"], "type": "ruleSet"}
        else:
            next_node = {"name": "final_decision", "type": "branch"}

        nodes.append(_ruleset(rs_name, place(ruleset_width(rules)), Y_MAIN, rules, sw))

        # If all rules in this node are muted it can never truly reject — treat
        # it as a pass-through; otherwise active logic applies.
        if _has_active_rules(rs):
            nodes.append(_active_switch(sw, rules, next_node))
        else:
            nodes.append(_muted_switch(sw, rules, next_node))

    # ── 9. Final Decision branch ──────────────────────────────────────
    fd_sw = "final_decision-switch"
    # Approve condition references only rulesets that have at least one active rule
    parts = [
        f'{rs["name"]}.decision == "pass"'
        for rs in all_rulesets
        if _has_active_rules(rs)
    ]
    approve_cond = " and ".join(parts) if parts else "true"

    nodes.append({
        "type": "branch",
        "name": "final_decision",
        "tag": _uuid(),
        "expressions": [
            {"name": "approve", "id": _uuid(), "seqNo": 0, "condition": approve_cond, "tag": _uuid()},
            {"name": "reject",  "id": _uuid(), "seqNo": 1, "condition": "true",       "tag": _uuid()},
        ],
        "metadata": {"x": place(BASE_MEDIUM), "y": Y_MAIN, "nodeColor": 1},
        "nextState": {"type": "switch", "name": fd_sw},
    })

    approve_path = (
        {"name": "eligibility", "type": "modelSet"}
        if elig_exprs
        else {"name": END_APPROVED, "type": "end"}
    )
    nodes.append(_switch(fd_sw, [
        {"name": "approve", "nextState": approve_path},
        {"name": "reject",  "nextState": {"name": END_REJECTED, "type": "end"}},
    ]))

    # ── 10. Eligibility modelSet ──────────────────────────────────────
    if elig_exprs:
        nodes.append(_modelset(
            "eligibility", place(BASE_MEDIUM), Y_MAIN, elig_exprs,
            next_state={"name": END_APPROVED, "type": "end"},
        ))

    # ── 11. End nodes ─────────────────────────────────────────────────
    # Both end nodes share the same x (final column), offset vertically.
    # decisionNode.output must include every key from the outputs array.
    import json as _json

    outputs = [
        {"name": "decision",      "dataType": "text"},
        {"name": "amount",        "dataType": "number"},
        {"name": "interest_rate", "dataType": "number"},
        {"name": "tenure",        "dataType": "number"},
        {"name": "emi",           "dataType": "number"},
        {"name": "foir",          "dataType": "number"},
    ]

    def _end_output(terminal: str) -> str:
        """Build decisionNode output JSON containing every declared output field."""
        obj: Dict[str, Any] = {}
        for out in outputs:
            if out["name"] == "decision":
                obj["decision"] = terminal          # "approved" or "rejected"
            elif out["dataType"] == "number":
                obj[out["name"]] = 0
            else:
                obj[out["name"]] = ""
        return _json.dumps(obj)

    end_x = x_cursor   # x_cursor already points past the last node
    nodes.append({
        "type": "end",
        "name": END_APPROVED,
        "endNodeName": "approved",
        "tag": _uuid(),
        "decisionNode": {"output": _end_output("approved")},
        "metadata": {"x": end_x, "y": Y_APPROVED, "nodeColor": 3},
    })
    nodes.append({
        "type": "end",
        "name": END_REJECTED,
        "endNodeName": "rejected",
        "tag": _uuid(),
        "decisionNode": {"output": _end_output("rejected")},
        "metadata": {"x": end_x, "y": Y_REJECTED, "nodeColor": 2},
    })

    # ── 12. Build inputs array ────────────────────────────────────────
    inputs = _build_inputs(nodes)

    return {
        "nodes": nodes,
        "inputs": inputs,
        "outputs": outputs,
        "settings": {
            "isNullableInputsAllowed": True,
            "continueEvalWithDataSourceErr": False,
            "isRejectionBasedRulesetEnable": False,
        },
    }


def _build_inputs(nodes: List[Dict]) -> List[Dict]:
    """Scan all node expressions and build the inputs array.

    - input.* variables → scalar inputs (text or number)
    - bank.* variables  → single object input with children (one per referenced field)
    - bureau.* variables come from the dataSource node and are NOT listed in inputs
    """
    serialised = str(nodes)

    # ── scalar input.* fields ─────────────────────────────────────────
    input_vars = set(re.findall(r"input\.([a-zA-Z_][a-zA-Z0-9_]*)", serialised))

    numeric_inputs = {
        "age", "business_vintage", "req_loan_amount", "loan_amount",
        "income", "emi", "abb", "foir", "credit_limit",
    }

    scalar_inputs = [
        {
            "id": _uuid(),
            "name": v,
            "dataType": "number" if v in numeric_inputs else "text",
            "isNullable": True,
            "defaultInput": "",
            "is_array": False,
            "schema": None,
        }
        for v in sorted(input_vars)
    ]

    # ── bank object input (when bank.* fields are referenced) ─────────
    bank_vars = sorted(set(re.findall(r"bank\.([a-zA-Z_][a-zA-Z0-9_]*)", serialised)))
    if bank_vars:
        # All bank fields are numeric (counts, amounts, ratios, percentages)
        bank_children = [
            {
                "id": _uuid(),
                "name": field,
                "dataType": "number",
                "isNullable": True,
                "defaultInput": None,
                "is_array": False,
                "schema": None,
            }
            for field in bank_vars
        ]
        bank_input: List[Dict] = [{
            "id": _uuid(),
            "name": "bank",
            "dataType": "object",
            "isNullable": False,
            "defaultInput": None,
            "is_array": True,
            "schema": None,
            "children": bank_children,
        }]
    else:
        bank_input = []

    return bank_input + scalar_inputs
