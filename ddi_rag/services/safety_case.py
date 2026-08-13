"""
services/safety_case.py — SafetyCase workflow state machine.

State invariant (architecture doc, section 3.1): a CLOSED case is immutable.
Corrections must create appended amendments (new audit events / new records),
never rewrite a closed case's fields. A severe alert can be acknowledged or
overridden through review_status on Finding, but never deleted or hidden.

All state changes go through transition_case() so every change is paired
with an audit event — never set SafetyCase.state directly.
"""

from datetime import datetime, timezone
from typing import Dict, Optional, Set

from enums import SafetyCaseState
from models import ClinicalProfileSnapshot, Prescription, SafetyCase
from services.audit import record_audit_event


class InvalidTransitionError(Exception):
    pass


class CaseClosedError(Exception):
    """Raised when a mutation is attempted against a closed (immutable) case."""
    pass


# Allowed forward transitions. HELD_OR_CANCELLED and CLOSED are terminal
# except CLOSED can only be reached from READY_TO_DISPENSE or HELD_OR_CANCELLED.
ALLOWED_TRANSITIONS: Dict[SafetyCaseState, Set[SafetyCaseState]] = {
    SafetyCaseState.DRAFT: {
        SafetyCaseState.AWAITING_ANALYSIS,
    },
    SafetyCaseState.AWAITING_ANALYSIS: {
        SafetyCaseState.AWAITING_PHARMACIST_REVIEW,
    },
    SafetyCaseState.AWAITING_PHARMACIST_REVIEW: {
        SafetyCaseState.AWAITING_PRESCRIBER_RESPONSE,
        SafetyCaseState.READY_TO_DISPENSE,
        SafetyCaseState.HELD_OR_CANCELLED,
    },
    SafetyCaseState.AWAITING_PRESCRIBER_RESPONSE: {
        SafetyCaseState.ESCALATED,
        SafetyCaseState.READY_TO_DISPENSE,
        SafetyCaseState.HELD_OR_CANCELLED,
    },
    SafetyCaseState.ESCALATED: {
        SafetyCaseState.READY_TO_DISPENSE,
        SafetyCaseState.HELD_OR_CANCELLED,
    },
    SafetyCaseState.READY_TO_DISPENSE: {
        SafetyCaseState.CLOSED,
    },
    SafetyCaseState.HELD_OR_CANCELLED: {
        SafetyCaseState.CLOSED,
    },
    SafetyCaseState.CLOSED: set(),
}


def create_case(
    session,
    organization_id: str,
    prescription: Prescription,
    profile_snapshot: ClinicalProfileSnapshot,
    actor_user_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> SafetyCase:
    case = SafetyCase(
        organization_id=organization_id,
        prescription_id=prescription.id,
        profile_snapshot_id=profile_snapshot.id,
        state=SafetyCaseState.DRAFT,
    )
    session.add(case)
    session.flush()

    record_audit_event(
        session,
        action="safety_case.created",
        subject_type="safety_case",
        subject_id=case.id,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        after={"state": case.state.value},
    )
    return case


def transition_case(
    session,
    case: SafetyCase,
    new_state: SafetyCaseState,
    actor_user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> SafetyCase:
    """Move `case` to `new_state`, recording an audit event. Raises
    CaseClosedError if the case is already closed, or InvalidTransitionError
    if the transition isn't allowed from the current state."""
    if case.state == SafetyCaseState.CLOSED:
        raise CaseClosedError(
            f"SafetyCase {case.id} is closed and immutable; corrections must "
            "be recorded as new audit events, not a state change."
        )

    allowed = ALLOWED_TRANSITIONS.get(case.state, set())
    if new_state not in allowed:
        raise InvalidTransitionError(
            f"Cannot transition SafetyCase {case.id} from {case.state.value} "
            f"to {new_state.value}."
        )

    before_state = case.state.value
    case.state = new_state
    if owner_user_id is not None:
        case.owner_user_id = owner_user_id
    if new_state == SafetyCaseState.CLOSED:
        case.closed_at = datetime.now(timezone.utc)
    session.flush()

    record_audit_event(
        session,
        action="safety_case.state_changed",
        subject_type="safety_case",
        subject_id=case.id,
        organization_id=case.organization_id,
        actor_user_id=actor_user_id,
        request_id=request_id,
        before={"state": before_state},
        after={"state": new_state.value},
    )
    return case
