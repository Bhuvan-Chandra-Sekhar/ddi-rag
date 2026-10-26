"""
auth.py — JWT issuance + bcrypt password hashing.

Security notes:
    - Passwords are hashed with bcrypt (cost factor 12) and never stored,
      logged, or returned in plaintext.
    - JWT_SECRET_KEY must come from the environment; the app refuses to start
      if it is missing or shorter than 32 characters, instead of silently
      falling back to a weak or hardcoded default.
    - Access tokens are signed HS256, expire after JWT_ACCESS_TOKEN_MINS
      (24h default), and carry only the user's id as the `sub` claim.
"""

import re

import bcrypt
from flask_jwt_extended import JWTManager, create_access_token

from config import BCRYPT_ROUNDS, JWT_ACCESS_TOKEN_MINS, JWT_SECRET_KEY
from database import get_session
from enums import UserRole
from models import Organization, Patient, User

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

jwt_manager = JWTManager()


def configure_jwt(flask_app) -> None:
    """Wire flask-jwt-extended into the app with a validated secret key."""
    if not JWT_SECRET_KEY or len(JWT_SECRET_KEY) < 32:
        raise RuntimeError(
            "JWT_SECRET_KEY is missing or too short (must be >= 32 characters). "
            "Set a long random value via the JWT_SECRET_KEY environment "
            "variable — never hardcode it in source."
        )
    flask_app.config["JWT_SECRET_KEY"] = JWT_SECRET_KEY
    flask_app.config["JWT_ACCESS_TOKEN_EXPIRES"] = JWT_ACCESS_TOKEN_MINS * 60
    flask_app.config["JWT_ALGORITHM"] = "HS256"
    jwt_manager.init_app(flask_app)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(
        password.encode("utf-8"), bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    ).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def register_user(
    email: str,
    password: str,
    organization_id: str,
    full_name: str = "",
    first_name: str = "",
    last_name: str = "",
    role: UserRole = UserRole.PATIENT,
) -> dict:
    """
    Self-registration is restricted to the PATIENT role — pharmacist,
    prescriber, and administrative accounts are provisioned by an
    organization administrator, not created through this open endpoint.

    A PATIENT registration also creates a linked Patient record (clinical
    demographic row) — first_name/last_name are required for it, since
    Patient.first_name/last_name are non-nullable.
    """
    email = email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValueError("Invalid email address.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if role != UserRole.PATIENT:
        raise ValueError("Self-registration is only permitted for the patient role.")
    if not first_name.strip() or not last_name.strip():
        raise ValueError("first_name and last_name are required.")

    with get_session() as session:
        if not session.query(Organization).filter_by(id=organization_id).first():
            raise ValueError("Unknown organization_id.")
        if session.query(User).filter_by(email=email).first():
            raise ValueError("An account with this email already exists.")
        user = User(
            organization_id=organization_id,
            email=email,
            password_hash=hash_password(password),
            full_name=full_name.strip(),
            role=role,
        )
        session.add(user)
        session.flush()

        patient = Patient(
            organization_id=organization_id,
            user_id=user.id,
            first_name=first_name.strip(),
            last_name=last_name.strip(),
        )
        session.add(patient)
        session.flush()

        return {
            "id": user.id, "email": user.email, "full_name": user.full_name,
            "role": user.role.value, "patient_id": patient.id,
        }


def authenticate_user(email: str, password: str) -> dict:
    email = email.strip().lower()
    with get_session() as session:
        user = session.query(User).filter_by(email=email).first()
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("Invalid email or password.")
        token = create_access_token(identity=user.id)
        patient = session.query(Patient).filter_by(user_id=user.id).first()
        return {
            "access_token": token,
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.value,
                "organization_id": user.organization_id,
                "patient_id": patient.id if patient else None,
            },
        }
