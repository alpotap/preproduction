[CmdletBinding()]
param(
    [ValidateSet("Install", "Uninstall", "Start", "Stop", "Restart", "Status")]
    [string]$Action = "Install",

    [string]$Host = "127.0.0.1",

    [ValidateRange(1, 65535)]
    [int]$Port = 8000,

    [switch]$InstallRequirements,

    [switch]$OpenFirewall,

    [switch]$EnableAccessLog
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSCommandPath
$ServiceScript = Join-Path $RepoRoot "windows_web_service.py"
$OutputDir = Join-Path $RepoRoot "output"
$ConfigPath = Join-Path $OutputDir "web_service_config.json"
$ServiceName = "DocumentCorrectionToolkitWeb"
$ServiceUrl = "http://{0}:{1}" -f $Host, $Port

function Test-IsAdmin {
    $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-PythonLauncher {
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        return @($pyCommand.Source, "-3")
    }

    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        return @($pythonCommand.Source)
    }

    throw "Python launcher not found. Install Python 3 and ensure 'py' or 'python' is on PATH."
}

function Invoke-Python {
    param(
        [string[]]$Arguments
    )

    $launcher = Get-PythonLauncher
    $command = $launcher[0]
    $prefixArgs = @()
    if ($launcher.Length -gt 1) {
        $prefixArgs = $launcher[1..($launcher.Length - 1)]
    }

    & $command @prefixArgs @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python command failed with exit code $LASTEXITCODE"
    }
}

function Write-ServiceConfig {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
    $config = [ordered]@{
        host = $Host
        port = $Port
        access_log = [bool]$EnableAccessLog
    }
    $config | ConvertTo-Json | Set-Content -Path $ConfigPath -Encoding UTF8
}

function Configure-ServiceRecovery {
    sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
    sc.exe failureflag $ServiceName 1 | Out-Null
    sc.exe description $ServiceName "Hosts the Document Correction Toolkit web UI in the background." | Out-Null
}

function Configure-FirewallRule {
    if (-not $OpenFirewall) {
        return
    }
    if ($Host -eq "127.0.0.1" -or $Host -eq "localhost") {
        Write-Host "Skipping firewall rule because host is loopback only."
        return
    }

    $ruleName = "Document Correction Toolkit Web $Port"
    $existingRule = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
    if (-not $existingRule) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port | Out-Null
        Write-Host "Created firewall rule '$ruleName'."
    }
}

if ($Action -ne "Status" -and -not (Test-IsAdmin)) {
    throw "Run this script from an elevated PowerShell session."
}

Push-Location $RepoRoot
try {
    if ($InstallRequirements) {
        Write-Host "Installing Python dependencies from requirements.txt..."
        Invoke-Python -Arguments @("-m", "pip", "install", "-r", "requirements.txt")
    }

    $existingService = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue

    switch ($Action) {
        "Install" {
            Write-ServiceConfig

            if (-not $existingService) {
                Write-Host "Installing Windows service '$ServiceName'..."
                Invoke-Python -Arguments @($ServiceScript, "--startup", "auto", "install")
                Configure-ServiceRecovery
            } else {
                Write-Host "Service already exists. Updating configuration only."
            }

            Configure-FirewallRule

            if ((Get-Service -Name $ServiceName).Status -eq "Running") {
                Restart-Service -Name $ServiceName -Force
            } else {
                Start-Service -Name $ServiceName
            }

            Write-Host "Service installed and running at $ServiceUrl"
            Write-Host "Config file: $ConfigPath"
            Write-Host "Logs: $(Join-Path $OutputDir 'web_service.log')"
        }
        "Uninstall" {
            if (-not $existingService) {
                Write-Host "Service '$ServiceName' is not installed."
                return
            }

            if ($existingService.Status -eq "Running") {
                Stop-Service -Name $ServiceName -Force
            }

            Write-Host "Removing Windows service '$ServiceName'..."
            Invoke-Python -Arguments @($ServiceScript, "remove")
            Write-Host "Service removed."
        }
        "Start" {
            if (-not $existingService) {
                throw "Service '$ServiceName' is not installed."
            }
            Start-Service -Name $ServiceName
            Write-Host "Service started at $ServiceUrl"
        }
        "Stop" {
            if (-not $existingService) {
                throw "Service '$ServiceName' is not installed."
            }
            Stop-Service -Name $ServiceName -Force
            Write-Host "Service stopped."
        }
        "Restart" {
            if (-not $existingService) {
                throw "Service '$ServiceName' is not installed."
            }
            Write-ServiceConfig
            Restart-Service -Name $ServiceName -Force
            Write-Host "Service restarted at $ServiceUrl"
        }
        "Status" {
            if (-not $existingService) {
                Write-Host "Service '$ServiceName' is not installed."
                return
            }

            $service = Get-Service -Name $ServiceName
            Write-Host "Name:    $($service.Name)"
            Write-Host "Status:  $($service.Status)"
            Write-Host "Config:  $ConfigPath"
            if (Test-Path $ConfigPath) {
                Write-Host "URL:     $ServiceUrl"
            }
        }
    }
}
finally {
    Pop-Location
}