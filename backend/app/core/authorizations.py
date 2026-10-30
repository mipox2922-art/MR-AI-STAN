from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import ActivityLog, Setting

STANDING_AUTHORIZATION_KEY = "standing_authorizations.v1"
GMAIL_AUTO_SEND_KEY = "gmail_assistant.auto_send_enabled"

POLICY_DEFINITIONS = {
    "browser.fill_non_sensitive": {
        "id": "browser.fill_non_sensitive",
        "agent": "browser",
        "title": "Fill non-sensitive browser fields",
        "description": (
            "Allow Browser Hands to fill explicitly selected, non-sensitive form fields "
            "on domains already approved in the Chrome extension. It never submits forms."
        ),
        "default_enabled": False,
        "guardrails": [
            "Chrome domain allowlist remains mandatory.",
            "Passwords, OTP, PIN and payment-card fields are always blocked.",
            "Form submission, send, purchase, delete and publish remain approval-gated.",
        ],
    },
    "gmail.routine_reply": {
        "id": "gmail.routine_reply",
        "agent": "gmail",
        "title": "Send routine Gmail replies",
        "description": (
            "Standing permission for Gmail VIP to send only high-confidence routine replies. "
            "Gmail must be connected and VIP enabled."
        ),
        "default_enabled": False,
        "guardrails": [
            "Requires the Gmail VIP AUTO-REPLY setting.",
            "AI confidence must be at least 0.85.",
            "Financial, legal, medical, credential, urgent and commitment-related content stays draft-only.",
            "No-reply senders are never auto-replied to.",
        ],
    },
}

BLOCKED_ACTIONS = [
    {"id": "jobs.submit", "reason": "No verified employer submission hand is implemented."},
    {"id": "gmail.send_sensitive", "reason": "Sensitive email actions always require owner review."},
    {"id": "browser.submit_or_purchase", "reason": "Form submission, payment and purchase remain approval-gated."},
    {"id": "device.high_risk", "reason": "Device flashing, reboot and destructive operations require per-action approval."},
]


def _setting(db: Session, user_id: int, key: str) -> Setting | None:
    return (
        db.query(Setting)
        .filter(Setting.user_id == user_id, Setting.key == key)
        .order_by(Setting.id.desc())
        .first()
    )


def _load_state(db: Session, user_id: int) -> dict:
    row = _setting(db, user_id, STANDING_AUTHORIZATION_KEY)
    if not row or not row.value:
        return {"version": 1, "rules": {}}
    try:
        value = json.loads(row.value)
    except (TypeError, ValueError):
        return {"version": 1, "rules": {}}
    if not isinstance(value, dict) or not isinstance(value.get("rules"), dict):
        return {"version": 1, "rules": {}}
    return {"version": 1, "rules": value["rules"]}


def authorization_enabled(db: Session, user_id: int, policy_id: str) -> bool:
    definition = POLICY_DEFINITIONS.get(policy_id)
    if definition is None:
        return False
    state = _load_state(db, user_id)
    entry = state["rules"].get(policy_id)
    if isinstance(entry, dict) and isinstance(entry.get("enabled"), bool):
        return entry["enabled"]

    # Preserve an explicit pre-v1 Gmail AUTO-REPLY opt-in during migration.
    if policy_id == "gmail.routine_reply":
        legacy = _setting(db, user_id, GMAIL_AUTO_SEND_KEY)
        return bool(legacy and str(legacy.value or "").strip().lower() in {"1", "true", "yes", "on"})
    return bool(definition["default_enabled"])


def list_standing_authorizations(db: Session, user_id: int) -> dict:
    state = _load_state(db, user_id)
    rules = []
    for policy_id, definition in POLICY_DEFINITIONS.items():
        entry = state["rules"].get(policy_id)
        explicit = isinstance(entry, dict) and isinstance(entry.get("enabled"), bool)
        rules.append({
            **definition,
            "enabled": authorization_enabled(db, user_id, policy_id),
            "source": "owner_rule" if explicit else "default_or_existing_opt_in",
            "updated_at": entry.get("updated_at") if explicit else None,
        })
    return {
        "version": 1,
        "rules": rules,
        "blocked_actions": BLOCKED_ACTIONS,
        "note": (
            "Rules are owner-scoped. A rule grants only its named capability; it never "
            "overrides connector availability, extension domain allowlists, or hard safety checks."
        ),
    }


def set_standing_authorization(
    db: Session,
    user_id: int,
    policy_id: str,
    enabled: bool,
) -> dict:
    if policy_id not in POLICY_DEFINITIONS:
        raise ValueError("Unknown standing authorization policy.")
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean.")

    state = _load_state(db, user_id)
    state["rules"][policy_id] = {
        "enabled": enabled,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    row = _setting(db, user_id, STANDING_AUTHORIZATION_KEY)
    encoded = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
    if row is None:
        db.add(Setting(user_id=user_id, key=STANDING_AUTHORIZATION_KEY, value=encoded))
    else:
        row.value = encoded

    # Keep Gmail's existing AUTO-REPLY switch and the central standing rule in sync.
    if policy_id == "gmail.routine_reply":
        gmail_row = _setting(db, user_id, GMAIL_AUTO_SEND_KEY)
        if gmail_row is None:
            db.add(Setting(user_id=user_id, key=GMAIL_AUTO_SEND_KEY, value="true" if enabled else "false"))
        else:
            gmail_row.value = "true" if enabled else "false"

    db.add(ActivityLog(
        user_id=user_id,
        action="STANDING_AUTHORIZATION_CHANGED",
        details=f"policy={policy_id}; enabled={str(enabled).lower()}; actor=owner",
    ))
    db.commit()
    return list_standing_authorizations(db, user_id)
