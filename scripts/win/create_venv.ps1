$ErrorActionPreference = "Stop"
$projectDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $projectDirectory

$pythonLauncher = Get-Command py -ErrorAction SilentlyContinue
if ($null -eq $pythonLauncher) {
    throw "Python Launcher (py) was not found. Install Python 3.12 or newer and add the launcher to PATH."
}

$pythonVersion = & py -3 -c "import sys; print('Python {}.{}'.format(*sys.version_info[:2])); raise SystemExit(sys.version_info < (3, 12))" 2>&1
if ($LASTEXITCODE -ne 0) {
    throw "Python 3.12 or newer is required. $pythonVersion"
}
Write-Host "Using $pythonVersion"

if (Test-Path (Join-Path $projectDirectory "venv")) {
    Write-Host "Virtual environment already exists; skipping creation."
} else {
    & py -3 -m venv venv
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create the virtual environment."
    }
}

$venvPython = Join-Path $projectDirectory "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment Python was not created at $venvPython."
}

Write-Host "Virtual environment is ready at $(Join-Path $projectDirectory 'venv')."
