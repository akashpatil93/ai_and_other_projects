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


def _wrap_if_text(value: Any) -> Any:
    """Wrap a plain text string in escaped quotes; leave numbers and booleans unchanged.

    "A"     → '"A"'      (text → wrapped)
    "12.12" → "12.12"    (number → unchanged)
    "true"  → "true"     (boolean → unchanged)
    '"A"'   → '"A"'      (already wrapped → unchanged)
    """
    if not isinstance(value, str) or not value:
        return value
    v = value.strip()
    if v.startswith('"') and v.endswith('"'):
        return value  # already wrapped
    is_boolean = v.lower() in ("true", "false")
    is_numeric = False
    try:
        float(v)
        is_numeric = True
    except (ValueError, TypeError):
        pass
    return value if (is_numeric or is_boolean) else f'"{value}"'


def _quote_dt_outputs(dt_rules: Dict) -> Dict:
    """Apply text-wrapping to the default value and every row output in a
    decisionTableRules object.

    Plain text strings are wrapped ("A" → '"A"'); numbers and booleans are unchanged.
    """
    import copy as _copy
    rules = _copy.deepcopy(dt_rules)

    if rules.get("default") is not None:
        rules["default"] = _wrap_if_text(rules["default"])

    for row in rules.get("rows") or []:
        if row.get("output") is not None:
            row["output"] = _wrap_if_text(row["output"])

    return rules


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
                "decisionTableRules": _quote_dt_outputs(expr.get("decisionTableRules", _EMPTY_DT.copy())),
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


def assemble_workflow(extracted: Dict[str, Any], sample_payload: str = "") -> Dict[str, Any]:
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
    named_modelsets: List[Dict] = extracted.get("named_modelsets", [])

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

    # ── 3. Scorecard modelSet (if extracted) ─────────────────────────
    # Scan conditions for bank.* references to decide whether a bank datasource is needed.
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

    # Build the ordered pre-ruleset chain:
    # dataSource → [scorecard] → [named modelsets...] → first ruleset / final_decision
    def _first_ruleset_ref() -> Dict:
        if all_rulesets:
            return {"name": all_rulesets[0]["name"], "type": "ruleSet"}
        return {"name": "final_decision", "type": "branch"}

    def _first_named_modelset_or_ruleset() -> Dict:
        if named_modelsets:
            return {"name": named_modelsets[0]["name"], "type": "modelSet"}
        return _first_ruleset_ref()

    # What does the dataSource flow into?
    after_datasource = (
        {"name": "scorecard", "type": "modelSet"}
        if scorecard_exprs
        else _first_named_modelset_or_ruleset()
    )

    # What does scorecard flow into?
    after_scorecard = _first_named_modelset_or_ruleset()

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

    # ── Named modelsets (between scorecard and first ruleset) ───────────
    for i, ms in enumerate(named_modelsets):
        ms_name = ms["name"]
        ms_exprs = ms.get("expressions", [])
        if i + 1 < len(named_modelsets):
            ms_next = {"name": named_modelsets[i + 1]["name"], "type": "modelSet"}
        else:
            ms_next = _first_ruleset_ref()
        nodes.append(_modelset(ms_name, place(BASE_MEDIUM), Y_MAIN, ms_exprs, next_state=ms_next))

    def _muted_switch(sw_name: str, rules: List[Dict], forward: Dict) -> Dict:
        """Muted ruleSets: pass and reject both continue forward. cantDecide too if present."""
        conditions = [
            {"name": "pass",   "nextState": forward},
            {"name": "reject", "nextState": forward},
        ]
        if _has_cant_decide(rules):
            conditions.append({"name": "cantDecide", "nextState": forward})
        return _switch(sw_name, conditions)

    def _active_switch(sw_name: str, rules: List[Dict], next_node: Dict) -> Dict:
        """Active ruleSets: all outcomes (pass/reject/cantDecide) continue to the next node.
        The final_decision branch is the single point that aggregates all ruleset decisions."""
        conditions = [
            {"name": "pass",   "nextState": next_node},
            {"name": "reject", "nextState": next_node},
        ]
        if _has_cant_decide(rules):
            conditions.append({"name": "cantDecide", "nextState": next_node})
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
    outputs: List[Dict] = []

    end_x = x_cursor   # x_cursor already points past the last node
    nodes.append({
        "type": "end",
        "name": END_APPROVED,
        "endNodeName": "approved",
        "tag": _uuid(),
        "workflowState": {"type": "", "outcomeLogic": None},
        "decisionNode": {},
        "metadata": {"x": end_x, "y": Y_APPROVED, "nodeColor": 3},
    })
    nodes.append({
        "type": "end",
        "name": END_REJECTED,
        "endNodeName": "rejected",
        "tag": _uuid(),
        "workflowState": {"type": "", "outcomeLogic": None},
        "decisionNode": {},
        "metadata": {"x": end_x, "y": Y_REJECTED, "nodeColor": 2},
    })

    # ── 12. Build inputs array ────────────────────────────────────────
    inputs = _build_inputs(nodes, sample_payload=sample_payload)

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


def _build_inputs(nodes: List[Dict], sample_payload: str = "") -> List[Dict]:
    """Scan all node expressions and build the inputs array.

    - input.* variables → scalar inputs (text or number)
    - bank.* variables  → object input with numeric children
    - bureau.* variables come from the dataSource node and are NOT listed in inputs
    - Any other namespace.* (e.g. applicants.*, collateral.*) detected in conditions
      → object inputs; marked is_array=true when the namespace is used inside an
        array predicate function (all/any/filter/map/etc.)

    sample_payload: optional JSON string of a representative API request body.
      When provided, each object input's `schema` field is populated from the
      matching top-level key in the payload (stringified back to JSON).
    """
    import json as _json

    serialised = str(nodes)

    # Parse the sample payload once; fall back to empty dict on any error.
    try:
        _payload: Dict[str, Any] = _json.loads(sample_payload) if sample_payload and sample_payload.strip() else {}
        if not isinstance(_payload, dict):
            _payload = {}
    except Exception:
        _payload = {}

    def _schema_for(name: str) -> Any:
        """Return the raw payload value for an object input's schema, or None."""
        return _payload.get(name)  # BRE expects the actual list/dict, not a JSON string

    # ── payload-derived object inputs ─────────────────────────────────
    # For every top-level payload key whose value is an array or dict,
    # create a properly-typed object input using the payload structure.
    # This runs before condition scanning so we know which namespaces are covered.
    payload_namespaces: set = set()
    payload_object_inputs: List[Dict] = []

    for key, val in _payload.items():
        if not isinstance(val, (list, dict)):
            continue  # scalars are covered by input.* condition scanning

        is_arr = isinstance(val, list)
        # For arrays: use first element as the field template; for dicts: use directly
        sample = (val[0] if val and isinstance(val[0], dict) else {}) if is_arr else val

        oid = _uuid()
        children = [
            {
                "id": _uuid(),
                "name": f,
                "dataType": "number" if isinstance(fv, (int, float)) and not isinstance(fv, bool) else "text",
                "isNullable": False,
                "defaultInput": None,
                "children": None,
                "parentID": oid,
                "isArray": False,
                "schema": None,
                "operation": "",
            }
            for f, fv in sample.items()
        ]
        payload_object_inputs.append({
            "id": oid,
            "name": key,
            "dataType": "object",
            "isNullable": False,
            "defaultInput": None,
            "is_array": is_arr,
            "isArray": is_arr,
            "parentID": "",
            "operation": "",
            "schema": _schema_for(key),
            "children": children,
        })
        payload_namespaces.add(key)

    # BRE-internal namespaces: bureau from dataSource, model/scorecard from modelSet outputs,
    # plus any named modelSet / ruleSet / branch node names (they produce output namespaces).
    bre_node_names: set = set()
    for node in nodes:
        if node.get("type") in ("modelSet", "ruleSet", "branch"):
            n = node.get("name", "")
            if n:
                bre_node_names.add(n)

    # Also skip namespaces already covered by the payload to avoid duplicates.
    SKIP_NS = {"bureau", "input", "bank", "model", "scorecard"} | bre_node_names | payload_namespaces

    # ── scalar input.* fields ─────────────────────────────────────────
    input_vars = set(re.findall(r"\binput\.([a-zA-Z_][a-zA-Z0-9_]*)\b", serialised))

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
        if v not in payload_namespaces  # skip names already defined as object inputs via payload
    ]

    def _object_children(parent_id: str, fields: List[str], numeric: bool = False) -> List[Dict]:
        """Build the children list for an object input node."""
        return [
            {
                "id": _uuid(),
                "name": field,
                "dataType": "number" if numeric else "text",
                "isNullable": False,
                "defaultInput": None,
                "children": None,
                "parentID": parent_id,
                "isArray": False,
                "schema": None,
                "operation": "",
            }
            for field in fields
        ]

    def _object_input(name: str, is_arr: bool, fields: List[str], numeric: bool = False) -> Dict:
        """Build a top-level object input node with children."""
        oid = _uuid()
        return {
            "id": oid,
            "name": name,
            "dataType": "object",
            "isNullable": False,
            "defaultInput": None,
            "is_array": is_arr,
            "isArray": is_arr,
            "parentID": "",
            "operation": "",
            "schema": _schema_for(name),
            "children": _object_children(oid, fields, numeric=numeric),
        }

    # ── bank object input (when bank.* fields are referenced) ─────────
    # Skip if bank was already defined via the sample payload.
    bank_input: List[Dict] = []
    if "bank" not in payload_namespaces:
        bank_vars = sorted(set(re.findall(r"\bbank\.([a-zA-Z_][a-zA-Z0-9_]*)\b", serialised)))
        if bank_vars:
            bank_input = [_object_input("bank", is_arr=True, fields=bank_vars, numeric=True)]

    # ── other object namespace inputs ─────────────────────────────────
    # Find every `namespace.field` pair where namespace is lowercase and not already handled.
    all_ns_refs = re.findall(r"\b([a-z][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b", serialised)
    ns_fields: Dict[str, set] = {}
    for ns, field in all_ns_refs:
        if ns not in SKIP_NS:
            ns_fields.setdefault(ns, set()).add(field)

    # Namespaces that appear as the first argument of an array predicate function
    # e.g. all(applicants, {...}) or filter(applicants, ...) → applicants is an array.
    array_namespaces = set(re.findall(
        r"\b(?:all|any|none|one|filter|map|sum|count|find|findIndex|reduce|groupBy|sortBy)\s*\(\s*([a-z][a-zA-Z0-9_]*)",
        serialised,
    ))

    other_object_inputs: List[Dict] = [
        _object_input(ns, is_arr=(ns in array_namespaces), fields=sorted(ns_fields[ns]))
        for ns in sorted(ns_fields.keys())
    ]

    return payload_object_inputs + bank_input + other_object_inputs + scalar_inputs
