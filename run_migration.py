#!/usr/bin/env python3
"""
Run database migrations for CCTV Tool
"""
import os
import sys
import pyodbc
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

def get_db_connection():
    """Create database connection"""
    conn_str = (
        f"DRIVER={{{os.getenv('DB_DRIVER', 'FreeTDS')}}};"
        f"SERVER={os.getenv('DB_SERVER', 'SG-8-Test-SQL')};"
        f"DATABASE={os.getenv('DB_DATABASE', 'FDOT_CCTV_System')};"
        f"UID={os.getenv('DB_USERNAME', 'RTMCSNAP')};"
        f"PWD={os.getenv('DB_PASSWORD', '')};"
        f"PORT=1433;"
        f"TDS_Version=7.4;"
        f"Connection Timeout={os.getenv('DB_TIMEOUT', '30')};"
    )
    return pyodbc.connect(conn_str)

def run_migration(migration_file: Path):
    """Run a single migration file"""
    print(f"\n{'='*60}")
    print(f"Running migration: {migration_file.name}")
    print(f"{'='*60}")

    try:
        # Read migration SQL
        with open(migration_file, 'r') as f:
            sql_script = f.read()

        # Connect to database
        conn = get_db_connection()
        conn.autocommit = True  # Enable autocommit for DDL statements
        cursor = conn.cursor()

        # Split by GO statements and execute each batch
        batches = [batch.strip() for batch in sql_script.split('GO') if batch.strip()]

        for i, batch in enumerate(batches, 1):
            print(f"\nExecuting batch {i}/{len(batches)}...")
            try:
                cursor.execute(batch)
                # Fetch messages (PRINT statements)
                while cursor.nextset():
                    pass
                print(f"✓ Batch {i} completed successfully")
            except Exception as e:
                print(f"✗ Error in batch {i}: {e}")
                raise

        cursor.close()
        conn.close()

        print(f"\n✓ Migration {migration_file.name} completed successfully!")
        return True

    except Exception as e:
        print(f"\n✗ Migration failed: {e}")
        return False

def main():
    """Run all pending migrations"""
    migrations_dir = Path(__file__).parent / 'migrations'

    if not migrations_dir.exists():
        print(f"✗ Migrations directory not found: {migrations_dir}")
        sys.exit(1)

    # Get all .sql files in migrations directory
    migration_files = sorted(migrations_dir.glob('*.sql'))

    if not migration_files:
        print("No migrations found")
        sys.exit(0)

    print(f"\nFound {len(migration_files)} migration(s)")

    # Run each migration
    success_count = 0
    for migration_file in migration_files:
        if run_migration(migration_file):
            success_count += 1
        else:
            print(f"\n✗ Stopping at failed migration: {migration_file.name}")
            sys.exit(1)

    print(f"\n{'='*60}")
    print(f"✓ All migrations completed successfully!")
    print(f"  Total: {success_count}/{len(migration_files)}")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
