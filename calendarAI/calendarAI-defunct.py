from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv
from utility.context_tracker import ContextTracker
from utility.conversation_state import ConversationState
from utility.state_strategies import stage_strategies
import os
import json
import uuid
import threading
from datetime import datetime, timedelta
from openai import OpenAI
from flask_cors import CORS
import re
import calendar

# =========================
# App bootstrap
# =========================
app = Flask(__name__)
CORS(app)
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# State helpers
context_tracker = ContextTracker()
conversation_state = ConversationState()

# Where JSON lives (MVP store)
DATA_DIR = os.getenv("CAL_DATA_DIR", "./data")
EVENTS_PATH = os.path.join(DATA_DIR, "events.json")
os.makedirs(DATA_DIR, exist_ok=True)
if not os.path.exists(EVENTS_PATH):
    with open(EVENTS_PATH, "w", encoding="utf-8") as f:
        json.dump([], f)

# =========================
# Calendar JSON store
# =========================
class CalendarStore:
    """
    Minimal JSON adapter for events.
    Event schema:
    {
      "id": "uuid",
      "title": "str",
      "start": "YYYY-MM-DDTHH:MM",
      "end":   "YYYY-MM-DDTHH:MM",
      "all_day": false,
      "location": "str",
      "description": "str",
      "layer": "str"
    }
    """
    _lock = threading.Lock()

    @staticmethod
    def _load():
        with CalendarStore._lock:
            with open(EVENTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)

    @staticmethod
    def _save(events):
        with CalendarStore._lock:
            with open(EVENTS_PATH, "w", encoding="utf-8") as f:
                json.dump(events, f, ensure_ascii=False, indent=2)

    @staticmethod
    def list_events(start_iso=None, end_iso=None, layer_ids=None):
        events = CalendarStore._load()
        if start_iso or end_iso:
            def in_range(ev):
                s = datetime.fromisoformat(ev["start"])
                e = datetime.fromisoformat(ev["end"])
                if start_iso and e < datetime.fromisoformat(start_iso):
                    return False
                if end_iso and s > datetime.fromisoformat(end_iso):
                    return False
                return True
            events = [ev for ev in events if in_range(ev)]
        if layer_ids:
            events = [ev for ev in events if ev.get("layer") in layer_ids]
        return events

    @staticmethod
    def create_event(payload):
        events = CalendarStore._load()
        new_ev = {
            "id": str(uuid.uuid4()),
            "title": payload.get("title", "(untitled)"),
            "start": payload["start"],
            "end": payload["end"],
            "all_day": bool(payload.get("all_day", False)),
            "location": payload.get("location") or "",
            "description": payload.get("description") or "",
            "layer": payload.get("layer") or "personal",
        }
        events.append(new_ev)
        CalendarStore._save(events)
        return new_ev

    @staticmethod
    def update_event(event_id, patch):
        events = CalendarStore._load()
        for ev in events:
            if ev["id"] == event_id:
                ev.update({k: v for k, v in patch.items() if k in (
                    "title","start","end","all_day","location","description","layer","id"
                )})
                CalendarStore._save(events)
                return ev
        raise ValueError("Event not found")

    @staticmethod
    def delete_event(event_id):
        events = CalendarStore._load()
        new_list = [ev for ev in events if ev["id"] != event_id]
        if len(new_list) == len(events):
            raise ValueError("Event not found")
        CalendarStore._save(new_list)
        return True

    @staticmethod
    def find_free_time(date_iso, window_start, window_end, duration_min, layer_ids=None):
        ws = datetime.fromisoformat(f"{date_iso}T{window_start}")
        we = datetime.fromisoformat(f"{date_iso}T{window_end}")
        if we <= ws:
            raise ValueError("window_end must be after window_start")

        busy = []
        for ev in CalendarStore.list_events(
            start_iso=ws.isoformat(timespec="minutes"),
            end_iso=we.isoformat(timespec="minutes"),
            layer_ids=layer_ids
        ):
            s = datetime.fromisoformat(ev["start"])
            e = datetime.fromisoformat(ev["end"])
            s = max(s, ws)
            e = min(e, we)
            if e > s:
                busy.append((s, e))

        busy.sort()
        merged = []
        for s, e in busy:
            if not merged or s > merged[-1][1]:
                merged.append([s, e])
            else:
                merged[-1][1] = max(merged[-1][1], e)

        cursor = ws
        dur = timedelta(minutes=int(duration_min))
        for s, e in merged:
            if s - cursor >= dur:
                return {"start": cursor.isoformat(timespec="minutes"),
                        "end":   (cursor + dur).isoformat(timespec="minutes")}
            cursor = max(cursor, e)

        if we - cursor >= dur:
            return {"start": cursor.isoformat(timespec="minutes"),
                    "end":   (cursor + dur).isoformat(timespec="minutes")}
        return None

# =========================
# Tool schemas & dispatch
# =========================
def calendar_tool_schemas():
    return [
        {
            "type": "function",
            "function": {
                "name": "get_events_in_range",
                "description": "List calendar events in a time range.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "layers": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["start", "end"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "find_free_time",
                "description": "Find first available slot in a window.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string"},
                        "window_start": {"type": "string"},
                        "window_end": {"type": "string"},
                        "duration_min": {"type": "integer"},
                        "layers": {"type": "array", "items": {"type": "string"}}
                    },
                    "required": ["date", "window_start", "window_end", "duration_min"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "create_event",
                "description": "Create a new calendar event.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "start": {"type": "string"},
                        "end": {"type": "string"},
                        "all_day": {"type": "boolean"},
                        "location": {"type": "string"},
                        "description": {"type": "string"},
                        "layer": {"type": "string"}
                    },
                    "required": ["title", "start", "end"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "update_event",
                "description": "Update an event.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "event_id": {"type": "string"},
                        "patch": {"type": "object"}
                    },
                    "required": ["event_id", "patch"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "delete_event",
                "description": "Delete an event.",
                "parameters": {
                    "type": "object",
                    "properties": {"event_id": {"type": "string"}},
                    "required": ["event_id"]
                }
            }
        }
    ]

def tool_get_events_in_range(args):
    return {"events": CalendarStore.list_events(args["start"], args["end"], args.get("layers"))}

def tool_find_free_time(args):
    return {"slot": CalendarStore.find_free_time(
        args["date"], args["window_start"], args["window_end"],
        args["duration_min"], args.get("layers"))}

def tool_create_event(args):
    return {"created": CalendarStore.create_event(args)}

def tool_update_event(args):
    return {"updated": CalendarStore.update_event(args["event_id"], args["patch"])}

def tool_delete_event(args):
    return {"deleted": CalendarStore.delete_event(args["event_id"])}

TOOL_IMPL = {
    "get_events_in_range": tool_get_events_in_range,
    "find_free_time":      tool_find_free_time,
    "create_event":        tool_create_event,
    "update_event":        tool_update_event,
    "delete_event":        tool_delete_event,
}

# =========================
# Validation (Layer 2 guardrails)
# =========================
def validate_tool_call(tool_name, args):
    """
    Hard validations to prevent bad tool executions.
    Returns (status, issues) where status in {"OK","BLOCK"}.
    """
    issues = []

    if tool_name == "get_events_in_range":
        if not args.get("start") or not args.get("end"):
            issues.append("Missing start or end date.")
    elif tool_name == "create_event":
        if not args.get("start") or not args.get("end"):
            issues.append("Missing event start/end.")
        if "title" not in args:
            # We allow default "(untitled)" but warn here if you want; keeping strict:
            pass
    elif tool_name in ["update_event", "delete_event"]:
        if not args.get("event_id"):
            issues.append("Missing event_id.")
    elif tool_name == "find_free_time":
        for f in ["date", "window_start", "window_end", "duration_min"]:
            if not args.get(f):
                issues.append(f"Missing {f}.")

    return ("OK", []) if not issues else ("BLOCK", issues)

# =========================
# Layer 1 Prompt (YOUR VERSION)
# =========================
LAYER1_PROMPT = """
Layer 1:
You are a useful AI that manages everything regarding the user's calendar, scheduling and related events/information. 
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

** You should also not be too rigid and be able to handle basic conversation with the user, 
such as small talk, greetings, simple qnAs. Its just that if what the user says if very out of scope
of what you do, then align the user back.

Your role is to analyse the given information, and then analyse:
1) Is this a new request or dependent on previous context?
2) Identify the user’s intent (e.g., reschedule, retrieve info, ask for a briefing, request advice).
3) Figure out whether the request falls within the capabilities and scope of this calendar AI.
4) Check if there is enough information/context provided by the user prompt to invoke an action or if further clarification is needed. If ambiguous, clarify them.
5) If step 4 is yes, what would be the steps and tools to be invoked?

Always output strictly in JSON with the following keys:
{
  "is_new_request": true | false,
  "needs_previous_context": true | false,
  "intent": "reschedule|create|delete|info|briefing|advice|other|unknown",
  "in_scope": true | false,
  "info_sufficient": true | false,
  "missing_fields": ["month","date","time"],
  "tool_plan": [
    {"tool":"get_events_in_range","args":{"start":"...","end":"..."}}
  ]
}
"""

AGENT_MODEL = os.getenv("AGENT_MODEL", "gpt-4o-mini")
MAX_TOOL_TURNS = 4

# =========================
# Admin Agent (Layer 1 + Layer 2)
# =========================
def run_calendar_agent_admin_v2(user_message, session_id, context_summary=None, user_prefs=None):
    """
    Layer 1: Analysis-only JSON using LAYER1_PROMPT
    Layer 2: Controller/guardrails — clarify if info insufficient, otherwise execute tool_plan (validated)
    Returns: (user_reply, actions, admin_reasoning_json)
    """
    # ---- Layer 1: Analysis ----
    l1_messages = [{"role": "system", "content": LAYER1_PROMPT},
                   {"role": "user", "content": user_message}]
    l1_resp = client.chat.completions.create(
        model=AGENT_MODEL,
        messages=l1_messages,
        temperature=0
    )
    try:
        analysis = json.loads(l1_resp.choices[0].message.content)
    except Exception:
        analysis = {
            "is_new_request": True,
            "needs_previous_context": True,
            "intent": "unknown",
            "in_scope": True,
            "info_sufficient": False,
            "missing_fields": ["parse_error"],
            "tool_plan": []
        }

    admin_reasoning = analysis

    # ---- Layer 2: Controller ----
    # If out of scope
    if not analysis.get("in_scope", True):
        return ("Sorry, that’s outside what I can do. I can help with scheduling, event info, briefings, and calendar insights.", [], admin_reasoning)

    # If info insufficient → ask for clarifications (build a crisp, specific question)
    if not analysis.get("info_sufficient", False):
        missing = analysis.get("missing_fields", [])
        if missing:
            # Map common missing fields to friendly questions
            prompts = []
            if "month" in missing:
                prompts.append("Which month (and year) do you mean?")
            if "date" in missing:
                prompts.append("Which date(s) should I use?")
            if "time" in missing:
                prompts.append("What time should I use?")
            if not prompts:
                prompts.append("Could you share the missing details?")
            question = "I can help with that. " + " ".join(prompts)
        else:
            question = "I can help with that. Could you provide a bit more detail?"
        return (question, [], admin_reasoning)

    # If info sufficient → validate & run tool plan
    actions = []
    for step in analysis.get("tool_plan", []):
        name = step.get("tool")
        args = step.get("args", {})
        status, issues = validate_tool_call(name, args)
        if status == "BLOCK":
            reply = f"I need a bit more info before I can proceed: {', '.join(issues)}."
            return (reply, actions, admin_reasoning)

        impl = TOOL_IMPL.get(name)
        if not impl:
            actions.append({"tool": name, "args": args, "error": "Unknown tool"})
            continue
        try:
            result = impl(args)
            actions.append({"tool": name, "args": args, "result": result})
        except Exception as e:
            actions.append({"tool": name, "args": args, "error": str(e)})

    # Simple user-facing reply (you can replace with a Layer 3 NLG later)
    final_reply = "Done. I've completed the requested calendar action."
    return (final_reply, actions, admin_reasoning)

# =========================
# (Optional) Simple user-mode agent
# =========================
def run_calendar_agent_user(user_message, context_summary=None, user_prefs=None):
    system_prompt = (
        "You are a helpful Calendar Assistant. "
        "Be concise and friendly. Always use tools to check the calendar, never guess."
    )
    if user_prefs:
        system_prompt += f"\nUser preferences: {json.dumps(user_prefs)}"
    if context_summary:
        system_prompt += f"\nConversation summary: {context_summary}"

    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}]
    tools = calendar_tool_schemas()
    actions = []

    for _ in range(MAX_TOOL_TURNS):
        resp = client.chat.completions.create(
            model=AGENT_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.2
        )
        msg = resp.choices[0].message

        if msg.tool_calls:
            for tc in msg.tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments or "{}")
                impl = TOOL_IMPL.get(name)
                try:
                    result_payload = impl(args) if impl else {"error": f"Unknown tool {name}"}
                except Exception as e:
                    result_payload = {"error": str(e)}
                actions.append({"tool": name, "args": args, "result": result_payload})
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": name,
                    "content": json.dumps(result_payload, ensure_ascii=False)
                })
            continue

        final_text = msg.content or "(no content)"
        return final_text, actions

    return "I reached my internal step limit.", actions

# =========================
# Simple classifier (optional)
# =========================
def classify_intent_openai(message):
    system_prompt = (
        "You are an AI assistant that classifies user messages. "
        "Return JSON with 'intent' and 'refer_to_context'. Valid intents: "
        "greeting, question, call_to_action, product_interest, request, feedback, spam, unknown.\n\n"
        f"User message:\n{message.strip()}"
    )
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0
        )
        parsed = json.loads(response.choices[0].message.content.strip())
        return parsed.get("intent", "unknown"), parsed.get("refer_to_context", False)
    except Exception:
        return "unknown", False

# =========================
# Routes
# =========================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin_view():
    return render_template('admin.html')

@app.route('/generate_reply', methods=['POST'])
def generate_reply():
    """User mode endpoint (simple)"""
    data = request.get_json()
    message = (data.get('message') or '').strip()
    session_id = data.get('session_id') or str(uuid.uuid4())
    context_summary = context_tracker.get_summary_string(session_id)
    user_prefs = {"timezone": "local", "default_layer": "personal"}

    ai_text, actions = run_calendar_agent_user(
        user_message=message,
        context_summary=context_summary,
        user_prefs=user_prefs
    )
    return jsonify({"ai_reply": ai_text, "actions": actions, "session_id": session_id})

@app.route('/generate_reply_admin', methods=['POST'])
def generate_reply_admin():
    """Admin mode endpoint: returns admin reasoning JSON + user-facing reply + actions log"""
    data = request.get_json()
    message = (data.get('message') or '').strip()
    session_id = data.get('session_id') or str(uuid.uuid4())

    # Optional: classify to update your state panel
    intent, refer_to_context = classify_intent_openai(message)

    # Update logs
    context_tracker.update_user(session_id, f"user said: '{message[:140]}'")
    context_summary = context_tracker.get_summary_string(session_id)
    conversation_state.update(session_id, intent, message, context_summary)

    # Run admin agent (Layer 1 + Layer 2)
    ai_text, actions, admin_reasoning = run_calendar_agent_admin_v2(
        user_message=message,
        session_id=session_id,
        context_summary=context_summary if refer_to_context else None,
        user_prefs={"timezone": os.getenv("CAL_TZ", "local"), "default_layer": "personal"}
    )

    # Log assistant reply
    context_tracker.update_ai(
        session_id,
        ai_text,
        metadata={"intent": intent, "actions": actions, "context_used": refer_to_context, "admin_reasoning": admin_reasoning}
    )

    return jsonify({
        "session_id": session_id,
        "intent": intent,
        "refer_to_context": refer_to_context,
        "context_summary": context_summary,
        "admin_reasoning": admin_reasoning,  # JSON analysis from Layer 1
        "ai_reply": ai_text,                 # user-facing message
        "actions": actions
    })

# =========================
# Run
# =========================
if __name__ == '__main__':
    app.run(debug=True)
