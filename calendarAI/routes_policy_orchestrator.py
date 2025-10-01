# routes_policy_orchestrator.py
from flask import Blueprint, request, jsonify
import json, uuid, datetime as dt

from policy_engine import (
    policy_layer1_intent,
    policy_layer2_extract,
    policy_layer3_canonicalize,
)

from policy_store import (
    list_policies,
    create_policy,
    update_policy,
    delete_policy,
    toggle_policy,
)

policy_bp = Blueprint("policy_bp", __name__)  # <-- define a Blueprint (no app import)

def _json(obj):
    return obj if isinstance(obj, dict) else json.loads(str(obj))

def _now_iso():
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

@policy_bp.route("/policy/handle", methods=["POST"])
def policy_handle():
    print("--- POLICY MESSAGE RECEIVED. POLICY HANDLER TRIGGERED ---")
    payload     = request.get_json() or {}
    session_id  = payload.get("session_id") or str(uuid.uuid4())
    message     = (payload.get("message") or "").strip()
    mode        = (payload.get("mode") or "compose").lower()
    confirmed   = bool(payload.get("confirmed"))
    override_writes = payload.get("writes") or None

    # L1
    print("--- POLICY LAYER 1 ANALYSIS TRIGGERED ---")
    l1 = _json(policy_layer1_intent(message=message))

    if l1.get("immediate_reply_applicable") and l1.get("immediate_reply"):
        return jsonify({
            "session_id": session_id,
            "layer1": l1,
            "reply_text": l1["immediate_reply"],
            "layer2": None, "layer3_plan": None, "layer4_results": None
        })

    # L2
    print("--- POLICY LAYER 2 ANALYSIS TRIGGERED ---")
    l2 = _json(policy_layer2_extract(message=message, chat_context=None))
    if not l2.get("adequate_information", False):
        return jsonify({
            "session_id": session_id,
            "layer1": l1, "layer2": l2,
            "reply_text": l2.get("clarifying_questions") or "Could you clarify the rule details?",
            "layer3_plan": None, "layer4_results": None
        })

    # L3
    print("--- POLICY LAYER 3 ANALYSIS TRIGGERED ---")
    extracted = l2.get("extracted") or {}
    l3 = _json(policy_layer3_canonicalize(
        user_message=message,
        extracted=extracted,
        context_summary=None,
        intent=l1.get("intent", "compose")
    ))

    plan_writes   = l3.get("proposed_writes") or []
    needs_confirm = bool(l3.get("confirmation_required") or plan_writes)

    if confirmed:
        l4 = _apply_policy_writes(plan_writes if override_writes is None else override_writes)
        reply = l4.get("final_reply") or "Policies updated."
        return jsonify({
            "session_id": session_id,
            "layer1": l1, "layer2": l2,
            "layer3_plan": l3,
            "layer4_results": l4,
            "reply_text": reply
        })

    return jsonify({
        "session_id": session_id,
        "layer1": l1, "layer2": l2, "layer3_plan": l3,
        "reply_text": l3.get("reply_text") or "Here’s the draft policy. Would you like me to save it?",
        "confirmation": {
            "message": l3.get("confirm_text") or "Save/enable these policy changes?",
            "writes": plan_writes
        } if needs_confirm else None
    })


def _apply_policy_writes(writes: list[dict]) -> dict:
    status = "ok"
    results = []

    def _normalize_on_create(pol: dict) -> dict:
        pol = dict(pol or {})
        pol.setdefault("enabled", True)
        pol.setdefault("status", "enabled" if pol.get("enabled", True) else "disabled")
        pol.setdefault("priority", 50)
        pol.setdefault("type", "soft")
        pol.setdefault("scope", "global")
        pol.setdefault("timeframe", {"kind": "ongoing"})
        return pol

    try:
        for w in (writes or []):
            wtype  = (w or {}).get("type")
            params = dict((w or {}).get("parameters") or {})

            if wtype == "policy_create":
                pol = _normalize_on_create(params.get("policy") or params)
                created = create_policy(pol)
                results.append({"action": wtype, "status": "success", "policy_id": created["id"], "policy": created})

            elif wtype == "policy_update":
                pid   = params.get("id")
                patch = dict(params.get("patch") or {})
                if not pid:
                    results.append({"action": wtype, "status": "error", "error": "Missing id"}); continue
                updated = update_policy(pid, patch)
                results.append(
                    {"action": wtype, "status": "success", "policy_id": pid, "policy": updated}
                    if updated else {"action": wtype, "status": "error", "error": "Policy not found"}
                )

            elif wtype == "policy_delete":
                pid = params.get("id")
                if not pid:
                    results.append({"action": wtype, "status": "error", "error": "Missing id"}); continue
                ok = delete_policy(pid)
                results.append({"action": wtype, "status": "success" if ok else "error", "policy_id": pid, "deleted": bool(ok)})

            elif wtype == "policy_toggle":
                pid     = params.get("id")
                enabled = bool(params.get("enabled", True))
                if not pid:
                    results.append({"action": wtype, "status": "error", "error": "Missing id"}); continue
                toggled = toggle_policy(pid, enabled)
                if toggled:
                    toggled["enabled"] = (toggled.get("status") == "enabled")
                    results.append({"action": wtype, "status": "success", "policy_id": pid, "enabled": toggled["enabled"], "policy": toggled})
                else:
                    results.append({"action": wtype, "status": "error", "error": "Policy not found"})

            else:
                results.append({"action": wtype, "status": "error", "error": f"Unknown write {wtype}"})

    except Exception as e:
        status = "error"
        results.append({"action": "exception", "status": "error", "error": str(e)})

    return {
        "status": status,
        "results": results,
        "final_reply": "All policy changes have been applied." if status == "ok" else "Some policy changes failed."
    }
