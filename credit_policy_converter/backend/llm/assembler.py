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

_MODELSET_LIMIT = 180


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


_MATRIX_MAX_ROWS = 19
_MATRIX_MAX_COLS = 15


def _enforce_matrix_limits(expr: Dict) -> Dict:
    """Truncate a matrix expression to the BRE platform limits (19 rows, 15 cols)."""
    matrix = expr.get("matrix")
    if not matrix or not isinstance(matrix, dict):
        return expr

    rows = matrix.get("rows") or []
    cols = matrix.get("columns") or []
    values = matrix.get("values") or []

    data_row = next((r for r in rows if not r.get("isNoMatches")), None)
    no_match_row = next((r for r in rows if r.get("isNoMatches")), None)
    data_col = next((c for c in cols if not c.get("isNoMatches")), None)
    no_match_col = next((c for c in cols if c.get("isNoMatches")), None)

    if not data_row or not data_col:
        return expr

    row_conds = data_row.get("conditions") or []
    col_conds = data_col.get("conditions") or []
    R, C = len(row_conds), len(col_conds)

    if R <= _MATRIX_MAX_ROWS and C <= _MATRIX_MAX_COLS:
        return expr

    new_R = min(R, _MATRIX_MAX_ROWS)
    new_C = min(C, _MATRIX_MAX_COLS)

    def reindex(conds: list, count: int) -> list:
        return [{**c, "index": i} for i, c in enumerate(conds[:count])]

    def fix_no_match_conds(conds: list, idx: int) -> list:
        return [{**c, "index": idx} for c in (conds or [])]

    new_rows = []
    for r in rows:
        if r.get("isNoMatches"):
            new_rows.append({**r, "index": new_R, "conditions": fix_no_match_conds(r.get("conditions"), new_R)})
        else:
            new_rows.append({**r, "conditions": reindex(row_conds, new_R)})

    new_cols = []
    for c in cols:
        if c.get("isNoMatches"):
            new_cols.append({**c, "index": new_C, "conditions": fix_no_match_conds(c.get("conditions"), new_C)})
        else:
            new_cols.append({**c, "conditions": reindex(col_conds, new_C)})

    # Rebuild values grid: last row = original no-matches row; last col = original no-matches col.
    orig_R = len(values)
    new_values = []
    for i in range(new_R + 1):
        if i == new_R:
            src_row = values[-1] if values else []
        elif i < orig_R:
            src_row = values[i]
        elif values:
            src_row = values[-1]
        else:
            src_row = []

        orig_C = len(src_row)
        new_row = []
        for j in range(new_C + 1):
            if j == new_C:
                new_row.append(src_row[-1] if src_row else "")
            elif j < orig_C:
                new_row.append(src_row[j])
            elif src_row:
                new_row.append(src_row[-1])
            else:
                new_row.append("")
        new_values.append(new_row)

    new_matrix = {**matrix, "rows": new_rows, "columns": new_cols, "values": new_values,
                  "globalRowIndex": new_R, "globalColumnIndex": new_C}
    return {**expr, "matrix": new_matrix}


def _fix_undefined_model_refs(nodes: List[Dict]) -> List[Dict]:
    """Add placeholder expressions (condition '0') for any cross-node <modelset>.<expr>
    references that appear in conditions but are not defined in the target modelset."""
    ms_map: Dict[str, Dict] = {}  # name → {"idx": int, "exprs": set}
    for idx, node in enumerate(nodes):
        if node.get("type") == "modelSet":
            name = node.get("name", "")
            exprs = node.get("expressions") or []
            ms_map[name] = {
                "idx": idx,
                "exprs": {e.get("name", "") for e in exprs if e.get("name")},
            }

    if not ms_map:
        return nodes

    skip_ns = {"bureau", "bank", "input"}
    cond_re = re.compile(r"\b([a-z][a-zA-Z0-9_]*)\.([a-zA-Z_][a-zA-Z0-9_]*)\b")

    all_conds = ""
    for node in nodes:
        for expr in node.get("expressions") or []:
            all_conds += " " + expr.get("condition", "")
            dt = expr.get("decisionTableRules") or {}
            for h in dt.get("headers") or []:
                all_conds += " " + str(h)
        for rule in node.get("rules") or []:
            all_conds += " " + rule.get("approveCondition", "")
            all_conds += " " + rule.get("cantDecideCondition", "")

    seen: Dict[str, set] = {}
    missing: Dict[str, List[str]] = {}
    for m in cond_re.finditer(all_conds):
        ns, field = m.group(1), m.group(2)
        if ns in skip_ns or ns not in ms_map:
            continue
        if field in ms_map[ns]["exprs"]:
            continue
        seen.setdefault(ns, set())
        if field not in seen[ns]:
            seen[ns].add(field)
            missing.setdefault(ns, []).append(field)

    for ms_name, expr_names in missing.items():
        info = ms_map[ms_name]
        node = nodes[info["idx"]]
        exprs = list(node.get("expressions") or [])
        for expr_name in expr_names:
            exprs.append({
                "name": expr_name,
                "id": _uuid(),
                "seqNo": len(exprs),
                "condition": "0",
                "type": "expression",
                "decisionTableRules": _EMPTY_DT.copy(),
                "matrix": _EMPTY_MATRIX.copy(),
                "tag": _uuid(),
            })
            info["exprs"].add(expr_name)
        node["expressions"] = exprs

    return nodes


def _modelset(name: str, x: int, y: int, expressions: List[Dict], next_state: Dict) -> Dict:
    expr_objs = []
    for i, expr in enumerate(expressions):
        etype = expr.get("type", "expression")

        if etype == "matrix":
            expr = _enforce_matrix_limits(expr)
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

    # Collect input variable names from extracted data to detect expression name conflicts.
    # Uses str(extracted) so no dependency on _collect_conditions (defined later).
    _input_var_names = set(re.findall(r"\binput\.([a-zA-Z_][a-zA-Z0-9_]*)\b", str(extracted)))

    def _dedup_exprs(exprs: List[Dict]) -> List[Dict]:
        """Remove duplicate expression names (keep first) and rename any expression
        whose name matches an input variable name (suffix _calc to avoid collisions).
        Also updates condition strings within the same batch so intra-modelSet
        references remain consistent after renaming."""
        # Pass 1: build rename map for clashing names.
        rename_map = {
            e["name"]: e["name"] + "_calc"
            for e in exprs
            if e.get("name") and e["name"] in _input_var_names
        }

        seen: set = set()
        deduped: List[Dict] = []
        for e in exprs:
            name = e.get("name", "")
            if name in rename_map:
                name = rename_map[name]
                e = {**e, "name": name}
            # Propagate renames into condition text.
            if rename_map:
                cond = e.get("condition", "")
                if cond:
                    updated = cond
                    for old, new in rename_map.items():
                        updated = re.sub(r'\b' + re.escape(old) + r'\b', new, updated)
                    if updated != cond:
                        e = {**e, "condition": updated}
            if name and name not in seen:
                seen.add(name)
                deduped.append(e)
        return deduped

    def _fix_modelset_refs(exprs: List[Dict]) -> List[Dict]:
        """Fix stale bare-name references in DT headers, matrix headers, and condition
        strings. When the LLM names an expression 'foo_calc' but references it as 'foo'
        in headers or sibling conditions, this aligns those references to the actual name."""
        name_set = {e["name"] for e in exprs if e.get("name")}
        alias_map = {
            n[:-5]: n
            for n in name_set
            if n.endswith("_calc") and n[:-5] not in name_set
        }
        if not alias_map:
            return exprs

        def apply_alias(s: str) -> str:
            if "." in s:
                return s
            return alias_map.get(s, s)

        def apply_alias_cond(s: str) -> str:
            for old, new in alias_map.items():
                s = re.sub(r'\b' + re.escape(old) + r'\b', new, s)
            return s

        result = []
        for e in exprs:
            etype = e.get("type", "expression")
            if etype == "expression":
                cond = e.get("condition", "")
                updated = apply_alias_cond(cond)
                if updated != cond:
                    e = {**e, "condition": updated}
            elif etype == "decisionTable":
                dt = e.get("decisionTableRules")
                if isinstance(dt, dict):
                    dt_copy = dict(dt)
                    dt_changed = False
                    headers = dt.get("headers") or []
                    new_headers = [apply_alias(h) if isinstance(h, str) else h for h in headers]
                    if new_headers != headers:
                        dt_copy["headers"] = new_headers
                        dt_changed = True
                    rows = dt.get("rows") or []
                    new_rows = []
                    rows_changed = False
                    for row in rows:
                        if not isinstance(row, dict):
                            new_rows.append(row)
                            continue
                        cols = row.get("columns") or []
                        new_cols = []
                        cols_changed = False
                        for col in cols:
                            if isinstance(col, dict) and "name" in col:
                                new_name = apply_alias(col["name"])
                                if new_name != col["name"]:
                                    col = {**col, "name": new_name}
                                    cols_changed = True
                            new_cols.append(col)
                        if cols_changed:
                            row = {**row, "columns": new_cols}
                            rows_changed = True
                        new_rows.append(row)
                    if rows_changed:
                        dt_copy["rows"] = new_rows
                        dt_changed = True
                    if dt_changed:
                        e = {**e, "decisionTableRules": dt_copy}
            elif etype == "matrix":
                mat = e.get("matrix")
                if isinstance(mat, dict):
                    mat_copy = dict(mat)
                    mat_changed = False
                    rows = mat.get("rows") or []
                    new_rows = []
                    rows_changed = False
                    for row in rows:
                        if isinstance(row, dict) and "header" in row:
                            new_h = apply_alias(row["header"])
                            if new_h != row["header"]:
                                row = {**row, "header": new_h}
                                rows_changed = True
                        new_rows.append(row)
                    if rows_changed:
                        mat_copy["rows"] = new_rows
                        mat_changed = True
                    cols = mat.get("columns") or []
                    new_cols = []
                    cols_changed = False
                    for col in cols:
                        if isinstance(col, dict) and "header" in col:
                            new_h = apply_alias(col["header"])
                            if new_h != col["header"]:
                                col = {**col, "header": new_h}
                                cols_changed = True
                        new_cols.append(col)
                    if cols_changed:
                        mat_copy["columns"] = new_cols
                        mat_changed = True
                    if mat_changed:
                        e = {**e, "matrix": mat_copy}
            result.append(e)
        return result

    elig_exprs = _fix_modelset_refs(_dedup_exprs(elig_exprs))
    scorecard_exprs = _fix_modelset_refs(_dedup_exprs(scorecard_exprs))
    named_modelsets = [
        {**ms, "expressions": _fix_modelset_refs(_dedup_exprs(ms.get("expressions", [])))}
        for ms in named_modelsets
    ]

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

    def append_modelset(base_name: str, exprs: List[Dict], final_next: Dict) -> None:
        """Build one or more modelSet nodes, splitting into chunks of _MODELSET_LIMIT.
        Chunks are named base_name, base_name_2, … The last chunk's nextState is
        final_next; each preceding chunk points to the next."""
        if not exprs:
            return
        chunk_names: List[str] = []
        chunk_exprs: List[List[Dict]] = []
        for i in range(0, len(exprs), _MODELSET_LIMIT):
            name = base_name if i == 0 else f"{base_name}_{i // _MODELSET_LIMIT + 1}"
            chunk_names.append(name)
            chunk_exprs.append(exprs[i: i + _MODELSET_LIMIT])
        for ci, (cname, cexprs) in enumerate(zip(chunk_names, chunk_exprs)):
            if ci + 1 < len(chunk_names):
                next_state: Dict = {"name": chunk_names[ci + 1], "type": "modelSet"}
            else:
                next_state = final_next
            nodes.append(_modelset(cname, place(BASE_MEDIUM), Y_MAIN, cexprs, next_state=next_state))

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

    append_modelset("scorecard", scorecard_exprs, after_scorecard)

    # ── Named modelsets (between scorecard and first ruleset) ───────────
    for i, ms in enumerate(named_modelsets):
        ms_name = ms["name"]
        ms_exprs = ms.get("expressions", [])
        if i + 1 < len(named_modelsets):
            ms_next = {"name": named_modelsets[i + 1]["name"], "type": "modelSet"}
        else:
            ms_next = _first_ruleset_ref()
        append_modelset(ms_name, ms_exprs, ms_next)

    def _muted_switch(sw_name: str, rules: List[Dict], forward: Dict) -> Dict:
        """Muted ruleSets: pass and reject both continue forward. cantDecide too if present."""
        conditions = [
            {"name": "pass",   "nextState": forward},
            {"name": "reject", "nextState": forward},
        ]
        if _has_cant_decide(rules):
            conditions.append({"name": "cant_decide", "nextState": forward})
        return _switch(sw_name, conditions)

    def _active_switch(sw_name: str, rules: List[Dict], next_node: Dict) -> Dict:
        """Active ruleSets: all outcomes (pass/reject/cant_decide) continue to the next node.
        The final_decision branch is the single point that aggregates all ruleset decisions."""
        conditions = [
            {"name": "pass",   "nextState": next_node},
            {"name": "reject", "nextState": next_node},
        ]
        if _has_cant_decide(rules):
            conditions.append({"name": "cant_decide", "nextState": next_node})
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
    append_modelset("eligibility", elig_exprs, {"name": END_APPROVED, "type": "end"})

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

    # ── 12. Post-process: fill in any undefined cross-node expression refs ──
    nodes = _fix_undefined_model_refs(nodes)

    # ── 13. Build inputs array ────────────────────────────────────────
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
