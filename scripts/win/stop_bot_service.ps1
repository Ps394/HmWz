param([string]$TaskName = "")

$ErrorActionPreference = "Stop"
$scriptDirectory = $PSScriptRoot
. (Join-Path $scriptDirectory "service_config.ps1")
$taskName = Resolve-HmwzTaskName -Name $TaskName
$task = Get-ScheduledTask -TaskName $taskName
if ($task.State -eq "Running") {
    Stop-ScheduledTask -TaskName $taskName
    Write-Host "Stopped scheduled task '$taskName'. It remains registered to run at the next logon."
} else {
    Write-Host "Scheduled task '$taskName' is not running."
}
