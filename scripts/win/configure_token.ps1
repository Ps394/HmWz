$ErrorActionPreference = "Stop"

$response = Read-Host "Configure a bot token now? (y/N)"
if ($response -notin @("y", "Y")) {
    Write-Host "Skipping bot-token configuration."
    return
}

$secureToken = Read-Host "Discord bot token" -AsSecureString
$tokenPointer = [IntPtr]::Zero
try {
    $tokenPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureToken)
    $plainToken = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($tokenPointer)
    if ([string]::IsNullOrWhiteSpace($plainToken)) {
        Write-Host "No token entered; skipping token configuration."
        return
    }

    $registryPath = "HKCU:\Software\HsBot"
    if (-not (Test-Path $registryPath)) {
        New-Item -Path $registryPath -Force | Out-Null
    }
    New-ItemProperty -Path $registryPath -Name "WZ_BOT_TOKEN" -Value $plainToken -PropertyType String -Force | Out-Null
    Write-Host "Bot token stored in HKEY_CURRENT_USER\Software\HsBot." -ForegroundColor Green
} finally {
    if ($tokenPointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($tokenPointer)
    }
    if ($null -ne $secureToken) {
        $secureToken.Dispose()
    }
    Remove-Variable plainToken -ErrorAction SilentlyContinue
}
