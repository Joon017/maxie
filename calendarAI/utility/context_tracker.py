# context_tracker.py

from __future__ import annotations
from typing import Any, Dict, List, Optional

class ContextTracker:
    def __init__(self):
        self.contexts: Dict[str, Dict[str, Any]] = {}
        self.pending_plans: Dict[str, Dict[str, Any]] = {}   # plans awaiting confirmation

    # ---------- session bootstrap ----------
    def init_session(self, session_id: str) -> None:
        if session_id not in self.contexts:
            self.contexts[session_id] = {
                "summary": [],      # rotating bullets for quick LLM context
                "history": [],      # full chat/event log if you want it
                "working_set": {    # structured, machine-usable state
                    "current_event_ids": [],
                    "last_date": None,
                    "last_date_range": None,   # tuple or list: ["YYYY-MM-DD","YYYY-MM-DD"]
                    "candidate_slots": [],     # [{"start": "...", "end": "..."}]
                    "last_intent": None,       # e.g., "block" | "reschedule" | "advice"
                    "notes": "",               # optional free text
                },
            }

    # ---------- user & ai logging ----------
    def update_user(self, session_id: str, message: str) -> None:
        self.init_session(session_id)
        self._add_summary(session_id, f"- User: {message}")
        self._add_history(session_id, role="user", message=message)

    def update_ai(self, session_id: str, message: str, metadata: Optional[dict] = None) -> None:
        self.init_session(session_id)
        bullet = f"responded: '{(message or '').strip()[:100]}'"
        self._add_summary(session_id, f"- AI: {bullet}")
        self._add_history(session_id, role="ai", message=(message or "").strip(), metadata=metadata or {})

    def _add_summary(self, session_id: str, entry: str) -> None:
        ctx = self.contexts[session_id]
        ctx["summary"].append(entry)
        ctx["summary"] = ctx["summary"][-10:]  # keep last 10 bullets

    def _add_history(self, session_id: str, role: str, message: str, metadata: Optional[dict] = None) -> None:
        ctx = self.contexts[session_id]
        ctx["history"].append({"role": role, "message": message, "metadata": metadata or {}})

    # ---------- retrieval ----------
    def get_summary_string(self, session_id: str) -> str:
        self.init_session(session_id)
        return "\n".join(self.contexts[session_id]["summary"])

    def get_log(self, session_id: str) -> List[dict]:
        self.init_session(session_id)
        return self.contexts[session_id]["history"]

    # ---------- focus set (task state) ----------
    def get_focus_set(self, session_id: str) -> dict:
        self.init_session(session_id)
        ctx = self.contexts[session_id]
        if "focus_set" not in ctx:
            ctx["focus_set"] = {}   # ensure it's always there
        return ctx["focus_set"]

    def set_focus_set(self, session_id: str, updates: dict):
        self.init_session(session_id)
        ctx = self.contexts[session_id]
        if "focus_set" not in ctx:
            ctx["focus_set"] = {}
        ctx["focus_set"].update(updates)

    def clear_working_set(self, session_id: str, keys: Optional[List[str]] = None) -> None:
        """
        Clear specific keys or wipe the entire working_set if keys is None/empty.
        """
        self.init_session(session_id)
        ws = self.contexts[session_id]["working_set"]
        if not keys:
            ws.clear()
            # re-seed defaults so callers don’t crash
            ws.update({
                "current_event_ids": [],
                "last_date": None,
                "last_date_range": None,
                "candidate_slots": [],
                "last_intent": None,
                "notes": "",
            })
            return
        for k in keys:
            ws.pop(k, None)

    # Handy: snapshot both summary + working set for L2/L3/L5 prompts
    def get_context_bundle(self, session_id: str) -> dict:
        self.init_session(session_id)
        ctx = self.contexts[session_id]
        return {
            "summary_string": "\n".join(ctx["summary"]),
            "working_set": dict(ctx["working_set"]),  # shallow copy
        }

    # ---------- pending plan handling ----------
    def set_pending_plan(self, session_id: str, plan: dict) -> None:
        self.pending_plans[session_id] = plan
        self._add_history(session_id, role="ai", message="[Plan awaiting confirmation]", metadata={"plan": plan})

    def get_pending_plan(self, session_id: str) -> Optional[dict]:
        return self.pending_plans.get(session_id)

    def clear_pending_plan(self, session_id: str) -> None:
        if session_id in self.pending_plans:
            del self.pending_plans[session_id]

    # ---------- reset ----------
    def reset(self, session_id: str) -> None:
        if session_id in self.contexts:
            del self.contexts[session_id]
        if session_id in self.pending_plans:
            del self.pending_plans[session_id]
        self.init_session(session_id)
