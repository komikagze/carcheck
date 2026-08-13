@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo carcheck - polnyy lokalnyy cikl: sborschik -^> eksport v dist/
echo (opciyonalno - osnovnoy scenariy teper avtomaticheskiy, cherez
echo  .github/workflows/weekly.yml na GitHub Actions).
echo Odna komanda dlya Planировщика zadaniy Windows, esli ne khotite
echo polagatsya na GitHub Actions.
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python ne nayden v PATH.
  pause
  exit /b 1
)

if not exist "%~dp0.venv" (
  python -m venv "%~dp0.venv"
)
call "%~dp0.venv\Scripts\activate.bat"
pip install -q -r "%~dp0requirements.txt"

echo [1/2] Sborschik ...
python "%~dp0collector\collector.py"
if errorlevel 1 (
  echo [ERROR] Sborschik zavershilsya s oshibkoy, eksport propuscheno.
  pause
  exit /b 1
)

echo [2/2] Eksport v dist/ ...
python "%~dp0export\export.py"

echo.
echo Gotovo. Staticheskaya versiya: export\dist\index.html
pause
