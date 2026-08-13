"""
services/audit.py — Append-only audit event recording.

Every clinically or security relevant action must go through
record_audit_event() rather than writing AuditEvent rows directly, so the
shape stays consistent and no caller accidentally updates or deletes one.
"""

from typing import Optional

from models import AuditEvent


def record_audit_event(
    session,
    action: str,
    subject_type: str,
    subject_id: str,
    organization_id: Optional[str] = None,
    actor_user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    before: Optional[dict] = None,
    after: Optional[dict] = None,
) -> AuditEvent:
    event = AuditEvent(
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        request_id=request_id,
        before_state=before,
        after_state=after,
    )
    session.add(event)
    session.flush()
    return event
