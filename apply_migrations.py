# Applies all SQL files in /migrations in order against the Supabase dev DB.
# Run once when setting up a new Supabase project.
# Safe to re-run — all statements use IF NOT EXISTS / ON CONFLICT DO NOTHING.
#
# This is the ONE file in the project that uses psycopg2 + DATABASE_URL.
# Reason: supabase-py goes through PostgREST and cannot execute raw DDL.
# Everything else in the pipeline uses SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY.
#
# Simpler alternative: paste each migrations/*.sql file into
# Supabase Dashboard → SQL Editor and run it there.
#
# Requires: pip install psycopg2-binary python-dotenv

from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    print("Missing DATABASE_URL in .env")
    print("Get it from: Supabase dashboard → Settings → Database → URI")
    sys.exit(1)

migrations_dir = Path(__file__).parent / "migrations"
sql_files = sorted(migrations_dir.glob("*.sql"))

if not sql_files:
    print("No migration files found in /migrations")
    sys.exit(1)

print(f"Connecting to database...")
conn = psycopg2.connect(DATABASE_URL)
conn.autocommit = True
cur = conn.cursor()

for sql_file in sql_files:
    print(f"Applying {sql_file.name}...", end=" ")
    sql = sql_file.read_text()
    cur.execute(sql)
    print("done")

cur.close()
conn.close()
print("\nAll migrations applied successfully.")
print("\nNext: run seed_connections.py to insert your API credentials.")
