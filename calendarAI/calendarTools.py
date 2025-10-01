# calendarTools.py
"""
Calendar tools with optional JSON-backed persistent store.

Modes:
- USE_JSON_STORE = True  -> Read/write events to EVENT_STORE_PATH (your schema)
- USE_JSON_STORE = False -> Deterministic mock generation (legacy behavior)

Public API is unchanged:
  fetch_events, get_free_slots, create_event, reschedule_event,
  delete_event, summarize_day, block_time, shift_events_batch,
  find_event_by_keyword, resolve_relative_date, resolve_relative_datetime, etc.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date as _date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
import itertools
import random

# -------- Mode toggle --------
USE_JSON_STORE = True
EVENT_STORE_PATH = os.environ.get("EVENT_STORE_PATH", "./mock_events.json")

_TIME_RE = re.compile(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b', re.I)

# ------------------------------
# Utilities: Dates & Parsing
# ------------------------------

WEEKDAY_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

def _iso_today() -> str:
    return _date.today().isoformat()

def get_today() -> str:
    """Return today's date in ISO format (YYYY-MM-DD)."""
    return _iso_today()

def _parse_iso_date(d: str) -> datetime:
    return datetime.strptime(d, "%Y-%m-%d")

def _combine(date_str: str, time_str: str) -> str:
    """Combine 'YYYY-MM-DD' and 'HH:MM' -> ISO datetime 'YYYY-MM-DDTHH:MM:00'."""
    # if time already includes seconds, preserve
    if len(time_str.split(":")) == 3:
        return f"{date_str}T{time_str}"
    return f"{date_str}T{time_str}:00"

def _ensure_seconds(iso_dt: Optional[str]) -> Optional[str]:
    if not iso_dt:          # handles None / empty string
        return None
    try:
        datetime.strptime(iso_dt, "%Y-%m-%dT%H:%M:%S")
        return iso_dt
    except Exception:
        dt = datetime.strptime(iso_dt, "%Y-%m-%dT%H:%M")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")

def _parse_iso_dt(s: str) -> datetime:
    s = _ensure_seconds(s)
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S")

def get_week_dates(containing_date: str, week_starts_on: str = "monday") -> List[str]:
    dt = _parse_iso_date(containing_date)
    start_idx = WEEKDAY_MAP.get(week_starts_on.lower(), 0)
    delta = (dt.weekday() - start_idx) % 7
    week_start = dt - timedelta(days=delta)
    return [(week_start + timedelta(days=i)).date().isoformat() for i in range(7)]

def resolve_week(expression: str, base_date: Optional[str] = None, week_starts_on: str = "monday") -> List[str]:
    base = _parse_iso_date(base_date) if base_date else _parse_iso_date(_iso_today())
    expr = expression.strip().lower()

    if expr in ("this week", "current week"):
        return get_week_dates(base.date().isoformat(), week_starts_on=week_starts_on)

    if expr == "next week":
        next_week_base = base + timedelta(days=7)
        return get_week_dates(next_week_base.date().isoformat(), week_starts_on=week_starts_on)

    m = re.match(r"week of (\d{4}-\d{2}-\d{2})", expr)
    if m:
        anchor = m.group(1)
        return get_week_dates(anchor, week_starts_on=week_starts_on)

    raise ValueError(f"Cannot resolve week expression: {expression}")

def resolve_relative_date(expr: str, base: datetime | None = None) -> str:
    base = base or datetime.now()
    s = expr.strip().lower()
    if s in ("today",):
        return base.strftime("%Y-%m-%d")
    if s in ("tomorrow",):
        return (base + timedelta(days=1)).strftime("%Y-%m-%d")
    # Example: simple Friday resolver
    if "this friday" in s or s == "friday":
        dow = 4  # Monday=0
        delta = (dow - base.weekday()) % 7
        target = base + timedelta(days=delta)
        return target.strftime("%Y-%m-%d")
    # fallback: already ISO?
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return s
    except:
        raise ValueError(f"Unrecognized date expression: {expr}")

# ------------------------------
# JSON Store Helpers
# ------------------------------

def _load_store() -> Dict[str, Dict[str, Any]]:
    if not USE_JSON_STORE:
        return {}
    if not os.path.exists(EVENT_STORE_PATH):
        return {}
    try:
        with open(EVENT_STORE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Ensure all date-times have seconds for internal consistency
        for ev in data.values():
            s = ev.get("start")
            e = ev.get("end")
            ev["start"] = _ensure_seconds(s) if s else None
            ev["end"]   = _ensure_seconds(e) if e else None
        return data
    except Exception as e:
        print(f"[calendarTools] Failed to load store: {e}")
        return {}

def _save_store(store: Dict[str, Dict[str, Any]]) -> None:
    if not USE_JSON_STORE:
        return
    try:
        os.makedirs(os.path.dirname(EVENT_STORE_PATH) or ".", exist_ok=True)
        with open(EVENT_STORE_PATH, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[calendarTools] Failed to save store: {e}")

def _new_id() -> str:
    return str(uuid.uuid4())

# ------------------------------
# Legacy Mock Data (fallback)
# ------------------------------

def _seed_from_date(date_str: str) -> int:
    return int(date_str.replace("-", ""))

def _mock_events_for_date(date_str: str) -> List[Dict[str, Any]]:
    rnd = random.Random(_seed_from_date(date_str))
    n = rnd.choice([0, 1, 2, 3])
    templates = [
        ("Morning Standup", "09:00", "09:30"),
        ("Client Sync", "14:00", "15:00"),
        ("Project Deep Dive", "11:00", "12:00"),
        ("1:1", "16:00", "16:30"),
        ("Team Retro", "15:30", "16:30"),
    ]
    events = []
    for i in range(n):
        title, start_t, end_t = rnd.choice(templates)
        eid = f"evt_{date_str.replace('-', '')}_{i+1:03d}"
        events.append({
            "event_id": eid,
            "title": title,
            "start": _ensure_seconds(_combine(date_str, start_t)),
            "end": _ensure_seconds(_combine(date_str, end_t)),
            "attendees": [],
            "location": "TBD",
            "description": None,
        })
    events.sort(key=lambda e: e["start"])
    return events

# ------------------------------
# Core Calendar Functions
# ------------------------------

def fetch_events(date: Optional[str] = None,
                 start_date: Optional[str] = None,
                 end_date: Optional[str] = None,
                 filters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Fetch events for a single date or an inclusive date range.
    If USE_JSON_STORE=True, pull from JSON store; otherwise, legacy mock.
    """
    if not date and not (start_date and end_date):
        return {"status": "error", "message": "Provide `date` or `start_date`+`end_date`."}

    if date:
        days = [date]
    else:
        start_dt = _parse_iso_date(start_date)  # type: ignore[arg-type]
        end_dt = _parse_iso_date(end_date)      # type: ignore[arg-type]
        if end_dt < start_dt:
            return {"status": "error", "message": "end_date cannot be before start_date."}
        days = [(start_dt + timedelta(days=i)).date().isoformat()
                for i in range((end_dt - start_dt).days + 1)]

    out_events: List[Dict[str, Any]] = []

    if USE_JSON_STORE:
        store = _load_store()
        # Store is a dict keyed by ID; filter by date
        for ev in store.values():
            if ev.get("status") == "holding":
                continue  # skip holding items in normal calendar fetches
            # ignore deleted exception entries if you choose
            s = ev.get("start"); e = ev.get("end")
            if not s or not e: 
                continue
            ev_date = s.split("T")[0]
            if ev_date in days:
                # adapt to L4/L5 expected fields (event_id, start, end, title)
                out_events.append({
                    "event_id": ev["id"],
                    "title": ev.get("title", ""),
                    "start": _ensure_seconds(ev["start"]),
                    "end": _ensure_seconds(ev["end"]),
                    "attendees": ev.get("attendees", []),
                    "location": ev.get("location", ""),
                    "description": ev.get("description"),
                    "layer": ev.get("layer", "work"),
                })
    else:
        out_events = list(itertools.chain.from_iterable(_mock_events_for_date(d) for d in days))

    # Minimal filter support
    if filters and "query" in filters:
        q = filters["query"].lower()
        out_events = [e for e in out_events if q in e["title"].lower()]

    # sort by start
    out_events.sort(key=lambda e: e["start"])
    return {"status": "success", "events": out_events}

def get_free_slots(date: str,
                   min_duration: int,
                   start_range: str = "09:00",
                   end_range: str = "18:00") -> Dict[str, Any]:
    window_start = _parse_iso_dt(_combine(date, start_range))
    window_end = _parse_iso_dt(_combine(date, end_range))
    if window_end <= window_start:
        return {"status": "error", "message": "end_range must be after start_range."}

    events_resp = fetch_events(date=date)
    if events_resp["status"] != "success":
        return events_resp
    busy = [(_parse_iso_dt(e["start"]), _parse_iso_dt(e["end"])) for e in events_resp["events"]]
    busy.sort()

    merged = []
    for s, e in busy:
        if not merged or s > merged[-1][1]:
            merged.append([s, e])
        else:
            merged[-1][1] = max(merged[-1][1], e)

    free: List[Tuple[datetime, datetime]] = []
    cursor = window_start
    for s, e in merged:
        if s > cursor:
            free.append((cursor, s))
        cursor = max(cursor, e)
    if cursor < window_end:
        free.append((cursor, window_end))

    out = []
    for s, e in free:
        dur = int((e - s).total_seconds() // 60)
        if dur >= min_duration:
            out.append({"start": s.strftime("%Y-%m-%dT%H:%M:%S"),
                        "end": e.strftime("%Y-%m-%dT%H:%M:%S")})

    return {"status": "success", "free_slots": out}

def _store_event(obj: Dict[str, Any]) -> Dict[str, Any]:
    store = _load_store()
    store[obj["id"]] = obj
    _save_store(store)
    return obj

def _update_event(ev_id: str, patch: Dict[str, Any]) -> Dict[str, Any]:
    store = _load_store()
    if ev_id not in store:
        return {"status": "error", "message": f"Event '{ev_id}' not found."}
    store[ev_id].update(patch)
    store[ev_id]["updated_at"] = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    _save_store(store)
    return {"status": "success", "event": store[ev_id]}

def _remove_event(ev_id: str) -> Dict[str, Any]:
    store = _load_store()
    if ev_id not in store:
        return {"status": "error", "message": f"Event '{ev_id}' not found."}
    del store[ev_id]
    _save_store(store)
    return {"status": "success"}

def create_event(title: str,
                 start_time: str,
                 end_time: str,
                 attendees: Optional[List[str]] = None,
                 location: Optional[str] = None,
                 description: Optional[str] = None,
                 layer: str = "work",
                 all_day: bool = False) -> Dict[str, Any]:
    """
    Create a real event if USE_JSON_STORE, otherwise mock-return.
    """
    start_time = _ensure_seconds(start_time)
    end_time   = _ensure_seconds(end_time)

    if not USE_JSON_STORE:
        rid = random.randint(1000, 9999)
        return {
            "status": "success",
            "event_id": f"evt_{rid}",
            "message": f"Event '{title}' created from {start_time} to {end_time}.",
            "echo": {"title": title, "start_time": start_time, "end_time": end_time,
                     "attendees": attendees or [], "location": location, "description": description}
        }

    ev_id = _new_id()
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    obj = {
        "id": ev_id,
        "title": title,
        "start": start_time,
        "end": end_time,
        "location": location or "",
        "description": description or "",
        "all_day": all_day,
        "layer": layer,
        "is_recurring_instance": False,
        "is_deletion_exception": False,
        "is_moved_exception": False,
        "original_pattern_id": None,
        "original_occurrence_date": None,
        "created_at": now,
        "updated_at": now,
        "attendees": attendees or []
    }
    _store_event(obj)
    return {"status": "success", "event_id": ev_id, "message": f"Event '{title}' created.", "event": obj}

def reschedule_event(event_id: str, new_start: str, new_end: str, notify_attendees: bool = False) -> Dict[str, Any]:
    new_start = _ensure_seconds(new_start)
    new_end   = _ensure_seconds(new_end)

    if not USE_JSON_STORE:
        return {
            "status": "success",
            "message": f"Event '{event_id}' rescheduled to {new_start}–{new_end}.",
            "notify_attendees": notify_attendees
        }

    res = _update_event(event_id, {"start": new_start, "end": new_end})
    if res.get("status") != "success":
        return res
    return {
        "status": "success",
        "message": f"Event '{event_id}' rescheduled to {new_start}–{new_end}.",
        "notify_attendees": notify_attendees,
        "event": res["event"]
    }

def delete_event(event_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    if not USE_JSON_STORE:
        return {"status": "success", "message": f"Event '{event_id}' deleted." + (f" Reason: {reason}" if reason else "")}
    res = _remove_event(event_id)
    if res.get("status") != "success":
        return res
    return {"status": "success", "message": f"Event '{event_id}' deleted." + (f" Reason: {reason}" if reason else "")}

def summarize_day(date: str) -> Dict[str, Any]:
    resp = fetch_events(date=date)
    if resp["status"] != "success":
        return resp

    events = resp["events"]
    if not events:
        summary = f"On {date}, your calendar is clear."
    else:
        bullets = []
        for e in events:
            start_t = _ensure_seconds(e["start"]).split("T")[1][:5]
            end_t = _ensure_seconds(e["end"]).split("T")[1][:5]
            bullets.append(f"- {e['title']} ({start_t}–{end_t})")
        summary = f"On {date}, you have {len(events)} event(s):\n" + "\n".join(bullets)

    return {"status": "success", "summary": summary, "events": events}

def block_time(start_time: str, end_time: str, reason: str = "Blocked time") -> Dict[str, Any]:
    start_time = _ensure_seconds(start_time)
    end_time   = _ensure_seconds(end_time)
    if not USE_JSON_STORE:
        rid = random.randint(1000, 9999)
        return {"status": "success", "event_id": f"block_{rid}", "message": f"Blocked {start_time}–{end_time} for '{reason}'."}
    return create_event(title=reason, start_time=start_time, end_time=end_time, layer="work", description="Auto block")

def shift_events_batch(source_date: str, target_date: str) -> Dict[str, Any]:
    resp = fetch_events(date=source_date)
    if resp["status"] != "success":
        return resp
    shifted_ids = []
    for e in resp["events"]:
        dur = _parse_iso_dt(e["end"]) - _parse_iso_dt(e["start"])
        new_start = _ensure_seconds(_combine(target_date, e["start"].split("T")[1][:5]))
        new_end = (_parse_iso_dt(new_start) + dur).strftime("%Y-%m-%dT%H:%M:%S")
        r = reschedule_event(e["event_id"], new_start, new_end)
        if r.get("status") == "success":
            shifted_ids.append(e["event_id"])
    return {"status": "success", "message": f"Shifted {len(shifted_ids)} event(s) from {source_date} to {target_date}.", "shifted_event_ids": shifted_ids}

def find_event_by_keyword(query: str, date_range: Optional[Tuple[str, str]] = None) -> Dict[str, Any]:
    if date_range is None:
        week = get_week_dates(_iso_today())
        start_d, end_d = week[0], week[-1]
    else:
        start_d, end_d = date_range
    resp = fetch_events(start_date=start_d, end_date=end_d, filters={"query": query})
    if resp["status"] != "success":
        return resp
    return {"status": "success", "results": resp["events"]}

# ------------------------------
# Helpers: Natural Language → Datetimes
# ------------------------------

def resolve_dates_for_phrase(phrase: str, base_date: Optional[str] = None) -> Dict[str, Any]:
    p = phrase.strip().lower()
    try:
        if p in ("this week", "next week") or p.startswith("week of"):
            return {"kind": "week", "dates": resolve_week(p, base_date=base_date)}
        return {"kind": "single", "date": resolve_relative_date(p, base_date=base_date)}
    except Exception as e:
        return {"kind": "error", "message": str(e)}

def resolve_relative_datetime(expr: str, base: datetime | None = None) -> str:
    base = base or datetime.now()
    s = expr.strip()
    m = re.match(r"(.+?)\s+(\d{1,2}:\d{2})$", s)
    if m:
        date_part, time_part = m.group(1).strip(), m.group(2)
        ymd = resolve_relative_date(date_part, base)
        return f"{ymd}T{time_part}:00"
    try:
        datetime.fromisoformat(s.replace("Z",""))
        return _ensure_seconds(s)
    except:
        pass
    try:
        dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
        return dt.strftime("%Y-%m-%dT%H:%M:00")
    except:
        pass
    try:
        ymd = resolve_relative_date(s, base)
        return f"{ymd}T00:00:00"
    except Exception as e:
        raise ValueError(f"Unrecognized datetime expression: {expr}") from e

# ------------------------------
# Router for Layer 4
# ------------------------------

def handle_action(action_type: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
    try:
        if action_type == "fetch_events":
            return fetch_events(
                date=parameters.get("date"),
                start_date=parameters.get("start_date"),
                end_date=parameters.get("end_date"),
                filters=parameters.get("filters"),
            )
        if action_type == "get_free_slots":
            return get_free_slots(
                date=parameters["date"],
                min_duration=int(parameters["min_duration"]),
                start_range=parameters.get("start_range", "09:00"),
                end_range=parameters.get("end_range", "18:00"),
            )
        if action_type == "create_event":
            return create_event(
                title=parameters["title"],
                start_time=parameters["start_time"],
                end_time=parameters["end_time"],
                attendees=parameters.get("attendees"),
                location=parameters.get("location"),
                description=parameters.get("description"),
                layer=parameters.get("layer", "work"),
                all_day=parameters.get("all_day", False),
            )
        if action_type == "reschedule_event":
            return reschedule_event(
                event_id=parameters["event_id"],
                new_start=parameters["new_start"],
                new_end=parameters["new_end"],
                notify_attendees=parameters.get("notify_attendees", False),
            )
        if action_type == "delete_event":
            return delete_event(
                event_id=parameters["event_id"],
                reason=parameters.get("reason"),
            )
        if action_type == "summarize_day":
            return summarize_day(date=parameters["date"])
        if action_type == "block_time":
            return block_time(
                start_time=parameters["start_time"],
                end_time=parameters["end_time"],
                reason=parameters.get("reason", "Blocked time"),
            )
        if action_type == "shift_events_batch":
            return shift_events_batch(
                source_date=parameters["source_date"],
                target_date=parameters["target_date"],
            )
        if action_type == "find_event_by_keyword":
            return find_event_by_keyword(
                query=parameters["query"],
                date_range=tuple(parameters["date_range"]) if parameters.get("date_range") else None,
            )

        # ---------- NEW: holding-area ----------
        if action_type == "list_holding":
            return list_holding()

        if action_type == "create_holding":
            return create_holding_item(
                title=parameters["title"],
                notes=parameters.get("notes"),
                layer=parameters.get("layer", "work"),
            )

        if action_type == "move_to_holding":
            return move_event_to_holding(
                event_id=parameters["event_id"],
                reason=parameters.get("reason"),
            )

        if action_type == "promote_holding":
            return promote_holding_to_event(
                item_id=parameters["item_id"],
                start_time=parameters["start_time"],
                end_time=parameters["end_time"],
                location=parameters.get("location"),
                attendees=parameters.get("attendees"),
            )
        # --------------------------------------

        return {"status": "error", "message": f"Unknown action_type: {action_type}"}
    except KeyError as ke:
        return {"status": "error", "message": f"Missing parameter: {ke}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


def handle_actions(required_actions: List[Dict[str, Any]]) -> Dict[str, Any]:
    results = []
    for idx, action in enumerate(required_actions, start=1):
        a_type = action.get("type")
        params = action.get("parameters", {})
        res = handle_action(a_type, params)
        results.append({"index": idx, "type": a_type, "result": res})
    return {"status": "success", "results": results}


# ------------------------------
# Holding functions
# ------------------------------
def list_holding() -> Dict[str, Any]:
    if not USE_JSON_STORE:
        return {"status": "success", "items": []}
    store = _load_store()
    items = [ev for ev in store.values() if ev.get("status") == "holding"]
    items = [{
        "id": ev["id"],
        "title": ev.get("title",""),
        "notes": ev.get("description",""),
        "layer": ev.get("layer","work"),
        "created_at": ev.get("created_at"),
        "updated_at": ev.get("updated_at"),
    } for ev in items]
    return {"status": "success", "items": items}

def create_holding_item(title: str, notes: Optional[str] = None, layer: str = "work") -> Dict[str, Any]:
    if not USE_JSON_STORE:
        return {"status": "success", "id": _new_id(), "message": f"Holding item '{title}' captured."}
    hid = _new_id()
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    obj = {
        "id": hid,
        "status": "holding",
        "title": title,
        "description": notes or "",
        "layer": layer,
        "start": None, "end": None,             # keep shape consistent
        "created_at": now,
        "updated_at": now,
    }
    _store_event(obj)
    return {"status": "success", "id": hid, "message": f"Holding item '{title}' captured.", "item": obj}

def promote_holding_to_event(event_id: str, start_time: str, end_time: str,
                             location: Optional[str] = None, attendees: Optional[List[str]] = None) -> Dict[str, Any]:
    if not USE_JSON_STORE:
        return {"status": "success", "message": f"Held item promoted to event {start_time}–{end_time}."}
    store = _load_store()
    ev = store.get(event_id)
    if not ev or ev.get("status") != "holding":
        return {"status": "error", "message": f"Holding item '{event_id}' not found."}
    start_time = _ensure_seconds(start_time)
    end_time   = _ensure_seconds(end_time)
    ev.update({
        "status": None,                          # no longer holding
        "start": start_time,
        "end": end_time,
        "location": location if location is not None else ev.get("location",""),
        "attendees": attendees if attendees is not None else ev.get("attendees", []),
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _save_store(store)
    return {"status": "success", "event": ev}

def move_event_to_holding(event_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
    if not USE_JSON_STORE:
        return {"status": "success", "message": f"Event '{event_id}' moved to holding."}
    store = _load_store()
    ev = store.get(event_id)
    if not ev:
        return {"status": "error", "message": f"Event '{event_id}' not found."}
    ev.update({
        "status": "holding",
        "start": None, "end": None,              # unschedule it
        "description": (ev.get("description") or "") + (f" (Moved to holding: {reason})" if reason else ""),
        "updated_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _save_store(store)
    return {"status": "success", "message": f"Event '{event_id}' moved to holding."}

# ------------------------------
# Misc helpers
# ------------------------------

def event_duration_minutes(start_iso: str, end_iso: str) -> int:
    s = _parse_iso_dt(start_iso); e = _parse_iso_dt(end_iso)
    return int((e - s).total_seconds() // 60)

def pick_first_slot(free_slots: list, required_minutes: int) -> dict | None:
    for slot in free_slots:
        s = _parse_iso_dt(slot["start"]); e = _parse_iso_dt(slot["end"])
        if (e - s).total_seconds() // 60 >= required_minutes:
            return slot
    return None

__all__ = [
    "fetch_events", "get_free_slots", "create_event", "reschedule_event", "delete_event",
    "summarize_day", "block_time", "shift_events_batch", "find_event_by_keyword",
    "get_today", "resolve_relative_date", "resolve_relative_datetime",
    "get_week_dates", "resolve_week", "resolve_dates_for_phrase",
    "handle_action", "handle_actions", "event_duration_minutes", "pick_first_slot",
    "list_holding","move_event_to_holding","promote_holding_to_event","create_holding_item",
]
