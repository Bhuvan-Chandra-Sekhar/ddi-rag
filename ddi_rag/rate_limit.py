"""
rate_limit.py — Shared Flask-Limiter instance.

Defined here, not in app.py, so routes_public.py and routes_clinical.py can
import and decorate their own routes with it without an app.py <-> routes_*
circular import (app.py registers their blueprints, so they can't import
back from app.py).

app.py calls limiter.init_app(flask_app) once at startup; every other
module just imports `limiter` and uses it as a decorator.
"""

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import RATE_LIMIT_PER_DAY, RATE_LIMIT_PER_MINUTE

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[RATE_LIMIT_PER_DAY, RATE_LIMIT_PER_MINUTE],
)
