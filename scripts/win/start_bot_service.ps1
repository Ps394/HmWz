param([string]$TaskName = "")

$ErrorActionPreference = "Stop"
$scriptDirectory = $PSScriptRoot
. (Join-Path $scriptDirectory "service_config.ps1")
$taskName = Resolve-HmwzTaskName -Name $TaskName
$task = Get-ScheduledTask -TaskName $taskName
if ($task.State -eq "Running") {
    Write-Host "Scheduled task '$taskName' is already running."
} else {
    Start-ScheduledTask -TaskName $taskName
    Write-Host "Started scheduled task '$taskName'."
}
