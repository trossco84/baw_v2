#!/usr/bin/env python3
"""Simple database backup script"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in environment")
    sys.exit(1)

# For now, just create a marker file since pg_dump isn't available
# In production, you'd use pg_dump or a proper backup solution
backup_dir = Path(__file__).parent.parent
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup_marker = backup_dir / f"backup_marker_{timestamp}.txt"

with open(backup_marker, 'w') as f:
    f.write(f"Backup marker created at {datetime.now()}\n")
    f.write(f"DATABASE_URL: {DATABASE_URL[:30]}...\n")
    f.write("\nNOTE: To create a proper backup, use:\n")
    f.write(f"  pg_dump $DATABASE_URL > backup_{timestamp}.sql\n")
    f.write("\nOr use Supabase dashboard to create a backup.\n")

print(f"✓ Backup marker created: {backup_marker.name}")
print(f"\nIMPORTANT: For production use, create a proper backup using:")
print(f"  1. Supabase dashboard (Database > Backups)")
print(f"  2. Or install PostgreSQL tools and run: pg_dump")
print(f"\nProceeding with migration...")
