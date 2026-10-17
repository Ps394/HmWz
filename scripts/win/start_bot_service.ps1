$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName "HmWzBot"
if ($task.State -eq "Running") {
    Write-Host "Scheduled task 'HmWzBot' is already running."
} else {
    Start-ScheduledTask -TaskName "HmWzBot"
    Write-Host "Started scheduled task 'HmWzBot'."
}
