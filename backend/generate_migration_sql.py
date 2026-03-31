import openpyxl
import json
from datetime import datetime

# Load the Excel file
wb = openpyxl.load_workbook("AuraGrade student DB1.xlsx")
ws = wb.active

# Extract students (skip header row)
students = []
for row in ws.iter_rows(min_row=2, values_only=True):
    if row and row[0]:  # Check if first cell has value
        # Extract date of birth
        dob = None
        if len(row) > 3 and row[3]:
            try:
                if isinstance(row[3], datetime):
                    dob = row[3].strftime("%Y-%m-%d")
                else:
                    dob_str = str(row[3])[:10]
                    dob = dob_str if dob_str else None
            except:
                dob = None
        
        students.append({
            "reg_no": str(row[2]).strip() if len(row) > 2 and row[2] else f"23TUAD{int(row[0]):03d}",
            "name": str(row[1]).strip() if len(row) > 1 and row[1] else "",
            "email": str(row[4]).strip().lower() if len(row) > 4 and row[4] and str(row[4]).strip() else None,
            "dob": dob,
            "course": "Data Science"
        })

# Generate SQL migration
sql_lines = [
    "-- ============================================================",
    "-- Migration: Insert 63 Students from Excel DB",
    "-- AuraGrade student DB1.xlsx",
    "-- ============================================================",
    "-- This migration syncs students from the Excel file",
    "-- Date of birth + exact XLS gmail IDs included",
    "",
    "INSERT INTO students (reg_no, name, email, dob, course)",
    "VALUES"
]

for i, student in enumerate(students):
    dob_val = f"'{student['dob']}'" if student['dob'] else "NULL"
    email_val = f"'{student['email']}'" if student['email'] else "NULL"
    is_last = i == len(students) - 1
    comma = "" if is_last else ","
    
    line = f"  ('{student['reg_no']}', '{student['name'].replace(chr(39), chr(39)*2)}', {email_val}, {dob_val}, 'Data Science'){comma}"
    sql_lines.append(line)

sql_lines.extend([
    "ON CONFLICT (reg_no) DO UPDATE SET",
    "  name = EXCLUDED.name,",
    "  email = COALESCE(EXCLUDED.email, students.email),",
    "  dob = EXCLUDED.dob,",
    "  course = EXCLUDED.course;",
    "",
    "",
    "-- Verify insertion",
    "SELECT COUNT(*) as total_students FROM students;"
])

# Write to file
with open("migration_excel_students_with_dob.sql", "w") as f:
    f.write("\n".join(sql_lines))

print(f"Generated SQL migration for {len(students)} students")
print("File: migration_excel_students_with_dob.sql")
print("\nSample data:")
for student in students[:5]:
    print(f"   {student['reg_no']} - {student['name'][:40]:<40} - DOB: {student['dob']}")
print(f"   ... ({len(students) - 5} more)")
