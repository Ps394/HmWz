$ErrorActionPreference = "Stop"
$projectDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
Set-Location $projectDirectory

$venvPython = Join-Path $projectDirectory "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found. Run create_venv.ps1 first."
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip."
}
& $venvPython -m pip install -r (Join-Path $projectDirectory "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install dependencies from requirements.txt."
}

Write-Host "Dependencies installed successfully."
