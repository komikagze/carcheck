@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo carcheck - sborschik (opciyonalnyy lokalnyy scenariy).
echo Osnovnoy scenariy teper - GitHub Actions (.github/workflows/weekly.yml),
echo etot bat nuzhen tolko dlya lokalnogo zapuska/otladki na svoem PC.
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python ne nayden v PATH. Ustanovite Python 3.10+ s python.org
  pause
  exit /b 1
)

if not exist "%~dp0.venv" (
  echo Sozdayu virtualnoe okruzhenie .venv ...
  python -m venv "%~dp0.venv"
)

call "%~dp0.venv\Scripts\activate.bat"
pip install -q -r "%~dp0requirements.txt"

echo.
echo Zapuskayu sborschik. Eto mozhet zanyat neskolko minut
echo (skachivanie CSV do 150-170 MB kazhdyy).
echo.

python "%~dp0collector\collector.py"

echo.
echo Gotovo. Log: collector\logs\collector.log
pause
