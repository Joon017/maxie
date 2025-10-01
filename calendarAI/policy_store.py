# policy_store.py
from __future__ import annotations
import json, os, uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

POLICY_STORE_PATH = os.environ.get("POLICY_STORE_PATH", "policies.json")

def _now() -> str:
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

def _load() -> Dict[str, Any]:
    if not os.path.exists(POLICY_STORE_PATH):
        return {}
    with open(POLICY_STORE_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f) or {}
        except Exception:
            return {}

def _save(obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(POLICY_STORE_PATH) or ".", exist_ok=True)
    with open(POLICY_STORE_PATH, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)

def list_policies() -> List[Dict[str, Any]]:
    return list(_load().values())

def get_policy(pid: str) -> Optional[Dict[str, Any]]:
    return _load().get(pid)

def create_policy(policy: Dict[str, Any]) -> Dict[str, Any]:
    store = _load()
    pid = policy.get("id") or str(uuid.uuid4())
    policy["id"] = pid
    policy["version"] = (policy.get("version") or 0) + 1
    ts = _now()
    policy["created_at"] = policy.get("created_at") or ts
    policy["updated_at"] = ts
    store[pid] = policy
    _save(store)
    return policy

def update_policy(pid: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    store = _load()
    if pid not in store:
        return None
    cur = store[pid]
    cur.update(patch)
    cur["version"] = (cur.get("version") or 0) + 1
    cur["updated_at"] = _now()
    store[pid] = cur
    _save(store)
    return cur

def delete_policy(pid: str) -> bool:
    store = _load()
    if pid in store:
        del store[pid]
        _save(store)
        return True
    return False

def toggle_policy(pid: str, enabled: bool) -> Optional[Dict[str, Any]]:
    return update_policy(pid, {"status": "enabled" if enabled else "disabled"})
