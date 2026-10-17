$ErrorActionPreference = "Stop"
$projectDirectory = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

$venvPython = Join-Path $projectDirectory "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Virtual environment not found. Run create_venv.ps1 first."
}

$taskName = "HmWzBot"
$entryPoint = Join-Path $projectDirectory "src\bot.py"
$action = New-ScheduledTaskAction -Execute $venvPython -Argument "`"$entryPoint`"" -WorkingDirectory $projectDirectory
$trigger = New-ScheduledTaskTrigger -AtLogOn -User ([Security.Principal.WindowsIdentity]::GetCurrent().Name)
$principal = New-ScheduledTaskPrincipal -UserId ([Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew

$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($null -ne $existingTask -and $existingTask.State -eq "Running") {
    Stop-ScheduledTask -TaskName $taskName
}

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Description "Runs the HmWz Discord bot when this user logs in." -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Registered and started scheduled task '$taskName'. It will start when this user logs in." -ForegroundColor Green
Write-Host "The task runs in this user's context so it can read the token from HKCU:\Software\HsBot."
