@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if not exist "backend\manage.py" (
  echo Missing backend\manage.py, please run this script from project root.
  exit /b 1
)

if not exist "venv\" (
  echo Creating virtual environment...
  python -m venv venv
  if errorlevel 1 (
    echo Failed to create venv. Ensure Python 3.8+ is on PATH.
    exit /b 1
  )
)

call "%~dp0venv\Scripts\activate.bat"
if errorlevel 1 (
  echo Failed to activate venv.
  exit /b 1
)

python -m pip install --upgrade pip
pip install -r "%~dp0requirements.txt"
if errorlevel 1 (
  echo pip install failed.
  exit /b 1
)

cd /d "%~dp0backend"
python manage.py migrate
if errorlevel 1 (
  echo migrate failed.
  exit /b 1
)

echo.
echo Done. Next: cd backend ^&^& python manage.py runserver
pause
