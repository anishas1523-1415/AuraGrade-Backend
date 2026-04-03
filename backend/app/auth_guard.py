import os
from fastapi import Request, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from functools import wraps

# Initialize Supabase Admin Client for Verification
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") # Use Service Key for backend validation

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise ValueError("CRITICAL: Supabase environment variables are missing.")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Validates the JWT token and retrieves the user from Supabase Auth."""
    token = credentials.credentials
    try:
        # Verify user token
        user_response = supabase.auth.get_user(token)
        if not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired authentication token."
            )
        return user_response.user
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}"
        )

def require_role(allowed_roles: list[str]):
    """Closure to enforce Role-Based Access Control (RBAC)."""
    def role_checker(user = Depends(verify_token)):
        # Fetch user profile to check role
        profile = supabase.table('profiles').select('role, department').eq('id', user.id).single().execute()
        
        if not profile.data or profile.data.get('role') not in allowed_roles:
            # Audit log the unauthorized attempt
            supabase.table('institutional_audit_logs').insert({
                "actor_id": user.id,
                "action": "UNAUTHORIZED_ACCESS_ATTEMPT",
                "target_id": "API_ENDPOINT",
                "ip_address": "Captured_by_Proxy"
            }).execute()
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Absolute Isolation: You do not have the required clearance to access this portal."
            )
        return {"user": user, "profile": profile.data}
    return role_checker

def require_subject_allocation(subject_id: str):
    """Ensures a Staff member is actually assigned to the Subject they are trying to access."""
    def allocation_checker(user_data = Depends(require_role(['EVALUATOR']))):
        user_id = user_data["user"].id
        
        # Verify allocation mapping
        allocation = supabase.table('staff_allocations').select('id').eq('staff_id', user_id).eq('subject_id', subject_id).execute()
        
        if not allocation.data:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Subject-Locked: You are not assigned to evaluate this subject."
            )
        return user_data
    return allocation_checker
