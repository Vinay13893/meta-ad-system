"""
One-shot ops script — ALREADY EXECUTED (June 2026).
Raises the 'creatives' storage bucket file-size limit to 500 MB.
NOT idempotent tooling; committed for audit trail only. Do not re-run.
"""
from __future__ import annotations
import os, sys
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

# 500 MB in bytes
LIMIT = 500 * 1024 * 1024

try:
    sb.storage.update_bucket("creatives", options={"file_size_limit": LIMIT})
    print(f"Bucket 'creatives' file-size limit raised to 500 MB.")
except Exception as e:
    print(f"Could not update bucket: {e}")
    sys.exit(1)
