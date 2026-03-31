#!/bin/bash
# Phase B+C: Automated Deployment Script
# Helps orchestrate the final deployment steps
# 
# Usage:
#   bash deploy.sh setup    - Prepare backend .env
#   bash deploy.sh validate - Validate all systems
#   bash deploy.sh deploy   - Deploy to production

set -e

GREEN='\033[92m'
RED='\033[91m'
YELLOW='\033[93m'
RESET='\033[0m'

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_ROOT="$REPO_ROOT/backend"

log_success() {
    echo -e "${GREEN}✓${RESET} $1"
}

log_error() {
    echo -e "${RED}✗${RESET} $1" >&2
}

log_info() {
    echo -e "${YELLOW}ℹ${RESET} $1"
}

log_header() {
    echo ""
    echo -e "${YELLOW}================================${RESET}"
    echo -e "$1"
    echo -e "${YELLOW}================================${RESET}"
    echo ""
}

setup_env() {
    log_header "Setting Up Environment Variables"
    
    if [ -f "$BACKEND_ROOT/.env" ]; then
        log_info ".env already exists at $BACKEND_ROOT/.env"
        read -p "Overwrite? (y/n) " -r
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            log_info "Skipping .env creation"
            return 0
        fi
    fi
    
    if [ ! -f "$REPO_ROOT/.env.example" ]; then
        log_error ".env.example not found"
        return 1
    fi
    
    cp "$REPO_ROOT/.env.example" "$BACKEND_ROOT/.env"
    log_success "Created $BACKEND_ROOT/.env"
    
    echo ""
    echo "Edit the file with your production credentials:"
    echo "  vim $BACKEND_ROOT/.env"
    echo ""
    echo "Required values from Supabase Dashboard:"
    echo "  SUPABASE_URL = Settings > API > Project URL"
    echo "  SUPABASE_KEY = Settings > API > service_role key"
    echo "  SUPABASE_JWT_SECRET = Settings > Database > JWT Secret"
    echo ""
    echo "Required values from Google Cloud Console:"
    echo "  GEMINI_API_KEY = API Keys"
    echo ""
    echo "When done, set CORS_ORIGIN to your production domain and save."
}

validate_env() {
    log_header "Validating Environment Configuration"
    
    if [ ! -f "$BACKEND_ROOT/.env" ]; then
        log_error ".env not found at $BACKEND_ROOT/.env"
        return 1
    fi
    
    required_vars=("SUPABASE_URL" "SUPABASE_KEY" "SUPABASE_JWT_SECRET" "GEMINI_API_KEY")
    
    missing=0
    for var in "${required_vars[@]}"; do
        value=$(grep "^$var=" "$BACKEND_ROOT/.env" | cut -d= -f2- || echo "")
        if [ -z "$value" ] || [ "$value" == "YOUR_VALUE" ]; then
            log_error "$var is not set or is placeholder"
            missing=$((missing + 1))
        else
            log_success "$var is configured"
        fi
    done
    
    if [ $missing -eq 0 ]; then
        log_success "All required environment variables are configured"
        return 0
    else
        log_error "$missing variables need to be configured"
        return 1
    fi
}

validate_rls() {
    log_header "Validating RLS Configuration"
    
    if [ ! -f "$BACKEND_ROOT/rls_gap_remediation.sql" ]; then
        log_error "RLS remediation script not found"
        return 1
    fi
    
    log_success "RLS remediation script found"
    echo ""
    echo "Execute this SQL in Supabase > SQL Editor:"
    echo "  1. Copy: $BACKEND_ROOT/rls_gap_remediation.sql"
    echo "  2. Paste into Supabase SQL Editor"
    echo "  3. Click Execute"
    echo "  4. Verify with: SELECT COUNT(*) FROM pg_policies WHERE tablename IN ('students', 'grades', 'audit_logs');"
}

validate_ci() {
    log_header "Validating CI/CD Configuration"
    
    if [ ! -f "$REPO_ROOT/.github/workflows/backend-ci.yml" ]; then
        log_error "Backend CI pipeline not found"
        return 1
    fi
    log_success "Backend CI pipeline found"
    
    if [ ! -f "$REPO_ROOT/.github/workflows/frontend-ci.yml" ]; then
        log_error "Frontend CI pipeline not found"
        return 1
    fi
    log_success "Frontend CI pipeline found"
    
    echo ""
    echo "GitHub Secrets needed:"
    echo "  1. TEST_GEMINI_API_KEY"
    echo "  2. TEST_SUPABASE_URL"
    echo "  3. TEST_SUPABASE_KEY"
    echo "  4. TEST_SUPABASE_JWT_SECRET"
    echo "  5. TEST_STUDENT_TOKEN"
    echo "  6. TEST_EVALUATOR_TOKEN"
    echo "  7. TEST_ADMIN_TOKEN"
    echo ""
    echo "Add these in: GitHub > Settings > Secrets and variables > Actions"
}

validate_proxy() {
    log_header "Validating Proxy Fix"

    if [ ! -f "$REPO_ROOT/src/proxy.ts" ]; then
        log_error "src/proxy.ts not found"
        return 1
    fi
    log_success "src/proxy.ts found"

    if ! grep -q "export.*function proxy" "$REPO_ROOT/src/proxy.ts"; then
        log_error "proxy.ts does not export 'proxy' function"
        return 1
    fi
    log_success "proxy.ts exports correct function name"
}

validate_all() {
    log_header "Full Validation"
    
    echo "Checking: RLS remediation script"
    validate_rls || return 1
    
    echo ""
    echo "Checking: CI/CD pipelines"
    validate_ci || return 1
    
    echo ""
    echo "Checking: Proxy fix"
    validate_proxy || return 1
    
    echo ""
    echo "Checking: Environment variables"
    validate_env || return 1
    
    echo ""
    log_success "All validation checks passed"
    return 0
}

deploy() {
    log_header "Deployment Checklist"
    
    echo "Prerequisites:"
    echo "  [ ] RLS remediation SQL executed in Supabase"
    echo "  [ ] .env deployed to production server"
    echo "  [ ] GitHub Secrets configured (7 values)"
    echo "  [ ] src/middleware.ts deployed with frontend"
    echo ""
    
    read -p "Have you completed all prerequisites? (y/n) " -r
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Please complete prerequisites first"
        return 1
    fi
    
    echo ""
    echo "Deployment commands:"
    echo ""
    echo "1. Backend deployment:"
    echo "   cd $BACKEND_ROOT"
    echo "   pip install -r requirements.txt"
    echo "   uvicorn main:app --host 0.0.0.0 --port 8000"
    echo ""
    echo "2. Frontend deployment:"
    echo "   cd $REPO_ROOT"
    echo "   npm ci"
    echo "   npm run build"
    echo "   # Deploy build/ to your hosting (Vercel, etc.)"
    echo ""
    echo "3. Verification:"
    echo "   # Test unauthenticated request (should 401)"
    echo "   curl http://your-backend/api/system/readiness"
    echo ""
    echo "   # Test authenticated request (should 200)"
    echo "   curl -H 'Authorization: Bearer YOUR_TOKEN' http://your-backend/api/system/readiness"
    echo ""
    echo "   # Check request ID header"
    echo "   curl -I http://your-backend/api/system/readiness"
    echo ""
    
    log_success "Ready for deployment"
}

main() {
    if [ $# -eq 0 ]; then
        echo "Usage:"
        echo "  $0 setup      - Create and setup .env template"
        echo "  $0 validate   - Validate all systems"
        echo "  $0 deploy     - Show deployment checklist"
        return 1
    fi
    
    case "$1" in
        setup)
            setup_env
            ;;
        validate)
            validate_all
            ;;
        deploy)
            deploy
            ;;
        *)
            log_error "Unknown command: $1"
            return 1
            ;;
    esac
}

main "$@"
