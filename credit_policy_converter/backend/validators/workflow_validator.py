"""Validates workflow JSON structure for the credit policy BRE platform."""
from typing import Dict, Any, List


def validate_workflow(workflow: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate a workflow JSON.
    Returns {valid, errors, warnings, stats}.
    """
    errors: List[str] = []
    warnings: List[str] = []

    nodes: List[Dict] = workflow.get("nodes", [])
    inputs: List[Dict] = workflow.get("inputs", [])

    if not nodes:
        return {
            "valid": False,
            "errors": ["Workflow has no nodes"],
            "warnings": [],
            "stats": {},
        }

    # Index nodes by name for reference checks
    node_by_name = {n["name"]: n for n in nodes if "name" in n}

    # ── Start node ──────────────────────────────────────────────────────
    start_nodes = [n for n in nodes if n.get("type") == "start"]
    if not start_nodes:
        errors.append("Missing required 'start' node")
    elif len(start_nodes) > 1:
        errors.append(f"Multiple start nodes found: {[n['name'] for n in start_nodes]}")

    # ── End nodes ────────────────────────────────────────────────────────
    end_nodes = [n for n in nodes if n.get("type") == "end"]
    if not end_nodes:
        errors.append("No 'end' nodes found — workflow has no terminal states")

    # ── nextState references ─────────────────────────────────────────────
    for node in nodes:
        name = node.get("name", "<unnamed>")

        next_state = node.get("nextState")
        if next_state:
            target = next_state.get("name")
            if target and target not in node_by_name:
                errors.append(
                    f"Node '{name}' nextState references unknown node '{target}'"
                )

        for cond in node.get("dataConditions", []):
            target = cond.get("nextState", {}).get("name")
            if target and target not in node_by_name:
                errors.append(
                    f"Switch '{name}' condition '{cond.get('name')}' "
                    f"references unknown node '{target}'"
                )

        for expr in node.get("expressions", []):
            # branch expressions reference nextState via the switch
            pass

    # ── ruleSet checks ───────────────────────────────────────────────────
    total_rules = 0
    for node in nodes:
        if node.get("type") == "ruleSet":
            rules = node.get("rules", [])
            total_rules += len(rules)
            if not rules:
                warnings.append(f"RuleSet '{node.get('name')}' has no rules")
            for rule in rules:
                if not rule.get("approveCondition"):
                    warnings.append(
                        f"Rule '{rule.get('name')}' in '{node.get('name')}' "
                        f"has an empty approveCondition"
                    )

    # ── modelSet checks ──────────────────────────────────────────────────
    for node in nodes:
        if node.get("type") == "modelSet" and not node.get("expressions"):
            warnings.append(f"ModelSet '{node.get('name')}' has no expressions")

    # ── branch checks ────────────────────────────────────────────────────
    for node in nodes:
        if node.get("type") == "branch" and not node.get("expressions"):
            errors.append(f"Branch '{node.get('name')}' has no expressions")

    node_types: Dict[str, int] = {}
    for n in nodes:
        t = n.get("type", "unknown")
        node_types[t] = node_types.get(t, 0) + 1

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "stats": {
            "total_nodes": len(nodes),
            "node_types": node_types,
            "rule_sets": node_types.get("ruleSet", 0),
            "total_rules": total_rules,
            "inputs": len(inputs),
        },
    }
