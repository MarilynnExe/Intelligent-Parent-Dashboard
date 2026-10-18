"""
Test configuration.

Points the app at a throwaway SQLite file before any app module is imported,
so importing app.main (which creates tables on startup) never touches the
real MySQL database configured in backend/.env.
"""

import os
import sys
import tempfile
from pathlib import Path

_test_db = Path(tempfile.mkdtemp(prefix="ipd-tests-")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_test_db}"  # load_dotenv does not override this

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
