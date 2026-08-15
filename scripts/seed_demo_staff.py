"""
scripts/seed_demo_staff.py — Create demo pharmacist/prescriber accounts for
manually exercising the clinical console (static/clinical/index.html).

Self-registration (api/auth/register) is intentionally restricted to the
patient role (see auth.py's docstring) — pharmacist/prescriber accounts are
"provisioned by an organization administrator", per the architecture doc.
This script is that provisioning step, run directly against the database,
not exposed over HTTP.

Idempotent: safe to re-run — existing accounts (matched by email) are left
untouched, not duplicated.

Run:
    python scripts/seed_demo_staff.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))

from auth import hash_password
from database import get_session, init_db
from enums import UserRole
from models import Organization, User

ORG_NAME = "Demo General Hospital"

STAFF = [
    {"email": "pharmacist@demo.local", "password": "DemoPharm123!", "full_name": "Pat Pharmacist", "role": UserRole.PHARMACIST},
    {"email": "prescriber@demo.local", "password": "DemoPrescriber123!", "full_name": "Dr. Prescriber", "role": UserRole.PRESCRIBER},
]


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

        for spec in STAFF:
            existing = session.query(User).filter_by(email=spec["email"]).first()
            if existing:
                print(f"  already exists: {spec['email']} ({existing.role.value})")
                continue
            user = User(
                organization_id=org.id, email=spec["email"],
                password_hash=hash_password(spec["password"]),
                full_name=spec["full_name"], role=spec["role"],
            )
            session.add(user)
            session.flush()
            print(f"  created: {spec['email']} / {spec['password']}  ({spec['role'].value})")

    print("\nLog into /clinical with either account above.")


if __name__ == "__main__":
    main()
