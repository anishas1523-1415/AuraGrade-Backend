"""
AuraGrade — Auth Boundary Test Suite
=====================================
Tests the auth matrix exhaustively:
  - No token     → 401 on every protected endpoint
  - Student token → 403 on every staff-only endpoint
  - Staff token   → 200 on staff endpoints
  - Student data isolation (students can't read each other's grades)
  - Grade mutation permissions (only staff can approve/override)

Run:
    pip install pytest pytest-asyncio httpx
    pytest test_auth_matrix.py -v

Environment variables required:
    TEST_STUDENT_TOKEN   — valid Supabase JWT for a STUDENT role user
    TEST_STAFF_TOKEN     — valid Supabase JWT for an EVALUATOR/ADMIN_COE role user
    TEST_ADMIN_TOKEN     — valid Supabase JWT for an ADMIN_COE role user
    TEST_STUDENT_REG_NO  — a real student reg_no in the DB
    TEST_GRADE_ID        — a real grade UUID in the DB
    TEST_ASSESSMENT_ID   — a real assessment UUID in the DB
    BACKEND_URL          — backend base URL (default: http://localhost:8000)
"""

import os
import pytest
import httpx

BASE = os.environ.get("BACKEND_URL", "http://localhost:8000")

STUDENT_TOKEN   = os.environ.get("TEST_STUDENT_TOKEN", "")
STAFF_TOKEN     = os.environ.get("TEST_STAFF_TOKEN", "")
ADMIN_TOKEN     = os.environ.get("TEST_ADMIN_TOKEN", "")
STUDENT_REG_NO  = os.environ.get("TEST_STUDENT_REG_NO", "TEST001")
GRADE_ID        = os.environ.get("TEST_GRADE_ID", "00000000-0000-0000-0000-000000000000")
ASSESSMENT_ID   = os.environ.get("TEST_ASSESSMENT_ID", "00000000-0000-0000-0000-000000000001")

def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}

def no_token() -> dict:
    return {}


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE, timeout=10) as c:
        yield c


# ─── SECTION 1: No token → 401 on every protected endpoint ───────────────────

@pytest.mark.parametrize("method,path,body,files", [
    # AI endpoints
    ("POST", "/api/evaluate",        None, {"file": ("t.jpg", b"x", "image/jpeg")}),
    ("POST", "/api/grade/stream",    None, {"file": ("t.jpg", b"x", "image/jpeg")}),
    ("POST", "/api/grade",           None, {"file": ("t.jpg", b"x", "image/jpeg")}),
    ("POST", "/api/evaluate_script", {"student_answer_text": "x", "course_rubric": "y"}, None),
    ("POST", "/api/voice-to-rubric", None, None),       # form field missing → 422 after auth
    ("POST", "/api/evaluate-batch",  None, {"files": ("t.jpg", b"x", "image/jpeg")}),

    # Student PII
    ("GET",  "/api/students",        None, None),
    ("GET",  f"/api/students/{STUDENT_REG_NO}", None, None),
    ("GET",  f"/api/students/{STUDENT_REG_NO}/grades", None, None),
    ("GET",  f"/api/students/{STUDENT_REG_NO}/notifications", None, None),
    ("GET",  f"/api/results/{STUDENT_REG_NO}", None, None),

    # Grade data
    ("GET",  "/api/grades",          None, None),
    ("GET",  f"/api/grades/{GRADE_ID}", None, None),
    ("PUT",  f"/api/grades/{GRADE_ID}/approve", None, None),
    ("PUT",  f"/api/grades/{GRADE_ID}/appeal?reason=test", None, None),

    # Rubric writes
    ("POST", "/api/setup-exam",      None, {"file": ("t.pdf", b"x", "application/pdf")}),
    ("POST", f"/api/sync-rubric?assessment_id={ASSESSMENT_ID}",
             {"rubric_json": {}}, None),
    ("POST", f"/api/assessments",    {"subject": "AI", "title": "Test"}, None),
    ("POST", f"/api/model-answer?assessment_id={ASSESSMENT_ID}", None, None),

    # Ledger / Admin
    ("GET",  f"/api/ledger/{ASSESSMENT_ID}/download", None, None),
    ("GET",  f"/api/ledger/{ASSESSMENT_ID}/preview",  None, None),
    ("GET",  f"/api/ledger/{ASSESSMENT_ID}/hashes",   None, None),
    ("GET",  "/api/audit-logs",      None, None),
    ("GET",  "/api/audit-logs/stats",None, None),
    ("GET",  "/api/admin/stats",     None, None),
    ("GET",  "/api/admin/recent-activity", None, None),
    ("GET",  "/api/admin/audit-records",   None, None),

    # Audit / appeal
    ("POST", f"/api/audit-appeal/{GRADE_ID}",         None, None),
    ("POST", f"/api/audit-appeal/{GRADE_ID}/stream",  None, None),

    # Misc protected
    ("GET",  "/api/system/readiness", None, None),
    ("GET",  "/api/exam-state",        None, None),
    ("GET",  "/api/assessments",       None, None),
    ("GET",  f"/api/assessments/{ASSESSMENT_ID}/lock-status", None, None),
    ("GET",  f"/api/batch-status/fake-job-id", None, None),
])
def test_no_token_returns_401(client, method, path, body, files):
    """Every protected endpoint must return 401 when called without a token."""
    kwargs = {"headers": no_token()}
    if files:
        kwargs["files"] = files
    elif body:
        kwargs["json"] = body

    resp = getattr(client, method.lower())(path, **kwargs)
    assert resp.status_code == 401, (
        f"{method} {path} returned {resp.status_code}, expected 401. "
        f"Body: {resp.text[:200]}"
    )


# ─── SECTION 2: Student token → 403 on staff-only endpoints ──────────────────

@pytest.mark.skipif(not STUDENT_TOKEN, reason="TEST_STUDENT_TOKEN not set")
@pytest.mark.parametrize("method,path,body", [
    # Student-exclusive staff endpoints
    ("GET",  "/api/students",         None),
    ("GET",  "/api/grades",           None),
    ("PUT",  f"/api/grades/{GRADE_ID}/approve", None),
    ("PUT",  f"/api/grades/{GRADE_ID}/override?new_score=9", None),
    ("GET",  "/api/audit-logs",       None),
    ("GET",  "/api/audit-logs/stats", None),
    ("GET",  "/api/admin/stats",      None),
    ("GET",  "/api/admin/recent-activity", None),
    ("GET",  "/api/admin/audit-records",   None),
    ("GET",  f"/api/ledger/{ASSESSMENT_ID}/download", None),
    ("GET",  f"/api/ledger/{ASSESSMENT_ID}/hashes",   None),
    ("POST", f"/api/audit-appeal/{GRADE_ID}", None),
    ("POST", f"/api/audit-appeal/{GRADE_ID}/stream", None),
    ("GET",  f"/api/knowledge-map/{ASSESSMENT_ID}", None),
    ("POST", "/api/setup-exam",       None),
    ("POST", f"/api/assessments",     {"subject": "AI", "title": "Test"}),
    ("POST", f"/api/assessments/{ASSESSMENT_ID}/lock", None),
    ("GET",  f"/api/institutional-ledger/{ASSESSMENT_ID}/download", None),
    ("GET",  "/api/staff/appeals/pending", None),
])
def test_student_token_returns_403_on_staff_endpoints(client, method, path, body):
    """A STUDENT role token must receive 403 on all staff-only endpoints."""
    kwargs = {"headers": auth(STUDENT_TOKEN)}
    if body:
        kwargs["json"] = body

    resp = getattr(client, method.lower())(path, **kwargs)
    assert resp.status_code == 403, (
        f"{method} {path} returned {resp.status_code} for student, expected 403. "
        f"Body: {resp.text[:200]}"
    )


# ─── SECTION 3: Student data isolation ───────────────────────────────────────

@pytest.mark.skipif(not STUDENT_TOKEN, reason="TEST_STUDENT_TOKEN not set")
def test_student_cannot_read_another_students_grades(client):
    """
    A student authenticated with their own token must not be able to read
    another student's grades. The backend should return 403 (ownership check).
    """
    # Use a reg_no that belongs to a DIFFERENT student than the token owner
    other_reg_no = "OTHER_STUDENT_REG"
    resp = client.get(
        f"/api/students/{other_reg_no}/grades",
        headers=auth(STUDENT_TOKEN)
    )
    assert resp.status_code == 403, (
        f"Student could read another student's grades! Got {resp.status_code}. "
        "Ownership check is broken."
    )


@pytest.mark.skipif(not STUDENT_TOKEN, reason="TEST_STUDENT_TOKEN not set")
def test_student_can_read_own_grades(client):
    """A student should be able to read their own grade record (200)."""
    resp = client.get(
        f"/api/students/{STUDENT_REG_NO}/grades",
        headers=auth(STUDENT_TOKEN)
    )
    # 200 = found, 404 = not in DB (still passing — auth boundary is what matters)
    assert resp.status_code in (200, 404), (
        f"Student reading own grades got {resp.status_code}. Expected 200 or 404."
    )


# ─── SECTION 4: Grade mutation permissions ────────────────────────────────────

@pytest.mark.skipif(not STUDENT_TOKEN, reason="TEST_STUDENT_TOKEN not set")
def test_student_cannot_approve_grade(client):
    """Students must not be able to approve grades."""
    resp = client.put(
        f"/api/grades/{GRADE_ID}/approve",
        headers=auth(STUDENT_TOKEN)
    )
    assert resp.status_code == 403, (
        f"Student approved a grade! Got {resp.status_code}. "
        "The optional_auth fix may have regressed."
    )


@pytest.mark.skipif(not STUDENT_TOKEN, reason="TEST_STUDENT_TOKEN not set")
def test_student_cannot_override_grade(client):
    """Students must not be able to override grade scores."""
    resp = client.put(
        f"/api/grades/{GRADE_ID}/override?new_score=10",
        headers=auth(STUDENT_TOKEN)
    )
    assert resp.status_code == 403


@pytest.mark.skipif(not STUDENT_TOKEN, reason="TEST_STUDENT_TOKEN not set")
def test_student_can_submit_appeal(client):
    """Students should be able to appeal their own grade (200 or 404)."""
    resp = client.put(
        f"/api/grades/{GRADE_ID}/appeal?reason=I+deserve+more",
        headers=auth(STUDENT_TOKEN)
    )
    assert resp.status_code in (200, 404), (
        f"Student appeal got unexpected {resp.status_code}"
    )


# ─── SECTION 5: Staff access works correctly ─────────────────────────────────

@pytest.mark.skipif(not STAFF_TOKEN, reason="TEST_STAFF_TOKEN not set")
def test_staff_can_list_grades(client):
    resp = client.get("/api/grades", headers=auth(STAFF_TOKEN))
    assert resp.status_code == 200


@pytest.mark.skipif(not STAFF_TOKEN, reason="TEST_STAFF_TOKEN not set")
def test_staff_can_list_students(client):
    resp = client.get("/api/students", headers=auth(STAFF_TOKEN))
    assert resp.status_code == 200


@pytest.mark.skipif(not STAFF_TOKEN, reason="TEST_STAFF_TOKEN not set")
def test_staff_can_approve_grade(client):
    resp = client.put(
        f"/api/grades/{GRADE_ID}/approve",
        headers=auth(STAFF_TOKEN)
    )
    assert resp.status_code in (200, 404)  # 404 = grade not in test DB


@pytest.mark.skipif(not ADMIN_TOKEN, reason="TEST_ADMIN_TOKEN not set")
def test_admin_can_download_ledger(client):
    resp = client.get(
        f"/api/ledger/{ASSESSMENT_ID}/download",
        headers=auth(ADMIN_TOKEN)
    )
    # 200 = has approved grades, 404 = no grades yet — both are auth-correct
    assert resp.status_code in (200, 404)


# ─── SECTION 6: Rate limiting ─────────────────────────────────────────────────

@pytest.mark.skipif(not STAFF_TOKEN, reason="TEST_STAFF_TOKEN not set")
def test_rate_limit_kicks_in_on_evaluate_batch(client):
    """
    Hitting /api/evaluate-batch more than 3 times in a minute should
    return 429 on the 4th request.
    """
    if not os.environ.get("TEST_RATE_LIMITS", ""):
        pytest.skip("Set TEST_RATE_LIMITS=1 to run rate limit tests (slow)")

    import io
    dummy_file = ("file.jpg", io.BytesIO(b"\xff\xd8\xff" + b"0" * 100), "image/jpeg")

    responses = []
    for _ in range(5):
        r = client.post(
            "/api/evaluate-batch",
            headers=auth(STAFF_TOKEN),
            files={"files": dummy_file}
        )
        responses.append(r.status_code)

    assert 429 in responses, (
        f"Rate limit not triggered after 5 requests to /api/evaluate-batch. "
        f"Responses: {responses}"
    )


# ─── SECTION 7: Health check is still public ─────────────────────────────────

def test_root_health_check_is_public(client):
    """The root / endpoint should remain publicly accessible."""
    resp = client.get("/")
    assert resp.status_code == 200


# ─── SECTION 8: Request ID header present ────────────────────────────────────

def test_x_request_id_header_present(client):
    """Every response must include X-Request-ID for log correlation."""
    resp = client.get("/")
    assert "x-request-id" in resp.headers, (
        "X-Request-ID header missing — RequestLoggerMiddleware may not be mounted"
    )
    assert len(resp.headers["x-request-id"]) >= 8


if __name__ == "__main__":
    import subprocess, sys
    sys.exit(subprocess.call(["pytest", __file__, "-v", "--tb=short"]))
