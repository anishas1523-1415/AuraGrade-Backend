"""
AuraGrade — Legacy Wrapper
=========================
This file serves as a entry point for local development. 
The production application has been refactored into the `app/` package.
"""

from app.main import app

if __name__ == "__main__":
    import uvicorn
    # Local development: python main.py
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
