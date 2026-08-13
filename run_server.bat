@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo carcheck - locheck server (opciyonalno, dlya proverki doma)
echo ============================================================

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] Python ne nayden v PATH. Ustanovite Python 3.10+ s python.org
  echo         i otmette "Add python.exe to PATH" pri ustanovke.
  pause
  exit /b 1
)

if not exist "%~dp0.venv" (
  echo [1/2] Sozdayu virtualnoe okruzhenie .venv ...
  python -m venv "%~dp0.venv"
)

call "%~dp0.venv\Scripts\activate.bat"

echo [2/2] Ustanavlivayu zavisimosti ...
pip install -q -r "%~dp0requirements.txt"

echo.
echo Zapuskayu server. Adresa dostupa budut vyvedeny nizhe.
echo Ne zakryvayte eto okno, poka nuzhen dostup s telefona.
echo.

python "%~dp0server\app.py"

pause
