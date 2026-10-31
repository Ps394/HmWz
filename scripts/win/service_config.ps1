$script:HmwzDefaultTaskName = "HmWzBot"

function Get-HmwzTaskNameConfigPath {
    if ([string]::IsNullOrWhiteSpace($env:APPDATA)) {
        throw "APPDATA must be set to store the scheduled task name."
    }

    Join-Path (Join-Path $env:APPDATA "HmWzBot") "task_name"
}

function Resolve-HmwzTaskName {
    param([AllowEmptyString()][string]$Name = "")

    if ([string]::IsNullOrWhiteSpace($Name)) {
        $Name = $env:HMWZ_SERVICE_NAME
    }
    if ([string]::IsNullOrWhiteSpace($Name)) {
        $configPath = Get-HmwzTaskNameConfigPath
        if (Test-Path $configPath) {
            $Name = (Get-Content -Path $configPath -Raw).Trim()
        }
    }
    if ([string]::IsNullOrWhiteSpace($Name)) {
        $Name = $script:HmwzDefaultTaskName
    }

    $Name = $Name.Trim()
    if ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9_. -]*$') {
        throw "Invalid scheduled task name '$Name'. Use letters, numbers, spaces, dots, underscores, or hyphens."
    }
    $Name
}

function Save-HmwzTaskName {
    param([Parameter(Mandatory)][string]$Name)

    $configPath = Get-HmwzTaskNameConfigPath
    $configDirectory = Split-Path -Parent $configPath
    New-Item -ItemType Directory -Path $configDirectory -Force | Out-Null
    Set-Content -Path $configPath -Value $Name -Encoding ASCII
}
