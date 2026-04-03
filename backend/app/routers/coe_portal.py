from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import hmac
import os
import secrets
from typing import Any, Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from supabase import Client

from app.config import get_settings
from app.dependencies import get_supabase
from app.logging_config import get_logger

router = APIRouter(prefix="/api/coe", tags=["COE Portal"])
logger = get_logger("coe_portal_router")
bearer_scheme = HTTPBearer(auto_error=False)
PBKDF2_ITERATIONS = 210_000


class CoeLoginBody(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    dob: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    email: str = Field(..., min_length=3, max_length=320)
    password: str = Field(..., min_length=8, max_length=200)


class CoeMemberOut(BaseModel):
    id: str
    full_name: str
    email: str
    role: str
    department: Optional[str] = None
    is_active: bool = True


class StaffProfileBody(BaseModel):
    full_name: str = Field(..., min_length=1, max_length=200)
    email: str = Field(..., min_length=3, max_length=320)
    role: str = Field(..., min_length=3, max_length=40)
    subjects: list[str] = Field(default_factory=list)
    departments: list[str] = Field(default_factory=list)
    years: list[str] = Field(default_factory=list)
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)
    is_active: bool = True


class StaffProfileUpdateBody(BaseModel):
    full_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    email: Optional[str] = Field(default=None, min_length=3, max_length=320)
    role: Optional[str] = Field(default=None, min_length=3, max_length=40)
    subjects: Optional[list[str]] = None
    departments: Optional[list[str]] = None
    years: Optional[list[str]] = None
    password: Optional[str] = Field(default=None, min_length=8, max_length=200)
    is_active: Optional[bool] = None


def _normalize_email(value: str) -> str:
    return value.strip().lower()


def _normalize_role(value: str) -> str:
    return value.strip().upper()


def _parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="DOB must use YYYY-MM-DD format.") from exc


def _hash_password(password: str, salt: Optional[str] = None) -> str:
    salt_hex = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_hex}${derived.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_str, salt_hex, digest_hex = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = _hash_password(password, salt_hex)
        return hmac.compare_digest(expected, stored_hash)
    except ValueError:
        return False


def _settings_secret() -> str:
    settings = get_settings()
    return settings.SUPABASE_JWT_SECRET


def _create_token(member: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": member["id"],
        "portal": "coe",
        "role": member.get("role", "ADMIN_COE"),
        "email": member.get("email"),
        "full_name": member.get("full_name"),
        "department": member.get("department"),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=8)).timestamp()),
    }
    return jwt.encode(payload, _settings_secret(), algorithm="HS256")


def _decode_token(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, _settings_secret(), algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired COE session.") from exc

    if payload.get("portal") != "coe":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid portal token.")
    return payload


def _extract_user_id(payload: Any) -> Optional[str]:
    if payload is None:
        return None
    if hasattr(payload, "id") and getattr(payload, "id"):
        return str(getattr(payload, "id"))
    if hasattr(payload, "user") and getattr(payload, "user") is not None:
        user = getattr(payload, "user")
        if hasattr(user, "id") and getattr(user, "id"):
            return str(getattr(user, "id"))
        if isinstance(user, dict) and user.get("id"):
            return str(user.get("id"))
    if isinstance(payload, dict):
        if payload.get("id"):
            return str(payload.get("id"))
        user = payload.get("user")
        if isinstance(user, dict) and user.get("id"):
            return str(user.get("id"))
    return None


def _find_auth_user_by_email(supabase: Client, email: str) -> Optional[Any]:
    target = _normalize_email(email)
    listed = supabase.auth.admin.list_users()
    users = None

    if isinstance(listed, list):
        users = listed
    elif hasattr(listed, "users"):
        users = getattr(listed, "users")
    elif isinstance(listed, dict) and isinstance(listed.get("users"), list):
        users = listed.get("users")

    if not users:
        return None

    for user in users:
        user_email = ""
        if hasattr(user, "email"):
            user_email = str(getattr(user, "email") or "")
        elif isinstance(user, dict):
            user_email = str(user.get("email") or "")
        if _normalize_email(user_email) == target:
            return user
    return None


def _ensure_staff_auth_identity(
    supabase: Client,
    *,
    full_name: str,
    email: str,
    role: str,
    department: Optional[str],
    password: Optional[str],
) -> str:
    existing_user = _find_auth_user_by_email(supabase, email)
    normalized_email = _normalize_email(email)

    if existing_user is None:
        if not password:
            raise HTTPException(status_code=400, detail="Password is required to provision login credentials.")

        created = supabase.auth.admin.create_user(
            {
                "email": normalized_email,
                "password": password,
                "email_confirm": True,
                "user_metadata": {"full_name": full_name},
            }
        )
        auth_user_id = _extract_user_id(created)
    else:
        auth_user_id = _extract_user_id(existing_user)
        update_payload: dict[str, Any] = {
            "email": normalized_email,
            "email_confirm": True,
            "user_metadata": {"full_name": full_name},
        }
        if password:
            update_payload["password"] = password
        if auth_user_id:
            supabase.auth.admin.update_user_by_id(auth_user_id, update_payload)

    if not auth_user_id:
        raise HTTPException(status_code=500, detail="Failed to provision Supabase Auth user for staff profile.")

    supabase.table("profiles").upsert(
        {
            "id": auth_user_id,
            "full_name": full_name,
            "email": normalized_email,
            "department": department or "",
            "role": role,
        },
        on_conflict="id",
    ).execute()

    return auth_user_id


async def require_coe_member(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    supabase: Client = Depends(get_supabase),
) -> dict[str, Any]:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing COE session token.")

    payload = _decode_token(credentials.credentials)
    member_id = payload.get("sub")
    if not member_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid COE session token.")

    try:
        result = (
            supabase.table("coe_office_members")
            .select("id, full_name, email, role, department, is_active")
            .eq("id", member_id)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.error(f"Failed to resolve COE member: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Unable to validate COE session.")

    member = result.data or None
    if not member or not member.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="COE account is inactive.")
    return member


def require_admin_coe(member: dict[str, Any] = Depends(require_coe_member)) -> dict[str, Any]:
    role = _normalize_role(str(member.get("role") or ""))
    if role != "ADMIN_COE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="COE admin access required.")
    return member


@router.post("/login")
async def coe_login(body: CoeLoginBody, supabase: Client = Depends(get_supabase)):
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    email = _normalize_email(body.email)
    provided_name = body.full_name.strip().casefold()
    dob_value = _parse_iso_date(body.dob)

    try:
        result = (
            supabase.table("coe_office_members")
            .select("id, full_name, email, dob, password_hash, role, department, is_active")
            .eq("email", email)
            .single()
            .execute()
        )
    except Exception as exc:
        logger.error(f"COE login lookup failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Login lookup failed.")

    member = result.data or None
    if not member or not member.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid COE credentials.")

    db_name = str(member.get("full_name") or "").strip().casefold()
    db_dob = member.get("dob")
    if db_name != provided_name:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid COE credentials.")

    if isinstance(db_dob, str):
        db_dob_str = db_dob[:10]
    elif isinstance(db_dob, date):
        db_dob_str = db_dob.isoformat()
    else:
        db_dob_str = str(db_dob or "")[:10]

    if db_dob_str != dob_value.isoformat():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid COE credentials.")

    if not _verify_password(body.password, str(member.get("password_hash") or "")):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid COE credentials.")

    token = _create_token(member)
    safe_member = {
        "id": member["id"],
        "full_name": member["full_name"],
        "email": member["email"],
        "role": member.get("role", "ADMIN_COE"),
        "department": member.get("department"),
        "is_active": member.get("is_active", True),
    }
    return {"status": "success", "access_token": token, "member": safe_member}


@router.get("/me")
async def get_me(member: dict[str, Any] = Depends(require_coe_member)):
    return {"status": "success", "member": member}


@router.get("/summary")
async def get_summary(
    supabase: Client = Depends(get_supabase),
    _: dict[str, Any] = Depends(require_coe_member),
):
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    try:
        members = supabase.table("coe_office_members").select("id, role, is_active").execute().data or []
        profiles = supabase.table("coe_staff_profiles").select("id, role, is_active").execute().data or []
        return {
            "status": "success",
            "data": {
                "office_members": len(members),
                "active_office_members": sum(1 for row in members if row.get("is_active", True)),
                "staff_profiles": len(profiles),
                "evaluators": sum(1 for row in profiles if _normalize_role(str(row.get("role") or "")) == "EVALUATOR"),
                "hods": sum(1 for row in profiles if _normalize_role(str(row.get("role") or "")) == "HOD_AUDITOR"),
                "active_staff_profiles": sum(1 for row in profiles if row.get("is_active", True)),
            },
        }
    except Exception as exc:
        logger.error(f"COE summary failed: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to load COE summary")


@router.get("/staff-profiles")
async def list_staff_profiles(
    supabase: Client = Depends(get_supabase),
    _: dict[str, Any] = Depends(require_admin_coe),
):
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    result = (
        supabase.table("coe_staff_profiles")
        .select("id, full_name, email, role, subjects, departments, years, is_active, created_at, updated_at")
        .order("created_at", desc=True)
        .execute()
    )
    return {"status": "success", "data": result.data or []}


@router.post("/staff-profiles")
async def create_staff_profile(
    body: StaffProfileBody,
    supabase: Client = Depends(get_supabase),
    _: dict[str, Any] = Depends(require_admin_coe),
):
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    role = _normalize_role(body.role)
    if role not in {"EVALUATOR", "HOD_AUDITOR"}:
        raise HTTPException(status_code=400, detail="Role must be EVALUATOR or HOD_AUDITOR")
    if not body.password:
        raise HTTPException(status_code=400, detail="Password is required for new profiles.")

    normalized_email = _normalize_email(body.email)
    normalized_name = body.full_name.strip()
    primary_department = body.departments[0] if body.departments else ""

    _ensure_staff_auth_identity(
        supabase,
        full_name=normalized_name,
        email=normalized_email,
        role=role,
        department=primary_department,
        password=body.password,
    )

    payload = {
        "full_name": normalized_name,
        "email": normalized_email,
        "role": role,
        "subjects": body.subjects,
        "departments": body.departments,
        "years": body.years,
        "password_hash": _hash_password(body.password),
        "is_active": body.is_active,
    }

    try:
        result = supabase.table("coe_staff_profiles").insert(payload).execute()
        return {"status": "success", "data": result.data or []}
    except Exception as exc:
        logger.error(f"Failed to create COE staff profile: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create staff profile")


@router.put("/staff-profiles/{profile_id}")
async def update_staff_profile(
    profile_id: str,
    body: StaffProfileUpdateBody,
    supabase: Client = Depends(get_supabase),
    _: dict[str, Any] = Depends(require_admin_coe),
):
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    existing = (
        supabase.table("coe_staff_profiles")
        .select("id, full_name, email, role, subjects, departments, years, is_active")
        .eq("id", profile_id)
        .single()
        .execute()
    )
    existing_row = existing.data or None
    if not existing_row:
        raise HTTPException(status_code=404, detail="Staff profile not found")

    payload: dict[str, Any] = {}
    if body.full_name is not None:
        payload["full_name"] = body.full_name.strip()
    if body.email is not None:
        payload["email"] = _normalize_email(body.email)
    if body.role is not None:
        role = _normalize_role(body.role)
        if role not in {"EVALUATOR", "HOD_AUDITOR"}:
            raise HTTPException(status_code=400, detail="Role must be EVALUATOR or HOD_AUDITOR")
        payload["role"] = role
    if body.subjects is not None:
        payload["subjects"] = body.subjects
    if body.departments is not None:
        payload["departments"] = body.departments
    if body.years is not None:
        payload["years"] = body.years
    if body.is_active is not None:
        payload["is_active"] = body.is_active
    if body.password:
        payload["password_hash"] = _hash_password(body.password)

    if not payload:
        raise HTTPException(status_code=400, detail="No fields provided for update.")

    target_name = payload.get("full_name", existing_row.get("full_name", ""))
    target_email = payload.get("email", existing_row.get("email", ""))
    target_role = payload.get("role", existing_row.get("role", "EVALUATOR"))
    target_departments = payload.get("departments", existing_row.get("departments", []))
    target_department = target_departments[0] if isinstance(target_departments, list) and target_departments else ""

    _ensure_staff_auth_identity(
        supabase,
        full_name=str(target_name),
        email=str(target_email),
        role=str(target_role),
        department=str(target_department),
        password=body.password,
    )

    try:
        result = supabase.table("coe_staff_profiles").update(payload).eq("id", profile_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Staff profile not found")
        return {"status": "success", "data": result.data}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to update COE staff profile {profile_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update staff profile")


@router.delete("/staff-profiles/{profile_id}")
async def delete_staff_profile(
    profile_id: str,
    supabase: Client = Depends(get_supabase),
    _: dict[str, Any] = Depends(require_admin_coe),
):
    if supabase is None:
        raise HTTPException(status_code=503, detail="Database not configured")

    existing = (
        supabase.table("coe_staff_profiles")
        .select("id, email")
        .eq("id", profile_id)
        .single()
        .execute()
    )
    existing_row = existing.data or None
    if not existing_row:
        raise HTTPException(status_code=404, detail="Staff profile not found")

    try:
        existing_user = _find_auth_user_by_email(supabase, str(existing_row.get("email") or ""))
        auth_user_id = _extract_user_id(existing_user)
        if auth_user_id:
            supabase.table("profiles").delete().eq("id", auth_user_id).execute()

        result = supabase.table("coe_staff_profiles").delete().eq("id", profile_id).execute()
        if not result.data:
            raise HTTPException(status_code=404, detail="Staff profile not found")
        return {"status": "success", "message": "Profile deleted"}
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to delete COE staff profile {profile_id}: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to delete staff profile")
