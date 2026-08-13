import os
import sys
import tempfile
from pathlib import Path

# Test-only secret so config.py/auth.py validation passes at import time.
os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-key-32-characters-min!!")

# A real (temp) file, not sqlite:///:memory: — an in-memory sqlite DB is
# private to a single connection, so anything using the app's pooled
# engine (multiple connections) would see a fresh empty DB per connection.
_test_db_path = Path(tempfile.gettempdir()) / "ddi_rag_test.db"
_test_db_path.unlink(missing_ok=True)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_test_db_path.as_posix()}")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "ddi_rag"))
