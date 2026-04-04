@echo off
setlocal EnableExtensions
cd /d "%~dp0"

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

if not exist "backend\" mkdir "backend"
cd /d "%~dp0backend"
if not exist "manage.py" (
  echo Initializing Django project core...
  django-admin startproject core .
  if errorlevel 1 (
    echo django-admin startproject failed.
    exit /b 1
  )
) else (
  echo backend\manage.py already exists, skipping startproject.
)

echo.
echo Done. Next: activate venv, cd backend, run: python manage.py runserver
pause
