$ErrorActionPreference = "Stop"
$task = Get-ScheduledTask -TaskName "HmWzBot"
if ($task.State -eq "Running") {
    Stop-ScheduledTask -TaskName "HmWzBot"
    Write-Host "Stopped scheduled task 'HmWzBot'. It remains registered to run at the next logon."
} else {
    Write-Host "Scheduled task 'HmWzBot' is not running."
}
