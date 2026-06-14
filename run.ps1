$ErrorActionPreference = 'Stop'

$RootDir = $PSScriptRoot
$BackendDir = Join-Path $RootDir 'backend'
$PythonExe = Join-Path $RootDir '.venv\Scripts\python.exe'
$RequiredEnv = @('ADMIN_PASSWORD', 'ADMIN_COOKIE_SECRET')
$FallbackEnv = @{
  ADMIN_PASSWORD = 'local-admin-password'
  ADMIN_COOKIE_SECRET = 'local-admin-cookie-secret'
}

if (-not (Test-Path -LiteralPath $PythonExe)) {
  throw "Missing virtual environment Python at $PythonExe"
}

foreach ($Name in $RequiredEnv) {
  if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($Name))) {
    Set-Item -Path ("Env:" + $Name) -Value $FallbackEnv[$Name]
  }
}

Set-Location -LiteralPath $BackendDir
& $PythonExe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
