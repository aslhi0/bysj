$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $repoRoot "venv\Scripts\python.exe"
$backend = Join-Path $repoRoot "backend"
$frontend = Join-Path $repoRoot "frontend"

if (-not (Test-Path $python)) {
  throw "Python virtualenv not found: $python"
}

function Invoke-Step {
  param(
    [string]$Name,
    [string]$WorkingDirectory,
    [string[]]$Command
  )

  Write-Host ""
  Write-Host "==> $Name" -ForegroundColor Cyan
  Push-Location $WorkingDirectory
  try {
    & $Command[0] @($Command | Select-Object -Skip 1)
    if ($LASTEXITCODE -ne 0) {
      throw "$Name failed with exit code $LASTEXITCODE"
    }
  } finally {
    Pop-Location
  }
}

Invoke-Step "Django system check" $backend @($python, "manage.py", "check")
Invoke-Step "Django migration dry run" $backend @($python, "manage.py", "makemigrations", "--check", "--dry-run")
Invoke-Step "Backend pytest" $backend @($python, "-m", "pytest", "-q")
Invoke-Step "Frontend unit tests" $frontend @("npm", "test")
Invoke-Step "Frontend lint" $frontend @("npm", "run", "lint")
Invoke-Step "Frontend production build" $frontend @("npm", "run", "build")

Write-Host ""
Write-Host "Submission checks completed successfully." -ForegroundColor Green
