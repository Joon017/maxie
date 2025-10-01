# policy_routes.py
from __future__ import annotations
from flask import Blueprint, request, jsonify
from typing import Any, Dict
from policy_store import list_policies, get_policy, create_policy, update_policy, delete_policy, toggle_policy
from policy_engine import (
    policy_layer1_intent,
    policy_layer2_extract,
    policy_layer3_canonicalize,
    policy_layer5_simulate,
    runtime_policies_load
)

bp = Blueprint("policies", __name__)

@bp.get("/policies")
def policies_list():
    q = (request.args.get("q") or "").strip().lower()
    items = list_policies()
    if q:
        items = [p for p in items if q in (p.get("name","")+p.get("description","")).lower()]
    return jsonify({"status":"success","items": items})

@bp.post("/policies")
def policies_create():
    payload = request.get_json() or {}
    # Accept either a raw "fields" (from L2) or a canonical draft
    fields = payload.get("fields") or payload.get("policy") or {}
    existing = list_policies()
    canon = policy_layer3_canonicalize(fields, existing)
    created = create_policy({
        **canon.get("policy_draft", {}),
        "name": fields.get("name") or canon.get("policy_draft",{}).get("name","Untitled Policy"),
        "description": fields.get("rationale") or canon.get("writeup",""),
        "status": "enabled"
    })
    return jsonify({"status":"success","policy": created, "writeup": canon.get("writeup"), "conflicts": canon.get("conflicts",[])})

@bp.put("/policies/<pid>")
def policies_update(pid: str):
    payload = request.get_json() or {}
    patch: Dict[str, Any] = payload.get("patch") or payload
    updated = update_policy(pid, patch)
    if not updated:
        return jsonify({"status":"error","message":"Not found"}), 404
    return jsonify({"status":"success","policy": updated})

@bp.post("/policies/<pid>/toggle")
def policies_toggle(pid: str):
    payload = request.get_json() or {}
    enabled = bool(payload.get("enabled", True))
    updated = toggle_policy(pid, enabled)
    if not updated:
        return jsonify({"status":"error","message":"Not found"}), 404
    return jsonify({"status":"success","policy": updated})

@bp.delete("/policies/<pid>")
def policies_delete(pid: str):
    ok = delete_policy(pid)
    if not ok:
        return jsonify({"status":"error","message":"Not found"}), 404
    return jsonify({"status":"success"})

# ----- Authoring helpers for Compose -----

@bp.post("/policy/intent")
def policy_intent():
    payload = request.get_json() or {}
    msg = payload.get("message","")
    out = policy_layer1_intent(msg)
    return jsonify({"status":"success","result": out})

@bp.post("/policy/extract")
def policy_extract():
    payload = request.get_json() or {}
    msg = payload.get("message","")
    prior = payload.get("prior_policy")
    out = policy_layer2_extract(msg, prior)
    return jsonify({"status":"success","result": out})

@bp.post("/policy/canonicalize")
def policy_canonicalize():
    payload = request.get_json() or {}
    fields = payload.get("fields") or {}
    existing = list_policies()
    out = policy_layer3_canonicalize(fields, existing)
    return jsonify({"status":"success","result": out})

# ----- Simulator -----

@bp.post("/policies/simulate")
def policies_simulate():
    payload = request.get_json() or {}
    action = payload.get("action") or {}
    active = runtime_policies_load()
    out = policy_layer5_simulate(action, active)
    return jsonify({"status":"success","result": out})
