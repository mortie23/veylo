#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Displays current Power Platform CLI authentication and website status.
.DESCRIPTION
    Checks active PAC authentication profiles and lists available Power Pages sites.
#>

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Power Platform CLI - Environment Status" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Check PAC CLI installation
$pacCmd = Get-Command "pac" -ErrorAction SilentlyContinue
if (-not $pacCmd) {
    Write-Error "Microsoft PowerPlatform CLI (pac) is not installed or not found in PATH.`nInstall it via: winget install Microsoft.PowerPlatformCLI or dotnet tool install --global Microsoft.PowerApps.CLI.Tool"
    exit 1
}

Write-Host "`n[1/2] Active Authentication Profiles:" -ForegroundColor Yellow
pac auth list

Write-Host "`n[2/2] Power Pages Websites in Active Environment:" -ForegroundColor Yellow
pac powerpages list

Write-Host "`nStatus check complete." -ForegroundColor Green
