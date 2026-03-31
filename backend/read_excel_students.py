import openpyxl
import json
from datetime import datetime

wb = openpyxl.load_workbook("AuraGrade student DB1.xlsx")
ws = wb.active

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
                    dob = str(row[3])[:10]
            except:
                dob = None
        
        students.append({
            "reg_no": str(row[0]).strip() if row[0] else "",
            "name": str(row[1]).strip() if len(row) > 1 and row[1] else "",
            "email": str(row[2]).strip() if len(row) > 2 and row[2] else "",
            "dob": dob,
            "course": "Data Science"
        })

print(f"Found {len(students)} students:\n")
print(json.dumps(students, indent=2))
