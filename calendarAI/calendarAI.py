from flask import Flask, render_template, request, jsonify
from flask import Response, stream_with_context
from dotenv import load_dotenv
from utility.context_tracker import ContextTracker
from utility.conversation_state import ConversationState
from utility.state_strategies import stage_strategies
import os
import json, time, uuid, hashlib
import uuid
import threading
from datetime import datetime, timedelta
from openai import OpenAI
from flask_cors import CORS
import re
import calendar
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo  # Python 3.9+

from calendarTools import (
    fetch_events, get_free_slots, create_event, reschedule_event, delete_event,
    summarize_day, block_time, shift_events_batch, find_event_by_keyword,
    # Holding helpers
    list_holding,
    create_holding_item as create_holding,
    move_event_to_holding as move_to_holding,
    promote_holding_to_event as promote_holding,
)

from calendarTools import handle_action

# AFTER
READ_ACTIONS  = {"fetch_events","summarize_day","find_event_by_keyword","get_free_slots","list_holding"}
WRITE_ACTIONS = {"create_event","reschedule_event","delete_event","block_time","shift_events_batch",
                 "move_to_holding","promote_holding"}

_TIME_ONLY_RE = re.compile(r'^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$', re.I)

# one pending plan per session; swap for Redis/DB in prod
PENDING_PLANS: dict[str, dict] = {}

def set_pending_plan(session_id: str, plan: dict) -> None:
    PENDING_PLANS[session_id] = plan

def get_pending_plan(session_id: str) -> dict | None:
    return PENDING_PLANS.get(session_id)

def clear_pending_plan(session_id: str) -> None:
    PENDING_PLANS.pop(session_id, None)

# =========================
# App bootstrap
# =========================
app = Flask(__name__)
CORS(app)
load_dotenv()

# Register the orchestrator blueprint
from routes_policy_orchestrator import policy_bp
app.register_blueprint(policy_bp)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


# State helpers
context_tracker = ContextTracker()
conversation_state = ConversationState()


# Define expected schema for Layer1
EXPECTED_KEYS_LAYER1 = {
    "needs_previous_context": bool,
    "intent": str,
    "in_scope": bool,
    "immediate_reply_applicable": bool,
    "immediate_reply": (str, type(None)),
    "next_steps_required": bool
}

EXPECTED_KEYS_LAYER2 = {
    "adequate_information": bool,
    "clarifying_questions": (str, type(None)),
    "reason": str,
}

# ---- Layer 3 schema helpers ----
EXPECTED_KEYS_LAYER3 = {
    "reply_text": str,
    "internal_steps": list,
    "required_actions": list,   # list of {"type": str, "parameters": dict}
    "debug": dict,
    "confirmation_required": bool
}

DATE_KEYS = {
    "date", "start_date", "end_date", "source_date", "target_date",
    # feel free to add: "on_date", "for_date"
}
DATETIME_KEYS = {
    "start_time", "end_time", "new_start", "new_end", "when", "due_at",
    # feel free to add: "datetime"
}

# =========================
# Helper functions
# =========================

# top of file (replace existing)
def _ensure_seconds(iso_dt: str | None) -> str | None:
    if not iso_dt:
        return iso_dt
    try:
        datetime.strptime(iso_dt, "%Y-%m-%dT%H:%M:%S")
        return iso_dt
    except Exception:
        dt = datetime.strptime(iso_dt, "%Y-%m-%dT%H:%M")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

def _load_store() -> Dict[str, Dict[str, Any]]:
    if not USE_JSON_STORE or not os.path.exists(EVENT_STORE_PATH):
        return {}
    try:
        with open(EVENT_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        for ev in data.values():
            try:
                if "start" in ev and ev["start"]:
                    ev["start"] = _ensure_seconds(ev["start"])
                if "end" in ev and ev["end"]:
                    ev["end"] = _ensure_seconds(ev["end"])
            except Exception as e:
                print(f"[calendarTools] normalize error for id={ev.get('id')}: {e}")
        return data
    except Exception as e:
        print(f"[calendarTools] Failed to load store: {e}")
        return {}

def user_now() -> datetime:
    """
    Returns 'now' in the user's timezone (env: USER_TZ; defaults to UTC).
    """
    import os
    tz = os.getenv("USER_TZ", "UTC")  # e.g. "America/Los_Angeles"
    try:
        return datetime.now(ZoneInfo(tz))
    except Exception:
        return datetime.utcnow()
    
def _looks_like_datetime(s: str) -> bool:
    """
    Heuristic: if the string contains a time-ish pattern,
    treat it as a datetime even when the key is 'date'.
    """
    s = s.lower().strip()
    return any(tkn in s for tkn in [":", " am", " pm"]) or any(
        kw in s for kw in ["at ", "noon", "midnight"]
    )


def _to_hhmm(val: str) -> str:
    """
    Accepts:
      - '19:00'
      - '7pm' or '7 pm' or '07:30pm'
      - ISO datetime 'YYYY-MM-DDTHH:MM(:SS)?[Z]?'
      - 'YYYY-MM-DD HH:MM'
    Returns 'HH:MM' (24h).
    Raises ValueError if unparseable.
    """
    s = str(val).strip()
    # ISO datetime (with or without Z)
    try:
        dt = datetime.fromisoformat(s.replace("Z", ""))
        return dt.strftime("%H:%M")
    except Exception:
        pass
    # 'YYYY-MM-DD HH:MM'
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        return dt.strftime("%H:%M")
    except Exception:
        pass
    # time-only, with optional am/pm
    m = _TIME_ONLY_RE.match(s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        ap = (m.group(3) or "").lower()
        if ap == "pm" and hh != 12:
            hh += 12
        if ap == "am" and hh == 12:
            hh = 0
        return f"{hh:02d}:{mm:02d}"
    # already HH:MM?
    try:
        datetime.strptime(s, "%H:%M")
        return s
    except Exception:
        pass
    raise ValueError(f"Unrecognized time-of-day: {val}")

def normalize_datetime_params(params: dict, base: Optional[datetime] = None) -> tuple[dict, list[str]]:
    base = base or user_now()
    if not params:
        return {}, []

    norm = {}
    warnings: list[str] = []

    for k, v in dict(params).items():
        # Recurse for dicts/lists (keep your existing code)
        if isinstance(v, dict):
            sub_norm, sub_warn = normalize_datetime_params(v, base=base)
            norm[k] = sub_norm
            warnings.extend(sub_warn)
            continue
        if isinstance(v, list):
            new_list = []
            for item in v:
                if isinstance(item, dict):
                    item_norm, sub_warn = normalize_datetime_params(item, base=base)
                    new_list.append(item_norm)
                    warnings.extend(sub_warn)
                else:
                    new_list.append(item)
            norm[k] = new_list
            continue

        # ---- NEW: time-window keys for get_free_slots must be HH:MM ----
        if isinstance(v, str) and k in {"start_range", "end_range"}:
            try:
                norm[k] = _to_hhmm(v)
            except Exception as e:
                warnings.append(f"Could not parse {k} '{v}': {e}")
                norm[k] = v  # pass through (your tool may error, but we recorded why)
            continue

        # existing min_duration parsing (keep as you already have)
        if k == "min_duration":
            try:
                norm[k] = _parse_min_duration(v)  # your existing helper: "30m" -> 30
            except Exception as e:
                warnings.append(f"Could not parse min_duration '{v}': {e}")
                norm[k] = v
            continue

        # existing date/datetime resolution blocks (keep yours):
        if isinstance(v, str):
            raw = v.strip()
            if (k in DATETIME_KEYS) or (k in DATE_KEYS and _looks_like_datetime(raw)):
                try:
                    norm[k] = resolve_relative_datetime(raw, base=base)
                except Exception as e:
                    warnings.append(f"Unrecognized datetime expression for '{k}': {raw} ({e})")
                    norm[k] = v
                continue
            if k in DATE_KEYS:
                try:
                    # if you support "this week"/"next week" expansion here, keep that too
                    norm[k] = resolve_relative_date(raw, base=base)
                except Exception as e:
                    warnings.append(f"Unrecognized date expression for '{k}': {raw} ({e})")
                    norm[k] = v
                continue

        # Fallback
        norm[k] = v

    return norm, warnings

def _extract_layer1_output(text: str) -> str:
    """
    Extract JSON block from assistant output.
    Prioritizes ```json ...``` fenced blocks, falls back to the first {...} object.
    """
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if m:
        return m.group(1)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("No JSON object found in the assistant output.")
    return m.group(0)

def _normalize_nil(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert "NIL" string into Python None for immediate_reply.
    """
    if "immediate_reply" in payload and payload["immediate_reply"] == "null":
        payload["immediate_reply"] = None
    return payload

def _validate_layer1(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate that all expected keys exist and are of the correct type.
    """
    for k, t in EXPECTED_KEYS_LAYER1.items():
        if k not in payload:
            raise ValueError(f"Missing key: {k}")
        if t is bool and not isinstance(payload[k], bool):
            raise TypeError(f"{k} must be bool")
        if t is str and not isinstance(payload[k], str):
            raise TypeError(f"{k} must be str")
        if isinstance(t, tuple) and not isinstance(payload[k], t):
            raise TypeError(f"{k} has wrong type")
    return payload

def parse_layer1_output(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print("[Parser] Raw L1 output not valid JSON, attempting repair...")

        # Fix common mistake: unquoted intent values (like check, reschedule, etc.)
        fixed = re.sub(r'("intent":\s*)(\w+)', r'\1"\2"', raw)

        try:
            return json.loads(fixed)
        except Exception:
            print("[Parser] Repair failed, returning raw text")
            return {"error": "parse_failed", "raw": raw}
        
def _extract_json_block(text: str) -> str:
    """
    Generic JSON extractor: prefer ```json fenced blocks, otherwise first {...} object.
    """
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, flags=re.S)
    if m:
        return m.group(1)
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("No JSON object found in assistant output.")
    return m.group(0)

def _normalize_nil_layer2(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert NIL to None for clarifying_questions.
    """
    if "clarifying_questions" in payload and payload["clarifying_questions"] == "NIL":
        payload["clarifying_questions"] = None
    return payload

def _massage_l2_keys(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize common misspellings / variants from the prompt.
    - Accept 'aqeduate_information' (typo) as 'adequate_information'
    """
    if "adequate_information" not in payload and "aqeduate_information" in payload:
        payload["adequate_information"] = payload.pop("aqeduate_information")
    return payload

def _validate_layer2(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate all expected keys exist and have correct types.
    """
    for k, t in EXPECTED_KEYS_LAYER2.items():
        if k not in payload:
            raise ValueError(f"Layer 2 JSON missing key: {k}")
        if isinstance(t, tuple):
            if not isinstance(payload[k], t):
                raise TypeError(f"Layer 2 key '{k}' has wrong type; expected {t}, got {type(payload[k]).__name__}")
        else:
            if not isinstance(payload[k], t):
                raise TypeError(f"Layer 2 key '{k}' must be {t.__name__}, got {type(payload[k]).__name__}")
    return payload

def parse_layer2_output(text: str) -> Dict[str, Any]:
    """
    Parse and validate the Layer 2 assistant JSON output.
    Returns dict with normalized keys/types:
    {
        "adequate_information": bool,
        "clarifying_questions": Optional[str],
        "reason": str
    }
    """
    raw = _extract_json_block(text)
    data = json.loads(raw)
    data = _massage_l2_keys(data)
    data = _normalize_nil_layer2(data)
    return _validate_layer2(data)

def _validate_layer3(payload: Dict[str, Any]) -> Dict[str, Any]:
    for k, t in EXPECTED_KEYS_LAYER3.items():
        if k not in payload:
            raise ValueError(f"Layer 3 JSON missing key: {k}")
        if not isinstance(payload[k], t):
            raise TypeError(f"Layer 3 key '{k}' must be {t.__name__}, got {type(payload[k]).__name__}")
    for a in payload["required_actions"]:
        if not isinstance(a, dict) or "type" not in a or "parameters" not in a:
            raise TypeError("Each required_action must have 'type' and 'parameters'.")
    return payload

def parse_layer3_output(text: str) -> Dict[str, Any]:
    raw = _extract_json_block(text)
    data = json.loads(raw)
    data.setdefault("required_actions", [])
    data.setdefault("proposed_writes", [])
    data.setdefault("confirmation_required", False)
    data.setdefault("debug", {})
    return data

def layer4_execute(plan: dict, session_id: str | None = None, allow_writes: bool = False) -> dict:
    """
    Execute the L3 plan with step-by-step execution trace.

    - Reads in plan["required_actions"] are always executed.
    - Writes in plan["proposed_writes"] are only executed when allow_writes=True.
    - Updates/persists a focus_set in the context tracker for continuity.
    - Returns:
        {
          "status": "ok" | "needs_confirmation" | "error",
          "results": [ ... per-action outputs ... ],
          "execution_trace": [ ...steps with labels, status, output... ],
          "final_reply": "<string for the user>",
          "confirmation": {
              "message": "<what will happen if confirmed>",
              "proposed_actions": [ ...writes to POST to /confirm_actions ... ],
              "preview": [ ...human-friendly bullets/rows... ]
          } | None
        }
    """
    actions = list(plan.get("required_actions") or [])
    writes  = list(plan.get("proposed_writes") or [])
    results = []
    execution_trace = []
    status  = "ok"
    final_text = plan.get("reply_text") or "Done."
    confirmation = None

    print("=== [L4] EXECUTION START ===")
    print("Plan:", json.dumps(plan, indent=2))

    # --- activate focus_set tracking ---
    fs = {}
    if session_id:
        fs = context_tracker.get_focus_set(session_id) or {}
        print(f"[L4] Retrieved focus_set for session {session_id}: {json.dumps(fs, indent=2)}")

    READ_ACTIONS  = {"fetch_events","summarize_day","find_event_by_keyword","get_free_slots","list_holding"}
    WRITE_ACTIONS = {"create_event","reschedule_event","delete_event","block_time","shift_events_batch",
                    "move_to_holding","promote_holding"}

    def _dispatch(act_type: str, params: dict):
        # READS
        if act_type == "fetch_events":
            return fetch_events(
                date=params.get("date"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
                filters=params.get("filters"),
            )
        if act_type == "get_free_slots":
            return get_free_slots(
                date=params["date"],
                min_duration=params.get("min_duration", 30),
                start_range=params.get("start_range"),
                end_range=params.get("end_range"),
            )
        if act_type == "summarize_day":
            return summarize_day(params["date"])
        if act_type == "find_event_by_keyword":
            return find_event_by_keyword(**params)
        if act_type == "list_holding":                 # ← add
            return list_holding()

        # WRITES
        if act_type == "create_event":
            return create_event(**params)
        if act_type == "reschedule_event":
            return reschedule_event(**params)
        if act_type == "delete_event":
            return delete_event(**params)
        if act_type == "block_time":
            return block_time(**params)
        if act_type == "shift_events_batch":
            return shift_events_batch(**params)

        # Holding writes
        if act_type == "create_holding":
            return create_holding(**params)            # alias to create_holding_item
        if act_type == "move_to_holding":
            return move_to_holding(**params)           # alias to move_event_to_holding
        if act_type == "promote_holding":
            return promote_holding(**params)           # alias to promote_holding_to_event

        raise ValueError(f"Unknown action type {act_type}")

    # ===== 1) RUN READS =====
    for idx, act in enumerate(actions, start=1):
        act_type = act.get("type")
        raw_params = act.get("parameters", {}) or {}
        params, warns = normalize_datetime_params(raw_params)
        if warns:
            print(f"[L4] Normalization warnings (read {idx}):", warns)

        print(f"\n--- [L4] READ {idx} --- {act_type} :: {params}")

        trace_entry = {
            "id": f"read{idx}",
            "label": f"{act_type} :: {params}",
            "type": "read",
            "status": "in_progress",
            "output": None
        }

        try:
            if act_type not in READ_ACTIONS:
                results.append({"action": act_type, "status": "skipped", "reason": "writes not allowed in required_actions"})
                trace_entry["status"] = "error"
                status = "error"
            else:
                out = _dispatch(act_type, params)
                results.append({"action": act_type, "status": "success", "output": out})
                trace_entry["status"] = "completed"
                trace_entry["output"] = out

                # --- update focus_set per action ---
                if session_id and isinstance(out, dict):
                    if act_type == "fetch_events" and out.get("status") == "success":
                        before = len(fs.get("focus_events", []))
                        fs["focus_events"] = fs.get("focus_events", []) + out.get("events", [])
                        after = len(fs["focus_events"])
                        print(f"[L4] focus_set updated: fetch_events → {after-before} new events (total {after})")

                    if act_type == "get_free_slots" and out:
                        fs["focus_free_slots"] = fs.get("focus_free_slots", []) + [out]
                        print(f"[L4] focus_set updated: get_free_slots → 1 new slot set (total {len(fs['focus_free_slots'])})")

                    if act_type == "summarize_day" and out:
                        fs["focus_summary"] = out
                        print(f"[L4] focus_set updated: summarize_day → summary replaced for {params.get('date')}")

                    if act_type == "find_event_by_keyword" and out:
                        fs["focus_search"] = fs.get("focus_search", []) + [out]
                        print(f"[L4] focus_set updated: find_event_by_keyword → 1 new search result (total {len(fs['focus_search'])})")

                if act_type == "summarize_day":
                    date_str = params.get("date")
                    evs = (out or {}).get("events", [])
                    msg = f"Here’s your agenda for {date_str}:\n" + (
                        "\n".join(f"- {e['title']} at {e['start']}" for e in evs) if evs else "No events scheduled."
                    )
                    final_text = msg
        except Exception as e:
            results.append({"action": act.get("type"), "status": "exception", "error": str(e)})
            trace_entry["status"] = "error"
            trace_entry["output"] = {"error": str(e)}
            status = "error"

        execution_trace.append(trace_entry)

    # persist focus_set after reads
    if session_id:
        context_tracker.set_focus_set(session_id, fs)
        print(f"[L4] Persisted focus_set for session {session_id}: {json.dumps(fs, indent=2)}")

    # ===== 2) HANDLE WRITES =====
    if writes:
        if allow_writes:
            for idx, act in enumerate(writes, start=1):
                act_type = act.get("type")
                raw_params = act.get("parameters", {}) or {}
                params, warns = normalize_datetime_params(raw_params)
                if warns:
                    print(f"[L4] Normalization warnings (write {idx}):", warns)

                print(f"\n--- [L4] WRITE {idx} --- {act_type} :: {params}")

                trace_entry = {
                    "id": f"write{idx}",
                    "label": f"{act_type} :: {params}",
                    "type": "write",
                    "status": "in_progress"
                }

                try:
                    if act_type not in WRITE_ACTIONS:
                        results.append({"action": act_type, "status": "skipped", "reason": "not a write action"})
                        trace_entry["status"] = "error"
                        status = "error"
                    else:
                        out = _dispatch(act_type, params)
                        results.append({"action": act_type, "status": "success", "output": out})
                        trace_entry["status"] = "completed"
                except Exception as e:
                    results.append({"action": act.get("type"), "status": "exception", "error": str(e)})
                    trace_entry["status"] = "error"
                    trace_entry["output"] = {"error": str(e)}
                    status = "error"

                execution_trace.append(trace_entry)

            if status == "ok":
                final_text = plan.get("success_text") or "All changes have been applied."
        else:
            confirmation = {
                "message": plan.get("confirm_text") or "I’m ready to apply these changes. Shall I proceed?",
                "proposed_actions": writes,
                "preview": [
                    f"{w.get('type')} → {json.dumps(w.get('parameters', {}))}" for w in writes
                ]
            }
            status = "needs_confirmation"
            if not final_text:
                final_text = "I’ve gathered the details. Review the proposal below and confirm to apply changes."

    print("\n=== [L4] EXECUTION END ===")
    return {
        "status": status,
        "results": results,
        "execution_trace": execution_trace,
        "final_reply": final_text,
        "confirmation": confirmation
    }

def layer5_synthesis(user_message: str, slim_l4_results: dict, context_summary: str = None):
    print("=== [L5] SYNTHESIS TRIGGERED ===")
    
    LAYER5_ADMIN_PROMPT = """
    <core_identity>
    You are a helpful scheduling assistant. 
    You take the user’s request, relevant context, and results from Layer 4 (executor),
    and produce the final user-facing answer.
    </core_identity>

    <rules>
    - Only use events/slots actually provided by L4. Don’t hallucinate.
    - Use the context summary if available (it may include earlier user messages).
    - If the request is incomplete or ambiguous, ask a clarifying follow-up.
    - Be concise and natural: 2–4 sentences max, unless a list is needed.
    </rules>

    <expected_output_format>
    Always return valid JSON:
    {
      "final_reply": string,
      "next_actions": [string],  // optional
      "confidence": number
    }
    </expected_output_format>
    """

    LAYER5_PROMPT = f"""
    User request (latest message):
    {user_message}

    Context summary (if any):
    {context_summary or "[no extra context]"}

    Layer 4 results (slimmed):
    {json.dumps(slim_l4_results, indent=2)}
    """

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": LAYER5_ADMIN_PROMPT},
            {"role": "user", "content": LAYER5_PROMPT}
        ]
    )

    answer = response.choices[0].message.content.strip()
    try:
        return json.loads(answer)
    except Exception:
        return {"final_reply": answer, "next_actions": [], "confidence": 0.6}

def _parse_min_duration(val) -> int:
    if isinstance(val, int):
        return val
    s = str(val).strip().lower()
    if s.endswith("m"):
        s = s[:-1]
    return int(s)

def _slim_l4_for_llm(plan: dict, l4: dict) -> dict:
    safe = {
        "intent": (plan.get("debug") or {}).get("intent"),
        "reply_text_hint": plan.get("reply_text"),
        "results": []
    }
    for r in l4.get("results", []):
        if r.get("status") != "success":
            continue
        action = r.get("action")
        out = r.get("output") or {}
        # include only relevant fields per action type
        if action == "get_free_slots":
            slots = out.get("free_slots") or out.get("slots") or []
            safe["results"].append({"action": "get_free_slots", "free_slots": slots})
        elif action == "summarize_day":
            evs = out.get("events") or []
            safe["results"].append({"action": "summarize_day", "events": evs, "summary": out.get("summary")})
        elif action == "fetch_events":
            evs = out.get("events") or []
            safe["results"].append({"action": "fetch_events", "events": evs})
        # add other read types similarly
    return safe

# =========================
# Routes
# =========================
@app.route('/')
def index():
    return render_template('index.html')

@app.route("/execute_plan_stream", methods=["GET"])
def execute_plan_stream():
    # expects ?session_id=<id>
    session_id = request.args.get("session_id", "").strip()
    if not session_id:
        return Response("Missing session_id", status=400)

    plan = get_pending_plan(session_id)
    if not plan:
        return Response("No pending plan", status=404)

    READ_ACTIONS  = {"fetch_events", "get_free_slots", "summarize_day",
                 "find_event_by_keyword", "list_holding"}
    WRITE_ACTIONS = {"create_event", "reschedule_event", "delete_event",
                    "block_time", "shift_events_batch",
                    "create_holding", "move_to_holding", "promote_holding"}

    def _dispatch(act_type: str, params: dict):
        # READS
        if act_type == "fetch_events":
            return fetch_events(
                date=params.get("date"),
                start_date=params.get("start_date"),
                end_date=params.get("end_date"),
                filters=params.get("filters"),
            )
        if act_type == "get_free_slots":
            return get_free_slots(
                date=params["date"],
                min_duration=params.get("min_duration", 30),
                start_range=params.get("start_range"),
                end_range=params.get("end_range"),
            )
        if act_type == "summarize_day":
            return summarize_day(params["date"])
        if act_type == "find_event_by_keyword":
            return find_event_by_keyword(**params)
        if act_type == "list_holding":
            return list_holding()

        # WRITES
        if act_type == "create_event":
            return create_event(**params)
        if act_type == "reschedule_event":
            return reschedule_event(**params)
        if act_type == "delete_event":
            return delete_event(**params)
        if act_type == "block_time":
            return block_time(**params)
        if act_type == "shift_events_batch":
            return shift_events_batch(**params)

        # Holding writes
        if act_type == "create_holding":
            return create_holding(**params)          # alias to create_holding_item
        if act_type == "move_to_holding":
            return move_to_holding(**params)         # alias to move_event_to_holding
        if act_type == "promote_holding":
            return promote_holding(**params)         # alias to promote_holding_to_event

        raise ValueError(f"Unknown action type {act_type}")

    @stream_with_context
    def generate():
        # 1) signal start
        yield "event: start\ndata: {}\n\n"

        # 2) run READS
        for idx, act in enumerate(plan.get("required_actions") or [], start=1):
            act_type = act.get("type")
            raw_params = act.get("parameters", {}) or {}
            params, _ = normalize_datetime_params(raw_params)

            step = {
                "id": f"read{idx}",
                "label": f"{act_type} :: {params}",
                "type": "read",
                "status": "in_progress"
            }
            yield f"data: {json.dumps(step)}\n\n"

            try:
                if act_type not in READ_ACTIONS:
                    raise ValueError(f"{act_type} is not a read action")
                out = _dispatch(act_type, params)
                step["status"] = "completed"
                step["output"] = out
            except Exception as e:
                step["status"] = "error"
                step["output"] = {"error": str(e)}
            yield f"data: {json.dumps(step)}\n\n"

        # 3) run WRITES
        for idx, act in enumerate(plan.get("proposed_writes") or [], start=1):
            act_type = act.get("type")
            raw_params = act.get("parameters", {}) or {}
            params, _ = normalize_datetime_params(raw_params)

            step = {
                "id": f"write{idx}",
                "label": f"{act_type} :: {params}",
                "type": "write",
                "status": "in_progress"
            }
            yield f"data: {json.dumps(step)}\n\n"

            try:
                if act_type not in WRITE_ACTIONS:
                    raise ValueError(f"{act_type} is not a write action")
                out = _dispatch(act_type, params)
                step["status"] = "completed"
                step["output"] = out
            except Exception as e:
                step["status"] = "error"
                step["output"] = {"error": str(e)}
            yield f"data: {json.dumps(step)}\n\n"

        # 4) cleanup & end
        clear_pending_plan(session_id)
        yield "event: end\ndata: {}\n\n"

    # SSE response
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"  # friendly to some proxies
    }
    return Response(generate(), mimetype="text/event-stream", headers=headers)

CONFIRM_WORDS = {"yes", "yep", "sure", "confirm", "proceed", "do it", "go ahead", "ok", "okay"}
CANCEL_WORDS  = {"no", "cancel", "stop", "nevermind", "never mind", "abort", "don’t", "dont"}
THRESHOLD = 0.65  # require this confidence to auto-apply

def _extract_json_block(text: str) -> str | None:
    m = re.search(r"```json\s*(\{.*?\})\s*```", text, re.S)
    if m: return m.group(1)
    m = re.search(r"\{.*\}", text, re.S)
    return m.group(0) if m else None

def _safe_load_json(s: str) -> dict | None:
    try:
        return json.loads(s)
    except Exception:
        return None

def _fallback_keywords(msg: str) -> dict | None:
    t = msg.strip().lower()
    if t in CONFIRM_WORDS:
        return {"follow_up": True, "decision": "confirm", "confidence": 0.51, "reason": "keyword fallback"}
    if t in CANCEL_WORDS:
        return {"follow_up": True, "decision": "cancel", "confidence": 0.51, "reason": "keyword fallback"}
    return None

def preL1_check(message: str, session_id: str, get_pending_plan, clear_pending_plan, layer4_execute):
    print("\n--- [PreL1 Check] Activated ---")
    print(f"[PreL1] Session: {session_id}")
    print(f"[PreL1] User message: {message}")

    pending = get_pending_plan(session_id)
    if not pending:
        print("[PreL1] No pending plan found. Passing through to L1.")
        return None

    print(f"[PreL1] Found pending plan: {json.dumps(pending, indent=2, ensure_ascii=False)}")

    SYSTEM = """
    You are a router that decides whether the user's latest message is a follow-up
    to a pending calendar proposition/suggestion that you've given previously.
    Output STRICT JSON ONLY:

    {
      "follow_up": true|false,
      "decision": "confirm"|"cancel"|"modify"|"other",
      "confidence": 0.0-1.0,
      "reason": "<short reason>"
    }

    Rules:
    - If the user clearly approves (e.g., "confirm", "yes"), decision="confirm".
    - If the user declines (e.g., "cancel", "no"), decision="cancel".
    - If the user changes details (e.g., new date/time), decision="modify".
    - If unrelated, decision="other" and follow_up=false.
    - Be conservative; only mark follow_up=true when reasonably clear.
    """
    USER = f"""
Pending plan (summarize):
{json.dumps(pending, ensure_ascii=False)}

User message:
{message}
"""

    try:
        resp = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "system", "content": SYSTEM},
                      {"role": "user", "content": USER}],
            temperature=0
        )
        raw = resp.choices[0].message.content.strip()
        print(f"[PreL1] Raw model output:\n{raw}")

        block = _extract_json_block(raw) or raw
        data = _safe_load_json(block)

        print(f"[PreL1] Parsed decision: {json.dumps(data, indent=2)}")

    except Exception as e:
        print(f"[PreL1] Exception during model call: {e}")
        data = None

    if not data:
        print("[PreL1] Falling back to keyword check...")
        data = _fallback_keywords(message)
        print(f"[PreL1] Fallback keyword result: {data}")

    if not data or data.get("follow_up") is not True:
        print("[PreL1] Not a follow-up → proceed with L1 flow.")
        return None

    decision = data.get("decision")
    conf = float(data.get("confidence", 0))
    print(f"[PreL1] Decision: {decision}, Confidence: {conf}, Reason: {data.get('reason')}")

    # CONFIRM
    if decision == "confirm" and conf >= THRESHOLD:
        print("[PreL1] High-confidence CONFIRM → stream execution (do not execute here).")
        # Keep the plan pending; frontend will open SSE to run it.
        return {
            "session_id": session_id,
            "reply_text": "Got it — starting now and I’ll update you step by step…",
            "start_stream": True,                 # <-- frontend will look for this
            "routed_to": "confirm_followup_stream_ready"
        }

    # CANCEL
    if decision == "cancel" and conf >= 0.5:
        print("[PreL1] CANCEL → clearing pending plan.")
        clear_pending_plan(session_id)
        return {
            "session_id": session_id,
            "reply_text": "Okay — I won’t apply those changes.",
            "routed_to": "cancel_followup"
        }

    # MODIFY
    if decision == "modify":
        print("[PreL1] MODIFY → keeping plan, rerouting to L1/L2/L3 for new instructions.")
        return None

    # Low-confidence → ask again
    if decision in {"confirm", "cancel"} and conf < THRESHOLD:
        print("[PreL1] Low-confidence → asking user for explicit confirmation.")
        return {
            "session_id": session_id,
            "reply_text": "Just to confirm — should I proceed with the plan I proposed earlier?",
            "routed_to": "low_conf_ask"
        }

    print("[PreL1] No actionable decision → pass to L1.")
    return None

def layer1_analysis(message):
    print("--- LAYER 1 ANALYSIS TRIGGERED ---")
    LAYER1_ADMIN_PROMPT = """
    <core_identity>
    You are a useful AI that manages everything regarding the user's calendar, scheduling and related events/information. 
    Your first task now as the first layer is to analyse the user's message, and provide the first analyses.
    <core_identity>

    <important_rules>      
    *** As the first layer, you don't have access to the user's calendar or context, only the user's input/request
    message. If the request requires more context/the user's calendar, then next steps is required. ***
    *** You should not hallucinate any information about the user's calendar or schedules ***
    *** IF THE USER ASKS ANY QUESTIONS THAT IS UNRELATED TO HELPING THEM WITH THEIR SCHEDULING/CALENDER,
    REMIND THEM THAT YOU CAN ONLY HELP THEM WITH THAT AND DONT ACCEDE TO THEIR REQUESTS
    *** However, should also not be too rigid and be able to handle basic conversation with the user, 
    such as small talk, greetings, simple qnAs. Its just that if what the user says if very out of scope
    of what you do, then align the user back. ***
    </important_rules>

    <continuation_rules>
    Treat the message as a FOLLOW-UP that REQUIRES previous context when it contains any of:
    - Pronouns or deictics referring to earlier content: "it", "them", "that", "those", "this",
    "tomorrow", "next Monday/Tuesday", "the meeting", "the events", "that day".
    - Imperative follow-ups: "go ahead", "do it", "block it", "reschedule them/it", "move it",
    "book it", "confirm it".
    If it’s a follow-up: 
    "needs_previous_context": true,
    "next_steps_required": true,
    "immediate_reply_applicable": false.
    </continuation_rules>

    <in_scope>  
    Here is the general view of the actions you can perform, which is not exhaustive but a general guide:
    Core Scheduling
    - Create, update, delete events.
    - Reschedule events, including batch shifts (e.g., moving all events from one day to another).
    - Find free time slots and suggest optimal meeting times.
    - Check conflicts before scheduling.

    Event & Entity Information
    - Fetch event details (titles, times, participants, locations, notes).
    - Look up entities/people mentioned in events (e.g., “Who is the meeting with on Friday?”).
    - Answer questions about your schedule (e.g., “When’s my next client meeting?”).
    - Search events by keyword, layer, or timeframe.

    Briefing & Debriefing
    - Daily briefing: Summarize what’s happening today (events, locations, priorities).
    - Weekly overview: Provide a digest of the upcoming week.
    - Meeting prep briefing: Summarize relevant details before a meeting (who, where, agenda, recent related notes).
    - Debrief after events: Capture notes or action items after meetings.
    - Retrospectives: Provide a lookback on the past week/month.

    Extended Personal Assistant Features (future expansion)
    - Contextual reminders (e.g., “Don’t forget to prep slides before your 3pm call”).
    - Cross-link events with documents/emails if integrated.
    - Track goals or priorities across events (like recurring projects).
    - Suggest optimizations (e.g., reduce back-to-back meetings, highlight double-bookings).

    Insights & Advice
    - Workload balance: Highlight if your day/week is overloaded or uneven.
    - Focus optimization: Suggest better distribution of deep work vs. meetings.
    - Conflict spotting: Flag overlapping or back-to-back events that may need adjustment.
    - Time usage patterns: Point out recurring trends (e.g., too many late-night calls, or mornings free but afternoons packed).
    - Wellness advice: Remind you to schedule breaks if your day is packed.
    - Strategic suggestions: Suggest grouping similar events, blocking focus time, or rescheduling low-priority items.
    <in_scope>  

    <your_task>
    With the information above, analyse: 
    1) Does it require previous messages/context for answering (e.g. if the question asks about something that requires fetching previous interactions or one that is a continuity, then its true. 
    This is important to let our system know whether to fetch chat history later)
    2) Identify the user’s intent (e.g., smalltalk|check|reschedule|create|delete|info|briefing|advice|other|unknown).
    3) Is what the user is asking/requesting within the scope of actions listed above?
    4) Can an immediate reply be given? (For instance, immediate replies should be given to user's smalltalks, greetings, simple questions that you have the context to answer or if 
    the what the user is asking is beyond the scope and you can immediately remind the user
    to ask things within the scope.) But if further actions is needed, to fulfil the user's request, 
    dont provide immediate reply. 
    5) If an immediate reply can be given according to 4, what would be the immediate reply?
    <your_task>
    6) If the user is seeking help, checking etc and if it falls in scope as above, then next_steps is true. Else, false.

    <expected_output_format>
    Always output strictly in JSON with the following keys:
    {{
    "needs_previous_context": true | false,
    "intent": smalltalk|check|reschedule|create|delete|info|briefing|advice|other|unknown,
    "in_scope": true | false,
    "immediate_reply_applicable": true | false,
    "immediate_reply": null | <<immediate reply if applicable>>,
    "next_steps_required": true | false
    </expected_output_format>
    }}
    """
    LAYER1_PROMPT = f"""
    This is the user's message: {message}
    """
    response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[  
                {"role": "system", "content": LAYER1_ADMIN_PROMPT},
                {"role": "user", "content": LAYER1_PROMPT}
            ]
        )

    answer = response.choices[0].message.content.strip()
    return answer

def layer2_analysis(message, chat_context):
    print("--- LAYER 2 ANALYSIS TRIGGERED ---")
    LAYER1_ADMIN_PROMPT = f"""
    <core_identity>
    You are a helpful AI that specializes in calendar and scheduling tasks for the user.
    You are invoked at Layer 2 because the request was determined to be in-scope,
    but we must check whether it has enough detail to proceed. If not, ask clarifying questions
    to the user. 
    <core_identity>

     <important_rules>
    - You should strive to be an intelligent assistant, and strike a fine line between preempting/predicting
    what the user refers to or requires, and also clarifying and seeking the right information to perform the next actions
    - You do not have to clarify which calendar the user is referring to, there is only one that you will have 
    access to at a later layer
    - For dates, only clarify when necessary. E.g. if the user refers to time like today, yesterday,
    next week, sometime next week etc, you should automatically know the dates.
    - If what the user says is abit vague and requires clarification/confirmation, go ahead and ask
    - Its okay to be more verbose so as to let the user know your thinking process and to intervene 
    if necessary
    - If the user has a clear TITLE/intent but NO concrete datetime (phrases like
    "TBD", "sometime next week", "when free", "later", "no date yet") OR if a
    conflict is likely, it's acceptable to proceed by proposing a Holding item
    instead of blocking. In that case, treat the request as actionable and do not
    force a clarification—L3 will stage a `create_holding` plan.
    </important_rules>

    <chat_context>
    If chat context was deemed necessary and given, it will be provided here:
    {chat_context}
    </context>

    <identifying_ambiguities>  
    Look for the following common gaps that would block action:
    - Missing specific dates/times (e.g., "schedule a meeting
    - soon" without specifying when)
    - Missing event titles or purposes (e.g., "add something to my calendar")
    - Missing participant details (e.g.,"schedule a meeting with John")  
    - Unclear duration or time preferences (e.g., "find me a slot this week")
    - Missing location details (e.g., "schedule a meeting" without specifying where)
    - Vague or conflicting time ranges (e.g., "sometime next week" without specifying days or hours)
    - Unclear recurrence patterns (e.g., "every week" without specifying which day or time)
    - Missing event IDs or references for updates/deletions
    - Unclear action verbs (e.g., "handle", "deal with", "take care of" without specifying what action)
    Etc. This list is non exhaustive and its okay to utilise your own intelligence to make your 
    judgements on what is inadequate and what requires justification
    </identifying ambiguities>

    <examples>
    Here are some examples of user messages and whether they are adequate:
    "can you help me keep the whole of my tuesday free next week?": yes, because the intention of the user 
    is clear, which is to have no events scheduled on tues next week
    "can you help me keep tuesday free?": no, because it is unclear whether it is the upcoming tuesday,
    a specific tuesday or all tuesdays
    "can you postpone all my events next week": yes, because the intention is clear which is to postpone,
    and next week refers to all dates next week so user doesn't have to further elaborate on the dates
    </examples>

    <task>
    1. Determine if there is sufficient information to proceed
    2. If not, ask the clarifying questions together in a short paragraph. E.g. Could you please clarify/elaborate/confirm.....
    </task>

    <expected_output_format>
    Always output strictly in JSON with the following keys:
    {{
        "adequate_information:  true | false",
        "clarifying_questions":  null <clarifying questions in a paragraph>,
        "reason": <short explanation>
    }}
    """
    LAYER1_PROMPT = f"""
    This is the user's message: {message}
    """
    response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[  
                {"role": "system", "content": LAYER1_ADMIN_PROMPT},
                {"role": "user", "content": LAYER1_PROMPT}
            ]
        )

    answer = response.choices[0].message.content.strip()
    return answer

def layer3_analysis(
    *,
    user_message: str,
    context_summary: str | None = None,
    intent: str,
    facts: dict | None = None,
    actions: list[dict] | None = None,
    session_id: str | None = None,
    **extra,
) -> Dict[str, Any]:
    print("--- LAYER 3 ANALYSIS TRIGGERED ---")

    # Source-of-truth clock (your user_now() should return aware datetime)
    now = user_now()
    tzname = now.tzname() or "UTC"
    today_iso = now.strftime("%Y-%m-%d")
    time_hm   = now.strftime("%H:%M")
    weekday   = now.strftime("%A")

    fs = context_tracker.get_focus_set(session_id) or {}

    # ---------- Tool specs shown to the model ----------
    TOOL_MANIFEST = """
    <available_tools>
    Plan actions using these types (do NOT execute them here):

    READS
    - fetch_events:
    params:
        • EITHER {"date":"YYYY-MM-DD"}
        • OR     {"start_date":"YYYY-MM-DD","end_date":"YYYY-MM-DD"}
    notes:
        • Use date-range only when you truly need multiple days.

    - get_free_slots:
    params (STRICT):
        {"date":"YYYY-MM-DD","min_duration":<int minutes>,"start_range":"HH:MM","end_range":"HH:MM"}
    rules:
        • min_duration MUST be an integer number of minutes (e.g., 120).
        • start_range/end_range MUST be 24h "HH:MM" strings.
        • ❌ Never use start_date/end_date here.
        • If you need several days, emit one get_free_slots per day.

    - summarize_day:
    params: {"date":"YYYY-MM-DD"}

    - find_event_by_keyword:
    params: {"query":"<text>","date_range":["YYYY-MM-DD","YYYY-MM-DD"]}  (date_range optional)

    - list_holding:
    params: {}   # returns items in the holding area

    WRITES (run only after user confirmation)
    - create_event:
    params: {"title":"...","start_time":"YYYY-MM-DDTHH:MM:SS","end_time":"YYYY-MM-DDTHH:MM:SS",
            "attendees"?:[], "location"?: "...", "description"?: "...", "layer"?: "work"|"personal"}

    - reschedule_event:
    params: {"event_id":"...","new_start":"YYYY-MM-DDTHH:MM:SS","new_end":"YYYY-MM-DDTHH:MM:SS","notify_attendees"?:false}

    - delete_event:
    params: {"event_id":"...", "reason"?: "..."}

    - block_time:
    params: {"start_time":"YYYY-MM-DDTHH:MM:SS","end_time":"YYYY-MM-DDTHH:MM:SS","reason"?: "Blocked time"}

    - shift_events_batch:
    params: {"source_date":"YYYY-MM-DD","target_date":"YYYY-MM-DD"}

    - create_holding:
    params: {"title":"...", "notes"?: "...", "layer"?: "work"|"personal"}

    - move_to_holding:
    params: {"event_id":"...", "reason"?: "..."}

    - promote_holding:
    params: {"item_id":"...", "start_time":"YYYY-MM-DDTHH:MM:SS","end_time":"YYYY-MM-DDTHH:MM:SS",
            "location"?: "...", "attendees"?: []}
    </available_tools>
    """

    # ---------- Output contract (strict) ----------
    L3_EXPECTED = f"""
<expected_output_format>
Return ONLY a JSON object:
{{
  "reply_text": "<2–4 sentences describing what happens next; include 'Step 1/Step 2'. If writes are proposed, end with a clear yes/no question.>",
  "internal_steps": ["step 1","step 2","..."],

  "required_actions": [
    {{ "type": "<fetch_events|get_free_slots|summarize_day|find_event_by_keyword|list_holding>",
       "parameters": {{ /* STRICT per-tool schema above */ }} }}
  ],

  "proposed_writes": [
    {{ "type": "<create_event|reschedule_event|delete_event|block_time|shift_events_batch|create_holding|move_to_holding|promote_holding>",
       "parameters": {{ /* STRICT per-tool schema above */ }} }}
  ],

  "debug": {{ "intent": "{intent}", "notes": "..." }},
  "confirmation_required": false
}}

GLOBAL RULES
- Today is {today_iso} ({weekday}), {time_hm} {tzname}. Use this as the truth for resolving any relative language.
- All date-only fields MUST be "YYYY-MM-DD".
- All datetime fields MUST be "YYYY-MM-DDTHH:MM:SS" (24h).
- Durations MUST be integer minutes (e.g., 90, 120) — never "1:30" or "2h".
- For week spans, explicitly output "start_date"/"end_date" as ISO dates (no phrases like "this week Monday").
- For get_free_slots:
    • DO NOT use start_date/end_date.
    • Emit one action per day you want to inspect.
    • Include start_range/end_range if relevant (HH:MM).
- If the request lacks a concrete datetime but the title/intent is clear, propose `create_holding` (confirmation required).
- If a conflict is detected or likely, you may propose `move_to_holding` for the conflicting event.
- When the user later provides a time for a holding item, plan `promote_holding` with start/end.
- Do not invent keys. Do not output null values. Do not include comments in JSON.
</expected_output_format>
"""
    
    LAYER3_ADMIN_PROMPT = f"""
<core_identity>
You are a calendar/scheduling planner. You only produce a plan; you do not execute tools.
Use the tool schemas exactly as specified. If a field is not allowed, do not include it.
Today is {today_iso} ({weekday}), {time_hm} {tzname}.
</core_identity>

<chat_context>
{context_summary or "[no additional context provided]"}
</chat_context>

<focus_context>
Focus Date: {fs.get("focus_date") or "[none]"}
Focus Events JSON: {json.dumps(fs.get("focus_events") or [], ensure_ascii=False)}
Rules:
- If the user says "tomorrow/that day", resolve to focus_date unless they explicitly provide another date.
- If the user says "it/them/existing events", resolve to focus_events.
- Always prefer explicit event_ids when rescheduling/deleting.
</focus_context>

{TOOL_MANIFEST}

<planning_guidance>
- Break the user's request into concrete steps.
- Put reads into "required_actions".
- Put any mutations into "proposed_writes" and set "confirmation_required": true.
- Avoid duplicate or redundant actions.
- Prefer inspecting *from today forward* unless the user explicitly asks for the past.

- If the request lacks a specific datetime but has a clear title/intent → add a write:
    {{ "type": "create_holding", "parameters": {{ "title": "<inferred title>", "notes": "<any extra>" }} }}
  Set "confirmation_required": true and ask the user if they want to park it in Holding.

- If the user says "park it", "stash it", "put into holding", "no date yet" → prefer create_holding.

- If you detect (or just checked) a conflict when rescheduling/creating:
  Offer two options in reply_text, and include one of these writes (behind confirmation):
    • move_to_holding (for the conflicting event)  OR
    • get_free_slots (as a required read) followed by promote_holding (once time is chosen later)

- If the user asks to see reserve items: include a read
    {{ "type": "list_holding", "parameters": {{}} }}
  and summarize the items in reply_text.

  
</planning_guidance>

{L3_EXPECTED}
"""


    LAYER3_PROMPT = f"This is the user's message:\n{user_message}\nIntent: {intent}"

    response = client.chat.completions.create(
        model="gpt-4.1",
        messages=[
            {"role": "system", "content": LAYER3_ADMIN_PROMPT},
            {"role": "user", "content": LAYER3_PROMPT}
        ]
    )
    raw = response.choices[0].message.content.strip()
    print(raw)

    plan = parse_layer3_output(raw)  # your existing robust JSON repair/parse

    # ---------- Post-processor (auto-fix common drifts) ----------
    def _minutes(v) -> int:
        # Accept 120, "120", "2:00", "2h", "90m"
        if isinstance(v, int):
            return v
        s = str(v).strip().lower()
        if s.isdigit():
            return int(s)
        if ":" in s:               # "2:00" -> 120
            hh, mm = s.split(":")
            return int(hh) * 60 + int(mm)
        if s.endswith("h"):        # "2h"
            return int(s[:-1]) * 60
        if s.endswith("m"):        # "90m"
            return int(s[:-1])
        raise ValueError(f"bad min_duration '{v}'")

    fixed_actions: list[dict] = []
    for act in (plan.get("required_actions") or []):
        t = act.get("type", "")
        params = dict(act.get("parameters") or {})
        if t == "get_free_slots":
            # If the model mistakenly gave a range, fan-out to per-day
            if "start_date" in params or "end_date" in params:
                start = params.get("start_date")
                end   = params.get("end_date")
                if start and end:
                    # expand to dates
                    from datetime import datetime, timedelta
                    sd = datetime.strptime(start, "%Y-%m-%d").date()
                    ed = datetime.strptime(end,   "%Y-%m-%d").date()
                    days = (ed - sd).days
                    for i in range(days + 1):
                        d = (sd + timedelta(days=i)).isoformat()
                        fixed_actions.append({
                            "type": "get_free_slots",
                            "parameters": {
                                "date": d,
                                "min_duration": _minutes(params.get("min_duration", 30)),
                                "start_range": params.get("start_range", "06:00"),
                                "end_range": params.get("end_range", "22:00"),
                            }
                        })
                # skip the original range-based action
                continue

            # Ensure strict fields & defaults
            if "min_duration" in params:
                params["min_duration"] = _minutes(params["min_duration"])
            else:
                params["min_duration"] = 30
            params.setdefault("start_range", "06:00")
            params.setdefault("end_range", "22:00")
            fixed_actions.append({"type": "get_free_slots", "parameters": params})

        else:
            fixed_actions.append(act)

    plan["required_actions"] = fixed_actions
    return plan


@app.route('/handle_user_message', methods=['POST'])
def user_mesage_handler():
    print("--- User message received, starting analysis ---")
    data = request.get_json()
    message = (data.get('message') or '').strip()
    session_id = data.get('session_id') or str(uuid.uuid4())

    # --- Pre-L1 follow-up router ---
    try:
        shortcut = preL1_check(
            message,
            session_id,
            get_pending_plan=get_pending_plan,
            clear_pending_plan=clear_pending_plan,
            layer4_execute=layer4_execute
        )
    except Exception as e:
        print(f"[PreL1 Error] {e}")
        shortcut = None

    if shortcut:
        try:
            context_tracker.update_ai(session_id, shortcut.get("reply_text", ""), metadata={"stage": "PreL1"})
        except Exception as e:
            print(f"[ContextTracker] update_ai failed: {e}")
        return jsonify(shortcut)

    # Store the user's message into context
    try:
        context_tracker.update_user(session_id, message)
    except Exception as e:
        print(f"[ContextTracker] update_user failed: {e}")

    # --- PRE-L1 CONTINUATION CHECK ---
    try:
        continuation = preL1_check(message, session_id)
    except Exception as e:
        print(f"[PreL1 Error] {e}")
        continuation = None

    if continuation == "confirm":
        plan = context_tracker.get_pending_plan(session_id)
        if not plan:
            reply = "⚠️ There’s no pending plan to confirm."
            return jsonify({
                "session_id": session_id,
                "reply_text": reply,
                "routed_to": "preL1"
            })

        try:
            # ✅ Pass session_id into L4
            l4_results = layer4_execute(plan, session_id=session_id, allow_writes=True)
            context_tracker.clear_pending_plan(session_id)
            reply_out = (l4_results or {}).get("final_reply") or "Done."
            context_tracker.update_ai(session_id, reply_out, metadata={"stage": "L4", "routed_to": "continuation"})
            return jsonify({
                "session_id": session_id,
                "reply_text": reply_out,
                "layer4_results": l4_results,
                "routed_to": "continuation"
            })
        except Exception as e:
            print(f"[L4 Error] {e}")
            return jsonify({
                "session_id": session_id,
                "reply_text": f"⚠️ Failed to apply pending plan: {e}",
                "routed_to": "continuation_error"
            })

    elif continuation == "cancel":
        if context_tracker.get_pending_plan(session_id):
            context_tracker.clear_pending_plan(session_id)
            reply = "Okay — I won’t apply those changes."
        else:
            reply = "There was no pending plan to cancel."
        context_tracker.update_ai(session_id, reply, metadata={"stage": "preL1", "routed_to": "continuation"})
        return jsonify({
            "session_id": session_id,
            "reply_text": reply,
            "routed_to": "continuation"
        })

    # --- LAYER 1 ANALYSIS ---
    layer1_output_text = layer1_analysis(message)
    print(layer1_output_text)
    layer1_output_parsed = parse_layer1_output(layer1_output_text)

    needs_previous_context = layer1_output_parsed["needs_previous_context"]
    intent = layer1_output_parsed["intent"]
    in_scope = layer1_output_parsed["in_scope"]
    immediate_reply_applicable = layer1_output_parsed["immediate_reply_applicable"]
    immediate_reply = layer1_output_parsed["immediate_reply"]
    next_steps_required = layer1_output_parsed["next_steps_required"]

    # If out of scope
    if not in_scope:
        reply = immediate_reply
        context_tracker.update_ai(session_id, reply, metadata={"stage": "L1", "routed_to": "out_of_scope"})
        return jsonify({
            "session_id": session_id,
            "reply_text": reply,
            "layer1": layer1_output_parsed,
            "routed_to": "out_of_scope"
        })

    # Immediate reply
    if immediate_reply_applicable and immediate_reply:
        context_tracker.update_ai(session_id, immediate_reply, metadata={"stage": "L1", "routed_to": "immediate"})
        return jsonify({
            "session_id": session_id,
            "reply_text": immediate_reply,
            "layer1": layer1_output_parsed,
            "routed_to": "immediate"
        })

    # No next steps
    if not next_steps_required:
        reply = "No next steps needed. End of response"
        context_tracker.update_ai(session_id, reply, metadata={"stage": "L1", "routed_to": "done"})
        return jsonify({
            "session_id": session_id,
            "reply_text": reply,
            "layer1": layer1_output_parsed,
            "routed_to": "done"
        })

    # --- LAYER 2 ---
    print("--- NEXT STEPS NEEDED ---")
    chat_context = "[no additional context provided]"
    if needs_previous_context:
        try:
            fetched = context_tracker.get_summary_string(session_id)
            if fetched:
                chat_context = fetched
        except Exception as e:
            print(f"[ContextTracker] get_summary_string failed: {e}")

    layer2_output_text = layer2_analysis(message, chat_context)
    print(layer2_output_text)

    try:
        layer2 = parse_layer2_output(layer2_output_text)

        if not layer2["adequate_information"]:
            clarify = layer2["clarifying_questions"] or "Could you share the missing details?"
            context_tracker.update_ai(session_id, clarify, metadata={"stage": "L2", "routed_to": "clarify"})
            return jsonify({
                "session_id": session_id,
                "reply_text": clarify,
                "layer1": layer1_output_parsed,
                "layer2": layer2,
                "routed_to": "clarify"
            })
        
        # --- PREP CONTEXT FOR L3 ---
        chat_context = context_tracker.get_summary_string(session_id) or ""
        recent = f"\n[latest]\nuser: {message}"
        chat_context = (chat_context or "") + recent

        # --- LAYER 3 ---
        layer3_result = layer3_analysis(
            session_id=session_id,
            user_message=message,
            context_summary=chat_context,
            intent=intent,
            layer1=layer1_output_parsed,
            layer2=layer2
        )

        if not isinstance(layer3_result, dict):
            print("[L3] Unexpected output type; falling back.")
            layer3_result = {
                "reply_text": "Got it — I’ll take it from here.",
                "internal_steps": ["Fallback: L3 returned non-dict"],
                "required_actions": [],
                "debug": {"intent": intent, "note": "L3 non-dict fallback"},
                "confirmation_required": False
            }

        final_text = layer3_result.get("reply_text") or "Okay."
        print("L3 plan (safe):", json.dumps(layer3_result, indent=2))

        if layer3_result.get("confirmation_required") is True:
            set_pending_plan(session_id, layer3_result)
            final_text = layer3_result.get("reply_text") or "I have a plan ready. Proceed?"
            context_tracker.update_ai(session_id, final_text, metadata={"stage": "L3", "routed_to": "await_confirm"})
            return jsonify({
                "session_id": session_id,
                "reply_text": final_text,
                "layer1": layer1_output_parsed,
                "layer2": layer2,
                "layer3": layer3_result.get("debug", {}),
                "layer3_plan": layer3_result,
                "routed_to": "await_confirm"
            })

        # --- LAYER 4 ---
        l4_results = None
        if layer3_result.get("required_actions"):
            try:
                # ✅ Pass session_id into L4
                l4_results = layer4_execute(layer3_result, session_id=session_id)
                print("L4 execution results:", json.dumps(l4_results, indent=2))
            except Exception as e:
                print(f"[L4 Error] {e}")
                l4_results = {"status": "error", "results": [], "final_reply": str(e)}

        # --- LAYER 5 ---
        l5_output = None
        if l4_results:  
            try:
                l5_output = layer5_synthesis(
                    user_message=message,
                    slim_l4_results=l4_results,
                    context_summary=chat_context
                )
                print("L5 synthesis results:", json.dumps(l5_output, indent=2))
            except Exception as e:
                print(f"[L5 Error] {e}")
                l5_output = {"final_reply": (l4_results or {}).get("final_reply") or "Done.", "confidence": 0.5, "next_actions": []}

        final_text = (
            (l5_output or {}).get("final_reply")
            or (l4_results or {}).get("final_reply")
            or layer3_result.get("reply_text")
            or "Okay."
        )

        context_tracker.update_ai(
            session_id,
            final_text,
            metadata={"stage": "L5" if l5_output else "L4", "routed_to": "layer5" if l5_output else "layer4"}
        )

        return jsonify({
            "session_id": session_id,
            "reply_text": final_text,
            "layer1": layer1_output_parsed,
            "layer2": layer2,
            "layer3": layer3_result.get("debug", {}),
            "layer3_plan": layer3_result,
            "layer4_results": l4_results,
            "layer5": l5_output,
            "routed_to": "layer5" if l5_output else "layer4"
        })

    except Exception as e:
        print(f"[Layer2 Parse Error] {e}")
        return jsonify({
            "session_id": session_id,
            "reply_text": layer2_output_text,
            "layer1": layer1_output_parsed,
            "routed_to": "layer2_raw"
        })


@app.route("/confirm_actions", methods=["POST"])
def confirm_actions():
    payload   = request.get_json() or {}
    confirmed = bool(payload.get("confirmed"))
    writes    = payload.get("writes") or []
    print("[/confirm_actions] confirmed:", confirmed)

    if not confirmed:
        return jsonify({"reply_text": "Okay — I won’t make any changes."})

    results   = []
    status    = "ok"
    final_msg = "All changes applied."

    for idx, act in enumerate(writes, start=1):
        act_type   = (act or {}).get("type")
        raw_params = (act or {}).get("parameters", {}) or {}
        try:
            # Make sure your normalizer ignores non-datetime fields and None.
            params, warns = normalize_datetime_params(raw_params)
            if warns:
                print(f"[/confirm_actions] normalize warnings for {act_type}:", warns)

            if act_type == "block_time":
                out = block_time(**params)
            elif act_type == "create_event":
                out = create_event(**params)
            elif act_type == "reschedule_event":
                out = reschedule_event(**params)
            elif act_type == "delete_event":
                out = delete_event(**params)
            elif act_type == "shift_events_batch":
                out = shift_events_batch(**params)

            # NEW holding writes
            elif act_type == "move_to_holding":
                # expects: {"event_id":"...", "reason"?: "..."}
                out = move_event_to_holding(**params)
            elif act_type == "promote_holding":
                # expects: {"event_id":"...","start_time":"YYYY-MM-DDTHH:MM:SS","end_time":"YYYY-MM-DDTHH:MM:SS"}
                out = promote_holding_to_event(**params)

            else:
                out = {"status": "error", "error": f"Unknown write action {act_type}"}

            results.append({"action": act_type, "status": "success", "output": out})
            if isinstance(out, dict) and out.get("status") == "error":
                status = "error"

        except Exception as e:
            status = "error"
            results.append({"action": act_type, "status": "error", "error": str(e)})

    if status != "ok":
        final_msg = "Some changes failed. Check logs."

    # OPTIONAL: kick L5 to generate a human-y success sentence
    # (only if you already have layer5_synthesis in this module)
    try:
        l5 = layer5_synthesis(
            user_message="(system) confirm_actions applied writes",
            slim_l4_results={"status": status, "results": results, "final_reply": final_msg},
            context_summary=context_tracker.get_summary_string(payload.get("session_id")) if 'context_tracker' in globals() else None
        )
        if l5 and l5.get("final_reply"):
            final_msg = l5["final_reply"]
    except Exception as e:
        print("[/confirm_actions] L5 synthesis skipped:", e)

    return jsonify({
        "reply_text": final_msg,
        "layer4_results": {"status": status, "results": results, "final_reply": final_msg}
    })

# Run the app
if __name__ == '__main__':
    app.run(debug=True, port="8000")

