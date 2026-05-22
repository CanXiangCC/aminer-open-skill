param(
    [switch]$Status,
    [switch]$Clear,
    [switch]$Force,
    [switch]$ProcessOnly,
    [string]$Token
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$Name = "AMINER_API_KEY"

function Get-HashPrefix {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return ""
    }

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hash = $sha.ComputeHash($bytes)
        $hex = ($hash | ForEach-Object { $_.ToString("x2") }) -join ""
        return $hex.Substring(0, 12).ToUpperInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-KeyRows {
    $rows = @()
    foreach ($scope in @("Process", "User", "Machine")) {
        $value = [Environment]::GetEnvironmentVariable($Name, $scope)
        $rows += [PSCustomObject]@{
            Scope = $scope
            Configured = -not [string]::IsNullOrWhiteSpace($value)
            Length = if ($value) { $value.Length } else { 0 }
            Sha256Prefix = Get-HashPrefix $value
        }
    }
    return $rows
}

function Show-KeyStatus {
    Write-Host ""
    Write-Host "AMiner token status (token value is never printed):"
    Get-KeyRows | Format-Table -AutoSize
}

function Read-TokenSecurely {
    $secure = Read-Host "Paste AMiner token" -AsSecureString
    $ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try {
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    }
    finally {
        if ($ptr -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
        }
    }
}

function Test-TokenShape {
    param([string]$Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        throw "Empty token. Nothing was changed."
    }
    if ($Value -match "\s") {
        throw "Token contains whitespace. Nothing was changed."
    }
    if ($Value.Length -lt 40) {
        Write-Warning "The token is unusually short. Continuing because AMiner token formats may change."
    }
}

function Ask-ExistingKeyAction {
    param([string]$Scope)

    Write-Host "$Name is already configured in $Scope scope."
    Write-Host "Choose an action:"
    Write-Host "  R - Replace token"
    Write-Host "  S - Show status"
    Write-Host "  C - Clear token"
    Write-Host "  Q - Quit"

    while ($true) {
        $choice = (Read-Host "Enter R/S/C/Q").Trim().ToUpperInvariant()
        switch ($choice) {
            "R" { return "replace" }
            "S" { return "status" }
            "C" { return "clear" }
            "Q" { return "quit" }
            default { Write-Host "Please enter R, S, C, or Q." }
        }
    }
}

if ($Status) {
    Show-KeyStatus
    exit 0
}

if ($Clear) {
    if ($ProcessOnly) {
        [Environment]::SetEnvironmentVariable($Name, $null, "Process")
        Write-Host "Cleared $Name from the current process."
    }
    else {
        [Environment]::SetEnvironmentVariable($Name, $null, "User")
        [Environment]::SetEnvironmentVariable($Name, $null, "Process")
        Write-Host "Cleared $Name from User scope and the current process."
    }
    Show-KeyStatus
    exit 0
}

$targetScope = if ($ProcessOnly) { "Process" } else { "User" }
$existing = [Environment]::GetEnvironmentVariable($Name, $targetScope)

if ($existing -and -not $Force) {
    if ($Token) {
        Write-Host "$Name is already configured in $targetScope scope."
        Write-Host "Use -Force to replace it, -Status to inspect scopes, or -Clear to remove it."
        Show-KeyStatus
        exit 0
    }

    $action = Ask-ExistingKeyAction $targetScope
    if ($action -eq "status") {
        Show-KeyStatus
        exit 0
    }
    if ($action -eq "clear") {
        [Environment]::SetEnvironmentVariable($Name, $null, $targetScope)
        if (-not $ProcessOnly) {
            [Environment]::SetEnvironmentVariable($Name, $null, "Process")
        }
        Write-Host "Cleared $Name from $targetScope scope."
        Show-KeyStatus
        exit 0
    }
    if ($action -eq "quit") {
        Write-Host "No changes made."
        Show-KeyStatus
        exit 0
    }
}

if ([string]::IsNullOrWhiteSpace($Token)) {
    $Token = Read-TokenSecurely
}

$Token = $Token.Trim()
Test-TokenShape $Token

[Environment]::SetEnvironmentVariable($Name, $Token, $targetScope)

if (-not $ProcessOnly) {
    [Environment]::SetEnvironmentVariable($Name, $Token, "Process")
}

Write-Host "Configured $Name in $targetScope scope."
if (-not $ProcessOnly) {
    Write-Host "New terminals and future Codex sessions should be able to read it."
    Write-Host "The current process was also updated for immediate use."
}
else {
    Write-Host "This setting only applies to the current process."
}

Show-KeyStatus
