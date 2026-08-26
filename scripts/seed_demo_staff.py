"""
scripts/seed_demo_staff.py — Create/reset demo pharmacist/prescriber
accounts for manually exercising the clinical console
(static/clinical/index.html).

Self-registration (api/auth/register) is intentionally restricted to the
patient role (see auth.py's docstring) — pharmacist/prescriber accounts
are "provisioned by an organization administrator", per the architecture
doc. This script is that provisioning step, run directly against the
database, not exposed over HTTP.

SECURITY NOTE — this script used to hardcode real, working passwords
("DemoPharm123!" / "DemoPrescriber123!") directly in this file. That's
exactly why it needed fixing: this file is tracked in a *public* GitHub
repo, so hardcoding a real password here means committing a live
credential in plaintext, same class of mistake as committing a secret in
docs/SESSION_HANDOFF.md (which a separate session already had to remediate
— rotating both accounts' passwords and untracking that file). Generating
a fresh random password every run and only ever printing it to the
console (never writing it to a file) means there is no live secret in
this file to leak in the first place.

Re-running this script now RESETS both accounts' passwords to a new
random value (previously it silently skipped existing accounts) — that's
intentional: there's no way to "peek" at an existing password (it's only
ever stored hashed), so a reset is the only way to recover access if
you've lost the last-printed value.

Run:
    python scripts/seed_demo_staff.py
"""

import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

from auth import hash_password
from database import get_session, init_db
from enums import UserRole
from models import Organization, User

ORG_NAME = "Demo General Hospital"

STAFF = [
    {"email": "pharmacist@demo.local", "full_name": "Pat Pharmacist", "role": UserRole.PHARMACIST},
    {"email": "prescriber@demo.local", "full_name": "Dr. Prescriber", "role": UserRole.PRESCRIBER},
]


def _generate_password() -> str:
    # url-safe, no ambiguous characters to transcribe, comfortably above
    # any reasonable minimum-length policy.
    return secrets.token_urlsafe(12)


def main() -> None:
    init_db()
    with get_session() as session:
        org = session.query(Organization).filter_by(name=ORG_NAME).first()
        if not org:
            org = Organization(name=ORG_NAME)
            session.add(org)
            session.flush()
            print(f"Created organization '{ORG_NAME}' ({org.id})")
        else:
            print(f"Using existing organization '{ORG_NAME}' ({org.id})")

        print()
        for spec in STAFF:
            password = _generate_password()
            existing = session.query(User).filter_by(email=spec["email"]).first()
            if existing:
                existing.password_hash = hash_password(password)
                session.flush()
                print(f"  RESET: {spec['email']} / {password}  ({existing.role.value})")
            else:
                user = User(
                    organization_id=org.id, email=spec["email"],
                    password_hash=hash_password(password),
                    full_name=spec["full_name"], role=spec["role"],
                )
                session.add(user)
                session.flush()
                print(f"  CREATED: {spec['email']} / {password}  ({spec['role'].value})")

    print("\nLog into /clinical with either account above.")
    print("These values are only ever printed here — write them down now, they aren't stored anywhere retrievable.")


if __name__ == "__main__":
    main()
