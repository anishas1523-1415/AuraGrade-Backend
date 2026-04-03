#!/usr/bin/env python3
"""
Sync COE Excel DB into Supabase COE portal tables.

Default source workbook: ../AuraGrade-COE.xlsx
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv
from supabase import create_client
from postgrest.exceptions import APIError

PBKDF2_ITERATIONS = 210_000


def hash_password(password: str, salt: str | None = None) -> str:
    salt_hex = salt or secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        bytes.fromhex(salt_hex),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt_hex}${derived.hex()}"


def normalize_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def parse_list_cell(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in re.split(r"[,;\n|]+", text) if part.strip()]


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).replace("'", "''")
    return f"'{text}'"


def resolve_dob(row: dict[str, Any], default_dob: str) -> str:
    dob_raw = row.get("dob")
    if dob_raw is None or (isinstance(dob_raw, float) and pd.isna(dob_raw)):
        return default_dob
    if isinstance(dob_raw, date):
        return dob_raw.isoformat()
    text = str(dob_raw).strip()
    if not text:
        return default_dob
    try:
        return pd.to_datetime(text, dayfirst=False).date().isoformat()
    except Exception:
        return default_dob


def main() -> None:
    parser = argparse.ArgumentParser(description="Import COE Excel DB into Supabase")
    parser.add_argument("--excel", default=str(Path(__file__).resolve().parent.parent / "AuraGrade-COE.xlsx"))
    parser.add_argument("--default-dob", default="1990-01-01")
    parser.add_argument("--sql-out", default=None, help="Optional path to write SQL upsert statements")
    parser.add_argument("--dry-run", action="store_true", help="Build payloads only, skip API upsert")
    args = parser.parse_args()

    backend_dir = Path(__file__).resolve().parent
    load_dotenv(backend_dir / ".env")

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("SUPABASE_URL/SUPABASE_KEY missing in backend/.env")

    excel_path = Path(args.excel)
    if not excel_path.exists():
        raise FileNotFoundError(f"Excel file not found: {excel_path}")

    df = pd.read_excel(excel_path)
    df = df.rename(columns={col: normalize_key(col) for col in df.columns})

    required_cols = {"name", "role", "mail_id", "password"}
    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in Excel: {sorted(missing)}")

    client = create_client(supabase_url, supabase_key)

    office_payload: list[dict[str, Any]] = []
    staff_payload: list[dict[str, Any]] = []

    for _, row in df.iterrows():
        row_dict = row.to_dict()
        name = str(row_dict.get("name") or "").strip()
        role_title = str(row_dict.get("role") or "").strip()
        email = str(row_dict.get("mail_id") or "").strip().lower()
        password = str(row_dict.get("password") or "").strip()

        if not name or not role_title or not email or not password:
            continue

        role_upper = role_title.upper()
        password_hash = hash_password(password)
        departments = parse_list_cell(row_dict.get("department") or row_dict.get("departments"))
        subjects = parse_list_cell(row_dict.get("subjects") or row_dict.get("subject"))
        years = parse_list_cell(row_dict.get("years") or row_dict.get("year"))

        if "EVALUATOR" in role_upper or role_upper == "HOD" or "HOD" in role_upper:
            portal_role = "HOD_AUDITOR" if "HOD" in role_upper else "EVALUATOR"
            staff_payload.append(
                {
                    "full_name": name,
                    "email": email,
                    "role": portal_role,
                    "subjects": subjects,
                    "departments": departments,
                    "years": years,
                    "password_hash": password_hash,
                    "is_active": True,
                }
            )
        else:
            office_payload.append(
                {
                    "full_name": name,
                    "dob": resolve_dob(row_dict, args.default_dob),
                    "email": email,
                    "password_hash": password_hash,
                    "role": "ADMIN_COE",
                    "designation": role_title,
                    "department": departments[0] if departments else None,
                    "is_active": True,
                }
            )

    if args.sql_out:
        sql_path = Path(args.sql_out)
        lines: list[str] = [
            "-- Auto-generated from AuraGrade-COE.xlsx",
            "-- Run after backend/coe_portal_migration.sql",
            "",
        ]

        if office_payload:
            lines.append("INSERT INTO coe_office_members (full_name, dob, email, password_hash, role, designation, department, is_active)")
            lines.append("VALUES")
            office_values = []
            for item in office_payload:
                office_values.append(
                    "(" + ", ".join([
                        sql_literal(item["full_name"]),
                        sql_literal(item["dob"]),
                        sql_literal(item["email"]),
                        sql_literal(item["password_hash"]),
                        sql_literal(item["role"]),
                        sql_literal(item.get("designation")),
                        sql_literal(item.get("department")),
                        sql_literal(item.get("is_active", True)),
                    ]) + ")"
                )
            lines.append(",\n".join(office_values))
            lines.append("ON CONFLICT (email) DO UPDATE SET")
            lines.append("  full_name = EXCLUDED.full_name,")
            lines.append("  dob = EXCLUDED.dob,")
            lines.append("  password_hash = EXCLUDED.password_hash,")
            lines.append("  role = EXCLUDED.role,")
            lines.append("  designation = EXCLUDED.designation,")
            lines.append("  department = EXCLUDED.department,")
            lines.append("  is_active = EXCLUDED.is_active;")
            lines.append("")

        if staff_payload:
            lines.append("INSERT INTO coe_staff_profiles (full_name, email, role, subjects, departments, years, password_hash, is_active)")
            lines.append("VALUES")
            staff_values = []
            for item in staff_payload:
                subjects = sql_literal(json.dumps(item.get("subjects", []))) + "::jsonb"
                departments = sql_literal(json.dumps(item.get("departments", []))) + "::jsonb"
                years = sql_literal(json.dumps(item.get("years", []))) + "::jsonb"
                staff_values.append(
                    "(" + ", ".join([
                        sql_literal(item["full_name"]),
                        sql_literal(item["email"]),
                        sql_literal(item["role"]),
                        subjects,
                        departments,
                        years,
                        sql_literal(item["password_hash"]),
                        sql_literal(item.get("is_active", True)),
                    ]) + ")"
                )
            lines.append(",\n".join(staff_values))
            lines.append("ON CONFLICT (email) DO UPDATE SET")
            lines.append("  full_name = EXCLUDED.full_name,")
            lines.append("  role = EXCLUDED.role,")
            lines.append("  subjects = EXCLUDED.subjects,")
            lines.append("  departments = EXCLUDED.departments,")
            lines.append("  years = EXCLUDED.years,")
            lines.append("  password_hash = EXCLUDED.password_hash,")
            lines.append("  is_active = EXCLUDED.is_active;")
            lines.append("")

        sql_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"SQL seed file written: {sql_path}")

    if not args.dry_run:
        try:
            if office_payload:
                client.table("coe_office_members").upsert(office_payload, on_conflict="email").execute()
            if staff_payload:
                client.table("coe_staff_profiles").upsert(staff_payload, on_conflict="email").execute()
        except APIError as exc:
            if str(getattr(exc, "code", "")) == "PGRST205" or "schema cache" in str(exc).lower():
                raise RuntimeError(
                    "COE tables are missing in Supabase. Run backend/coe_portal_migration.sql first, then rerun this script."
                ) from exc
            raise

    print(f"Excel source: {excel_path}")
    print(f"Office member rows synced: {len(office_payload)}")
    print(f"Staff profile rows synced: {len(staff_payload)}")
    if args.default_dob:
        print(f"Default DOB used when missing: {args.default_dob}")


if __name__ == "__main__":
    main()
