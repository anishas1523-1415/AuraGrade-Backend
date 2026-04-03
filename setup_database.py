#!/usr/bin/env python3
"""
AuraGrade Database Setup Wizard
Helps user deploy schema to Supabase via their credentials.
"""

import os
import sys
import subprocess
from pathlib import Path

def main():
    print("=" * 70)
    print("AuraGrade Database Setup Wizard")
    print("=" * 70)
    print()
    
    # Detect backend directory
    backend_dir = Path(__file__).parent / "backend"
    schema_file = backend_dir / "schema.sql"
    rls_file = backend_dir / "rls_gap_remediation.sql"
    
    print("This wizard will help you set up the Supabase database.")
    print()
    print("OPTION 1: Manual Setup via Supabase Web UI (Recommended)")
    print("-" * 70)
    print()
    print("1. Open: https://app.supabase.com")
    print("2. Select your AuraGrade project")
    print("3. Click 'SQL Editor' → 'New Query'")
    print("4. Copy & paste the following into the SQL Editor:")
    print()
    print(f"   File: {schema_file}")
    print()
    print("5. Click 'Execute' - wait for success message")
    print("6. Repeat steps 3-5 with:")
    print()
    print(f"   File: {rls_file}")
    print()
    print()
    
    print("OPTION 2: Automatic Setup via psql (Expert Users)")
    print("-" * 70)
    print()
    
    supabase_host = os.getenv("SUPABASE_HOST", "")
    if not supabase_host:
        print("ERROR: SUPABASE_HOST environment variable not set.")
        print()
        print("To use psql automation, set:")
        print("  export SUPABASE_HOST=your-project.supabase.co")
        print("  export SUPABASE_PASSWORD=your-postgres-password")
        print()
        print("Then run:")
        print("  python setup_database.py --auto")
        sys.exit(1)
    
    if len(sys.argv) > 1 and sys.argv[1] == "--auto":
        password = os.getenv("SUPABASE_PASSWORD", "")
        if not password:
            print("ERROR: SUPABASE_PASSWORD not set")
            sys.exit(1)
        
        print(f"Connecting to {supabase_host}...")
        
        # Run schema.sql
        print()
        print("Executing schema.sql...")
        cmd = f"""PGPASSWORD="{password}" psql -h {supabase_host} -U postgres -d postgres -f {schema_file}"""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("ERROR:", result.stderr)
            sys.exit(1)
        print("✓ Schema created successfully")
        
        # Run RLS gaps
        print()
        print("Executing rls_gap_remediation.sql...")
        cmd = f"""PGPASSWORD="{password}" psql -h {supabase_host} -U postgres -d postgres -f {rls_file}"""
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode != 0:
            print("ERROR:", result.stderr)
            sys.exit(1)
        print("✓ RLS policies applied successfully")
        
        print()
        print("=" * 70)
        print("✓ Database setup complete! You can now:")
        print("  1. Refresh http://localhost:3000")
        print("  2. Log in with Supabase credentials")
        print("  3. Create an assessment and start grading")
        print("=" * 70)
    else:
        print("Run 'python scripts/setup_database.py --auto' after setting")
        print("SUPABASE_HOST and SUPABASE_PASSWORD environment variables")
        print()
        print("For manual setup (recommended), see OPTION 1 above.")
        print()

if __name__ == "__main__":
    main()
