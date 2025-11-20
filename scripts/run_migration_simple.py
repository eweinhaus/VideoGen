#!/usr/bin/env python3
"""
Simple script to run the migration SQL directly.
This script reads the SQL from the migration file and provides instructions.
"""

import sys
from pathlib import Path

# Read the migration SQL
migration_file = Path(__file__).parent / "supabase" / "migrations" / "20250120000000_add_video_model_aspect_ratio_template.sql"

if not migration_file.exists():
    print(f"❌ Migration file not found: {migration_file}")
    sys.exit(1)

print("=" * 80)
print("MIGRATION SQL TO RUN")
print("=" * 80)
print()
print("Copy and paste the following SQL into your Supabase SQL Editor:")
print()
print("-" * 80)

with open(migration_file, 'r') as f:
    print(f.read())

print("-" * 80)
print()
print("INSTRUCTIONS:")
print("1. Go to your Supabase project dashboard")
print("2. Navigate to: SQL Editor (in the left sidebar)")
print("3. Click 'New query'")
print("4. Copy and paste the SQL above")
print("5. Click 'Run' or press Cmd/Ctrl + Enter")
print()
print("Alternatively, if you have Supabase CLI installed:")
print("  supabase db push")
print()
print("=" * 80)

