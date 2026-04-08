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

def _ruleset(name: str, x: int, y: int, rules: List[Dict], switch_name: str) -> Dict:
    rule_objs = [
        {
            "name": r.get("name", f"Rule_{i + 1}"),
            "id": _uuid(),
            "seqNo": i,
            "approveCondition": r.get("approveCondition", "true"),
            "cantDecideCondition": r.get("cantDecideCondition", ""),
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

def assemble_workflow(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Build the complete workflow JSON from Claude-extracted data."""

    # ── Separate muted vs active rules ───────────────────────────────
    all_gng = extracted.get("go_no_go_rules", [])
    gng_muted = [r for r in all_gng if r.get("muted", False)]
    gng_active = [r for r in all_gng if not r.get("muted", False)]

    all_sp = extracted.get("surrogate_rules", [])
    sp_muted = [r for r in all_sp if r.get("muted", False)]
    sp_active = [r for r in all_sp if not r.get("muted", False)]

    elig_exprs = extracted.get("eligibility_expressions", [])
    scorecard_exprs = extracted.get("scorecard_expressions", [])

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
    bureau_name = "Source_Node_Bureau"
    nodes.append({
        "type": "start",
        "name": "Start",
        "metadata": {"x": place(BASE_NARROW), "y": Y_MAIN, "nodeColor": 1},
        "nextState": {"name": bureau_name, "type": "dataSource"},
    })

    # ── 2. DataSource — bureau ────────────────────────────────────────
    after_bureau = (
        {"name": "scorecard", "type": "modelSet"}
        if scorecard_exprs
        else {"name": "model", "type": "modelSet"}
    )
    nodes.append({
        "type": "dataSource",
        "name": bureau_name,
        "tag": _uuid(),
        "sources": [{"name": "bureau", "id": 41238, "seqNo": 0, "type": "finboxSource", "tag": _uuid()}],
        "metadata": {"x": place(BASE_NARROW), "y": Y_MAIN, "nodeColor": 1},
        "nextState": after_bureau,
    })

    # ── 3. Scorecard modelSet ─────────────────────────────────────────
    if scorecard_exprs:
        nodes.append(_modelset(
            "scorecard", place(BASE_MEDIUM), Y_MAIN, scorecard_exprs,
            next_state={"name": "model", "type": "modelSet"},
        ))

    # ── 4. Model modelSet ─────────────────────────────────────────────
    model_exprs = [
        {"name": "hit_no_hit", "condition": "bureau.bureauscore != nil", "type": "expression"},
        {"name": "age_at_maturity", "condition": "input.age + 3", "type": "expression"},
    ]

    def first_after_model() -> Dict:
        if gng_muted:
            return {"name": "muted_go_no_go_checks", "type": "ruleSet"}
        if gng_active:
            return {"name": "go_no_go_checks", "type": "ruleSet"}
        if sp_muted:
            return {"name": "muted_surrogate_policy_checks", "type": "ruleSet"}
        if sp_active:
            return {"name": "surrogate_policy_checks", "type": "ruleSet"}
        return {"name": "final_decision", "type": "branch"}

    nodes.append(_modelset("model", place(BASE_MEDIUM), Y_MAIN, model_exprs, next_state=first_after_model()))

    # ── 5. Muted Go/No-Go ─────────────────────────────────────────────
    if gng_muted:
        sw = "muted_go_no_go_checks-switch"
        next_rs = (
            {"name": "go_no_go_checks", "type": "ruleSet"} if gng_active else
            {"name": "muted_surrogate_policy_checks", "type": "ruleSet"} if sp_muted else
            {"name": "surrogate_policy_checks", "type": "ruleSet"} if sp_active else
            {"name": "final_decision", "type": "branch"}
        )
        nodes.append(_ruleset("muted_go_no_go_checks", place(ruleset_width(gng_muted)), Y_MAIN, gng_muted, sw))
        nodes.append(_switch(sw, [
            {"name": "pass",   "nextState": next_rs},
            {"name": "reject", "nextState": next_rs},
        ]))

    # ── 6. Active Go/No-Go ────────────────────────────────────────────
    if gng_active:
        sw = "go_no_go_checks-switch"
        pass_next = (
            {"name": "muted_surrogate_policy_checks", "type": "ruleSet"} if sp_muted else
            {"name": "surrogate_policy_checks", "type": "ruleSet"} if sp_active else
            {"name": "final_decision", "type": "branch"}
        )
        nodes.append(_ruleset("go_no_go_checks", place(ruleset_width(gng_active)), Y_MAIN, gng_active, sw))
        nodes.append(_switch(sw, [
            {"name": "pass",   "nextState": pass_next},
            {"name": "reject", "nextState": {"name": END_REJECTED, "type": "end"}},
        ]))

    # ── 7. Muted Surrogate ────────────────────────────────────────────
    if sp_muted:
        sw = "muted_surrogate_policy_checks-switch"
        next_rs = (
            {"name": "surrogate_policy_checks", "type": "ruleSet"} if sp_active else
            {"name": "final_decision", "type": "branch"}
        )
        nodes.append(_ruleset("muted_surrogate_policy_checks", place(ruleset_width(sp_muted)), Y_MAIN, sp_muted, sw))
        nodes.append(_switch(sw, [
            {"name": "pass",   "nextState": next_rs},
            {"name": "reject", "nextState": next_rs},
        ]))

    # ── 8. Active Surrogate ───────────────────────────────────────────
    if sp_active:
        sw = "surrogate_policy_checks-switch"
        nodes.append(_ruleset("surrogate_policy_checks", place(ruleset_width(sp_active)), Y_MAIN, sp_active, sw))
        nodes.append(_switch(sw, [
            {"name": "pass",   "nextState": {"name": "final_decision", "type": "branch"}},
            {"name": "reject", "nextState": {"name": END_REJECTED, "type": "end"}},
        ]))

    # ── 9. Final Decision branch ──────────────────────────────────────
    fd_sw = "final_decision-switch"
    parts = []
    if gng_active:
        parts.append('go_no_go_checks.decision == "pass"')
    if sp_active:
        parts.append('surrogate_policy_checks.decision == "pass"')
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
    end_x = x_cursor   # x_cursor already points past the last node
    nodes.append({
        "type": "end",
        "name": END_APPROVED,
        "endNodeName": "approved",
        "tag": _uuid(),
        "decisionNode": {"output": '{"decision": "approved"}'},
        "metadata": {"x": end_x, "y": Y_APPROVED, "nodeColor": 3},
    })
    nodes.append({
        "type": "end",
        "name": END_REJECTED,
        "endNodeName": "rejected",
        "tag": _uuid(),
        "decisionNode": {"output": '{"decision": "rejected"}'},
        "metadata": {"x": end_x, "y": Y_REJECTED, "nodeColor": 2},
    })

    # ── 12. Build inputs array ────────────────────────────────────────
    inputs = _build_inputs(nodes)

    return {
        "nodes": nodes,
        "inputs": inputs,
        "outputs": [
            {"name": "decision", "dataType": "text"},
            {"name": "amount",   "dataType": "number"},
        ],
        "settings": {
            "name": "Credit Policy Workflow",
            "version": "1.0.0",
            "description": "Auto-generated from credit policy document",
        },
    }


def _build_inputs(nodes: List[Dict]) -> List[Dict]:
    """Scan all node expressions for input.* references and build the inputs array."""
    serialised = str(nodes)
    vars_found = set(re.findall(r"input\.([a-zA-Z_][a-zA-Z0-9_]*)", serialised))

    numeric = {
        "age", "business_vintage", "req_loan_amount", "loan_amount",
        "income", "emi", "abb", "foir", "credit_limit",
    }

    return [
        {
            "id": _uuid(),
            "name": v,
            "dataType": "number" if v in numeric else "text",
            "isNullable": True,
            "defaultInput": "",
            "is_array": False,
            "schema": None,
        }
        for v in sorted(vars_found)
    ]
