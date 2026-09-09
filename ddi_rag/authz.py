"""
authz.py — Shared authorization: tenant isolation + role enforcement.

Before this module existed, app.py and routes_clinical.py each carried
their own near-identical _authorized_case_or_error()/_authorized_case()
helper, and BOTH checked only `case.organization_id == user.organization_id`
— organization membership. Neither checked `user.role` anywhere, and no
route in the app did either (grepped for it). That meant any authenticated
account in an organization — including a `patient`-role account, which is
the one role self-registration actually issues — could call
pharmacist/prescriber-only actions (assess findings, dispense, resolve
escalations, respond to a prescriber intervention) as long as it belonged
to the same org as the case. Not a hypothetical gap: verified by grepping
every route handler for a role check and finding none.

Both call sites now use authorized_case() from here instead of their own
copy, passing the roles that action actually requires. allowed_roles=None
preserves the old "any staff member in this org" behavior for read-only/
low-risk routes where a role split doesn't add real protection.
"""

from typing import Optional, Sequence, Tuple

from enums import UserRole
from models import SafetyCase, User

ErrorResponse = Tuple[dict, int]


def get_caller(session, caller_user_id: str) -> Tuple[Optional[User], Optional[ErrorResponse]]:
    """Resolve the calling User, or an error tuple if the JWT identity
    doesn't correspond to a real (still-existing) account."""
    user = session.get(User, caller_user_id)
    if not user:
        return None, ({"error": "unknown user"}, 401)
    return user, None


def require_role(user: User, allowed_roles: Sequence[UserRole]) -> Optional[ErrorResponse]:
    """None if user.role is permitted, else a (body, 403) error tuple for
    the caller to return directly."""
    if user.role not in allowed_roles:
        return (
            {"error": "forbidden — this action requires one of: "
                      + ", ".join(r.value for r in allowed_roles)},
            403,
        )
    return None


def authorized_case(
    session,
    case_id: str,
    caller_user_id: str,
    allowed_roles: Optional[Sequence[UserRole]] = None,
) -> Tuple[Optional[SafetyCase], Optional[ErrorResponse]]:
    """
    Return (case, None) if case_id exists, belongs to the caller's
    organization, and — when allowed_roles is given — the caller's role is
    one of them. Otherwise (None, (body, status)) for the caller to return
    as-is.

    Existence is checked before role so a caller in another organization
    always gets 404 (not 403) regardless of their own role — tenant
    boundaries stay non-leaking, same contract as before this module
    existed. A same-org caller with the wrong role gets 403, since case
    existence is already legitimately known to them at that point.
    """
    user, error = get_caller(session, caller_user_id)
    if error:
        return None, error

    case = session.get(SafetyCase, case_id)
    if not case:
        return None, ({"error": "not found"}, 404)
    if case.organization_id != user.organization_id:
        return None, ({"error": "not found"}, 404)  # 404, not 403 — don't leak existence across tenants

    if allowed_roles is not None:
        role_error = require_role(user, allowed_roles)
        if role_error:
            return None, role_error

    return case, None
