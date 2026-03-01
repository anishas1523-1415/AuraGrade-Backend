@echo off
echo =========================================
echo   AuraGrade - Push to GitHub
echo =========================================
echo.

:: Get commit message from user (or use default)
set /p MSG="Commit message (or press Enter for default): "
if "%MSG%"=="" set MSG=Update AuraGrade

echo.
echo --- Pushing Frontend (src + mobile) ---
cd /d d:\PROJECTS\AuraGrade
git add .
git commit -m "%MSG% [frontend]"
git push origin master
echo.

echo --- Pushing Backend (Python API) ---
cd /d d:\PROJECTS\AuraGrade\backend
git add .
git commit -m "%MSG% [backend]"
git push origin master
echo.

echo =========================================
echo   Done! Both repos updated on GitHub.
echo =========================================
echo   Frontend: https://github.com/anishas1523-1415/AuraGrade-Frontend
echo   Backend:  https://github.com/anishas1523-1415/AuraGrade-Backend
echo =========================================
pause
