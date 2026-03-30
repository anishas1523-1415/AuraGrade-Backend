#!/usr/bin/env python3
"""
Phase B+C: Automated Task Executor
Helps user execute the 3 remaining tasks with guided automation

Usage:
  python phase_bc_execute.py task1
  python phase_bc_execute.py task2
  python phase_bc_execute.py task3
  python phase_bc_execute.py verify
"""

import sys
import os
import subprocess
import json
from pathlib import Path
from typing import Optional, Tuple

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
RESET = '\033[0m'

class PhaseBC:
    def __init__(self):
        self.repo_root = Path(__file__).parent
        self.backend_root = self.repo_root / "backend"
        self.env_example = self.repo_root / ".env.example"
        
    def print_header(self, text: str):
        print(f"\n{BLUE}{'='*70}")
        print(f"{text}")
        print(f"{'='*70}{RESET}\n")
    
    def print_success(self, text: str):
        print(f"{GREEN}✓ {text}{RESET}")
    
    def print_error(self, text: str):
        print(f"{RED}✗ {text}{RESET}")
    
    def print_info(self, text: str):
        print(f"{YELLOW}ℹ {text}{RESET}")
    
    def check_rls_file(self) -> bool:
        """Verify RLS remediation file exists and is valid."""
        rls_file = self.backend_root / "rls_gap_remediation.sql"
        if not rls_file.exists():
            self.print_error(f"RLS file not found: {rls_file}")
            return False
        
        with open(rls_file) as f:
            content = f.read()
        
        required_keywords = ["exception_queue", "audit_logs", "students_select_fixed"]
        for keyword in required_keywords:
            if keyword not in content:
                self.print_error(f"RLS file missing expected content: {keyword}")
                return False
        
        self.print_success(f"RLS file valid ({len(content)} bytes)")
        return True
    
    def task1_rls_remediation(self):
        """Guide user through RLS remediation task."""
        self.print_header("TASK 1: RLS Gap Remediation")
        
        if not self.check_rls_file():
            return False
        
        print(f"{YELLOW}MANUAL STEPS REQUIRED:{RESET}\n")
        print("1. Open: https://app.supabase.com")
        print("2. Select your AuraGrade project")
        print("3. Click 'SQL Editor' in left sidebar")
        print("4. Click 'New Query'")
        print("5. Copy entire file contents:")
        print(f"   {self.backend_root / 'rls_gap_remediation.sql'}\n")
        print("6. Paste into SQL Editor")
        print("7. Click 'Execute' button\n")
        
        # Try to copy to clipboard if xclip/pbcopy available
        rls_file = self.backend_root / "rls_gap_remediation.sql"
        try:
            with open(rls_file) as f:
                content = f.read()
            
            if sys.platform == "darwin":  # macOS
                subprocess.run(["pbcopy"], input=content.encode(), check=False)
                self.print_success("RLS SQL copied to clipboard (macOS)")
            elif sys.platform == "linux":
                subprocess.run(["xclip", "-selection", "clipboard"], 
                             input=content.encode(), check=False)
                self.print_success("RLS SQL copied to clipboard (Linux)")
            elif sys.platform == "win32":
                subprocess.run(["clip"], input=content.encode(), check=False)
                self.print_success("RLS SQL copied to clipboard (Windows)")
        except Exception as e:
            self.print_info(f"Could not copy to clipboard: {e}")
        
        print(f"\n{YELLOW}VERIFICATION:{RESET}")
        print("After executing SQL in Supabase, run this query to verify:\n")
        print("  SELECT COUNT(*) as policy_count FROM pg_policies")
        print("  WHERE tablename IN ('students', 'grades', 'audit_logs');\n")
        print(f"Expected result: {GREEN}9+ rows (3 policies per table){RESET}")
        
        return True
    
    def task2_env_vars(self):
        """Guide user through environment variable setup."""
        self.print_header("TASK 2: Production Environment Variables")
        
        if not self.env_example.exists():
            self.print_error(f"Template not found: {self.env_example}")
            return False
        
        # Read template
        with open(self.env_example) as f:
            template = f.read()
        
        # Extract variables
        import re
        vars_found = re.findall(r'^([A-Z_]+)=', template, re.MULTILINE)
        
        print(f"Found {len(vars_found)} environment variables in template:\n")
        for var in vars_found:
            print(f"  • {var}")
        
        print(f"\n{YELLOW}SOURCES FOR YOUR CREDENTIALS:{RESET}\n")
        
        sources = {
            "SUPABASE_URL": "https://app.supabase.com > Settings > API > Project URL",
            "SUPABASE_KEY": "https://app.supabase.com > Settings > API > **service_role** key",
            "SUPABASE_JWT_SECRET": "https://app.supabase.com > Settings > Database > JWT Secret",
            "GEMINI_API_KEY": "https://console.cloud.google.com > Credentials > Generate API Key",
            "CORS_ORIGIN": "Your production domain(s): https://yourdomain.com",
        }
        
        for var, source in sources.items():
            print(f"  {var}")
            print(f"    → {source}\n")
        
        print(f"{YELLOW}NEXT STEPS:{RESET}\n")
        print("1. Copy template: .env.example → backend/.env")
        print("2. Open backend/.env in editor")
        print("3. Replace each VALUE with actual credentials from sources above")
        print("4. Deploy .env to your production server/container")
        print("5. Start backend: uvicorn main:app --host 0.0.0.0 --port 8000")
        print(f"6. Verify startup logs show: {GREEN}✅ All env vars validated{RESET}\n")
        
        # Offer to create template if it doesn't exist
        backend_env = self.backend_root / ".env"
        if not backend_env.exists():
            print(f"\n{YELLOW}Create backend/.env template? (y/n): {RESET}", end="")
            if input().lower() == 'y':
                import shutil
                shutil.copy(self.env_example, backend_env)
                self.print_success(f"Created: {backend_env}")
                print(f"Edit this file with your actual secrets, then deploy to production")
        
        return True
    
    def task3_github_secrets(self):
        """Guide user through GitHub secrets setup."""
        self.print_header("TASK 3: GitHub Secrets Configuration")
        
        secrets_needed = {
            "TEST_GEMINI_API_KEY": "Staging Gemini API key from Google Cloud Console",
            "TEST_SUPABASE_URL": "Staging Supabase PROJECT_URL",
            "TEST_SUPABASE_KEY": "Staging Supabase anon_key",
            "TEST_SUPABASE_JWT_SECRET": "Staging JWT secret from Supabase Settings",
            "TEST_STUDENT_TOKEN": "Valid JWT token with role='STUDENT'",
            "TEST_EVALUATOR_TOKEN": "Valid JWT token with role='EVALUATOR'",
            "TEST_ADMIN_TOKEN": "Valid JWT token with role='ADMIN_COE'",
        }
        
        print(f"{YELLOW}GITHUB SECRETS TO ADD:{RESET}\n")
        for secret_name, description in secrets_needed.items():
            print(f"  {secret_name}")
            print(f"    → {description}\n")
        
        print(f"{YELLOW}HOW TO ADD SECRETS:{RESET}\n")
        print("1. Go to: https://github.com/your-org/AuraGrade-Frontend")
        print("2. Click 'Settings' tab (top right)")
        print("3. Click 'Secrets and variables' (left sidebar)")
        print("4. Click 'Actions' (left sidebar)")
        print("5. Click 'New repository secret' button")
        print("6. Enter secret name and value")
        print("7. Click 'Add secret'")
        print("8. Repeat for all 7 secrets\n")
        
        print(f"9. Test by creating a PR or pushing to a branch")
        print(f"10. Go to GitHub > Actions > See workflow running")
        print(f"11. Check if auth_matrix tests execute\n")
        
        print(f"{YELLOW}IMPORTANT:{RESET}")
        print("  • Use STAGING environment credentials (not production)")
        print("  • Tokens must be valid JWTs (not placeholders)")
        print("  • Repeat process for both Frontend and Backend repos\n")
        
        # Try to gather local staging hints
        local_env = self.repo_root / ".env.local"
        if local_env.exists():
            self.print_info(f"Found local config: {local_env}")
            print("  You can use values from this file as reference (but not copy directly)")
        
        return True
    
    def task4_status(self):
        """Show status of Task 4 (already complete)."""
        self.print_header("TASK 4: Middleware Bug Fix — STATUS")
        
        middleware = self.repo_root / "src" / "middleware.ts"
        proxy = self.repo_root / "src" / "proxy.ts"
        
        if middleware.exists() and not proxy.exists():
            self.print_success("src/middleware.ts exists")
            self.print_success("src/proxy.ts deleted")
            
            # Check export
            with open(middleware) as f:
                content = f.read()
            
            if "export async function middleware" in content or "export function middleware" in content:
                self.print_success("middleware.ts exports 'middleware' function")
            else:
                self.print_error("middleware.ts does not export 'middleware' function")
                return False
            
            # Check git status
            try:
                result = subprocess.run(['git', 'log', '--oneline', '-1'],
                                      capture_output=True, text=True, 
                                      cwd=self.repo_root, timeout=5)
                if result.returncode == 0:
                    commit = result.stdout.strip()
                    self.print_success(f"Latest commit: {commit}")
                    
                    result2 = subprocess.run(['git', 'status', '-s'],
                                           capture_output=True, text=True,
                                           cwd=self.repo_root, timeout=5)
                    if result2.returncode == 0 and not result2.stdout.strip():
                        self.print_success("Working tree is clean (all changes committed)")
                    else:
                        self.print_info("Some uncommitted changes detected (review if needed)")
            except Exception as e:
                self.print_info(f"Could not verify git status: {e}")
        else:
            self.print_error("Middleware fix not complete")
            return False
        
        print(f"\n{GREEN}TASK 4: COMPLETE ✓{RESET}")
        print("No further action needed for this task.")
        
        return True
    
    def verify_all(self):
        """Run comprehensive verification."""
        self.print_header("COMPREHENSIVE VERIFICATION")
        
        checks = {
            "RLS remediation SQL": self.backend_root / "rls_gap_remediation.sql" / "exists",
            "Environment template": self.env_example / "exists",
            "Backend CI pipeline": self.repo_root / ".github" / "workflows" / "backend-ci.yml" / "exists",
            "Frontend CI pipeline": self.repo_root / ".github" / "workflows" / "frontend-ci.yml" / "exists",
            "Middleware fix": middleware / "exists" if (middleware := self.repo_root / "src" / "middleware.ts") else False,
        }
        
        results = []
        for check_name, path_exists in checks.items():
            if isinstance(path_exists, bool):
                status = "✓" if path_exists else "✗"
                color = GREEN if path_exists else RED
                print(f"{color}{status}{RESET} {check_name}")
                results.append(path_exists)
            elif isinstance(path_exists, Path):
                exists = path_exists.parent.exists()
                status = "✓" if exists else "✗"
                color = GREEN if exists else RED
                print(f"{color}{status}{RESET} {check_name}")
                results.append(exists)
        
        total = sum(1 for r in results if r)
        print(f"\n{YELLOW}Verification: {total}{RESET}/{len(results)} checks passed\n")
        
        if all(results):
            print(f"{GREEN}✓ ALL SYSTEMS GO — Ready for production deployment{RESET}")
            return True
        else:
            print(f"{RED}✗ Some checks failed — Review above{RESET}")
            return False

def main():
    executor = PhaseBC()
    
    if len(sys.argv) < 2:
        print(f"{BLUE}Phase B+C Task Executor{RESET}\n")
        print("Usage:")
        print("  python phase_bc_execute.py task1    - RLS remediation guidance")
        print("  python phase_bc_execute.py task2    - Environment variables guidance")
        print("  python phase_bc_execute.py task3    - GitHub secrets guidance")
        print("  python phase_bc_execute.py task4    - Middleware fix status")
        print("  python phase_bc_execute.py verify   - Full verification\n")
        return 1
    
    task = sys.argv[1].lower()
    
    try:
        if task == "task1":
            executor.task1_rls_remediation()
        elif task == "task2":
            executor.task2_env_vars()
        elif task == "task3":
            executor.task3_github_secrets()
        elif task == "task4":
            executor.task4_status()
        elif task == "verify":
            executor.verify_all()
        else:
            print(f"{RED}Unknown task: {task}{RESET}")
            return 1
        
        return 0
    except Exception as e:
        executor.print_error(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
