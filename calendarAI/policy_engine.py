# policy_engine.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
from policy_store import list_policies, create_policy, update_policy, delete_policy, toggle_policy
from flask import request, jsonify
import json, uuid, datetime as dt

# ======= LLM client shim (use your existing OpenAI client) =======
from openai import OpenAI
client = OpenAI()

def _json(obj):
    return obj if isinstance(obj, dict) else json.loads(str(obj))

def _now_iso():
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

# ---------- P1: intent ----------
def policy_layer1_intent(message: str) -> Dict[str, Any]:
    print("--- POLICY LAYER 1 ANALYSIS TRIGGERED ---")
    LAYER1_ADMIN_PROMPT = """
    """
    SYS = """
You are Policy L1. Classify if the user message is about policy management.
Output JSON only:
{"intent":"create|modify|delete|query|explain|simulate|other",
 "in_scope": true|false,
 "needs_previous_context": true|false}
Consider phrases like "never...", "always...", "don't let...", "policy", "rule".
"""
    rsp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role":"system","content":SYS},{"role":"user","content":message}]
    ).choices[0].message.content.strip()
    try: return json.loads(rsp)
    except: return {"intent":"other","in_scope":False,"needs_previous_context":False}

# ---------- P2: extract ----------
def policy_layer2_extract(message: str, prior_policy: Optional[Dict[str,Any]]=None) -> Dict[str, Any]:
    print("--- POLICY LAYER 2 ANALYSIS TRIGGERED ---")
    SYS = """
You are Policy L2. Extract a structured policy from the message.
Fields:
- name (string)
- strength: hard|ask|warn|soft
- scope: { "global":bool, "tags":[...], "entities":[...] }
- timeframe: { "kind":"ongoing|date_range|weekday_window|timeofday_window",
               "value":{...} }
- targets: array of actions (e.g., create_event,reschedule_event,delete_event,block_time,shift_events_batch)
- conditions: object (e.g., {"layer":"personal","min_buffer":15})
- priority: integer (lower = stronger across same strength)
- rationale: string
Return JSON:
{"adequate_information": true|false,
 "fields": {...},
 "clarifying_questions": null or "text"}
"""
    user = f"Message:\n{message}\n\nPrior policy:\n{json.dumps(prior_policy or {}, ensure_ascii=False)}"
    rsp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role":"system","content":SYS},{"role":"user","content":user}]
    ).choices[0].message.content.strip()
    try: return json.loads(rsp)
    except: return {"adequate_information": False, "fields": {}, "clarifying_questions": "Could you restate the rule?"}

# ---------- P3: canonicalize ----------
def policy_layer3_canonicalize(fields: Dict[str,Any], existing: List[Dict[str,Any]]) -> Dict[str, Any]:
    print("--- POLICY LAYER 3 ANALYSIS TRIGGERED ---")
    SYS = """
You are Policy L3. Convert fields to canonical policy and produce:
{"policy_draft": {...canonical...},
 "writeup":"plain english summary",
 "conflicts":[{"with_id":"...","reason":"...","resolution":"most_restrictive|priority|ask_user"}]}
Rules:
- Default status = "enabled"
- Default timeframe.kind="ongoing" if omitted
- Default strength="ask" if omitted
- Default priority=50
- When conflicts with existing, prefer most restrictive if same strength else higher strength beats lower.
"""
    user = f"Fields:\n{json.dumps(fields, ensure_ascii=False)}\n\nExisting:\n{json.dumps(existing, ensure_ascii=False)}"
    rsp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role":"system","content":SYS},{"role":"user","content":user}]
    ).choices[0].message.content.strip()
    try: return json.loads(rsp)
    except:
        return {"policy_draft": fields, "writeup": "Draft created.", "conflicts": []}

# ---------- P5: simulate ----------
def policy_layer5_simulate(action: Dict[str,Any], active_policies: List[Dict[str,Any]]) -> Dict[str,Any]:
    SYS = """
You are Policy L5 Simulator. Decide effect of policies on a proposed calendar action.
Output JSON only:
{"decision":"allow|block|ask|warn",
 "matched":[{"id":"...","name":"...","strength":"...","reason":"..."}],
 "explanation":"..."}
Rules:
- If multiple policies apply, choose the strongest outcome: block > ask > warn > allow.
- Consider scope (tags/entities), timeframe windows, targets, and conditions.
"""
    user = f"Action:\n{json.dumps(action, ensure_ascii=False)}\n\nPolicies:\n{json.dumps(active_policies, ensure_ascii=False)}"
    rsp = client.chat.completions.create(
        model="gpt-4.1",
        messages=[{"role":"system","content":SYS},{"role":"user","content":user}]
    ).choices[0].message.content.strip()
    try: return json.loads(rsp)
    except: return {"decision":"allow","matched":[],"explanation":"Simulator fallback."}

# ---------- Runtime helpers for calendar ----------
def runtime_policies_load() -> List[Dict[str,Any]]:
    return [p for p in list_policies() if p.get("status","enabled")=="enabled"]

def runtime_policies_filter_writes(writes: List[Dict[str,Any]], policies: List[Dict[str,Any]]) -> Dict[str,Any]:
    reviewed = []
    had_block, had_ask, had_warn = False, False, False
    for w in writes:
        sim = policy_layer5_simulate(w, policies)
        decision = sim.get("decision","allow")
        if decision == "block": had_block = True
        elif decision == "ask": had_ask = True
        elif decision == "warn": had_warn = True
        reviewed.append({**w, "_policy": sim})
    msg_bits = []
    if had_block: msg_bits.append("Some items were blocked by your policies.")
    if had_ask:   msg_bits.append("Some items need your confirmation due to policy.")
    if had_warn:  msg_bits.append("Some items include warnings.")
    return {
        "writes_filtered": [r for r in reviewed if r["_policy"]["decision"]!="block"],
        "per_item": reviewed,
        "confirmation_message": " ".join(msg_bits) or "Please confirm these changes."
    }
