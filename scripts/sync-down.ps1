#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Downloads latest changes from Power Pages site into local repository.
.DESCRIPTION
    Downloads the Power Pages website records using PAC CLI with the Enhanced Data Model (-mv 2).
    Configuration parameters can be supplied via arguments or loaded from .env.
.PARAMETER Path
    Destination root directory where the website directory will be placed (Default: ./src).
.PARAMETER WebsiteId
    The GUID of the Power Pages website (Default: from .env or specified).
.PARAMETER ModelVersion
    Power Pages data model version (Default: 2 for Enhanced Data Model).
.PARAMETER Environment
    Optional Dataverse environment URL or ID.
.EXAMPLE
    .\sync-down.ps1
.EXAMPLE
    .\sync-down.ps1 -WebsiteId "00000000-0000-0000-0000-000000000000"
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Path = "$PSScriptRoot/../src",

    [Parameter(Position = 1)]
    [string]$WebsiteId = "",

    [Parameter()]
    [int]$ModelVersion = 0,

    [Parameter()]
    [string]$Environment = ""
)

$ErrorActionPreference = "Stop"

# Load .env if present
. "$PSScriptRoot/dotenv-helper.ps1"
Import-DotEnv

if ([string]::IsNullOrWhiteSpace($WebsiteId)) {
    $WebsiteId = [Environment]::GetEnvironmentVariable("POWERPAGES_WEBSITE_ID", "Process")
}

if ($ModelVersion -le 0) {
    $envMv = [Environment]::GetEnvironmentVariable("POWERPAGES_MODEL_VERSION", "Process")
    $ModelVersion = if (-not [string]::IsNullOrWhiteSpace($envMv)) { [int]$envMv } else { 2 }
}

if ([string]::IsNullOrWhiteSpace($Environment)) {
    $Environment = [Environment]::GetEnvironmentVariable("DATAVERSE_ENVIRONMENT_URL", "Process")
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Power Pages - Sync Down Script         " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Verify PAC CLI
$pacCmd = Get-Command "pac" -ErrorAction SilentlyContinue
if (-not $pacCmd) {
    Write-Error "Microsoft PowerPlatform CLI (pac) is not installed or not found in PATH."
    exit 1
}

# 2. Optional Environment / Profile Switch
if (-not [string]::IsNullOrWhiteSpace($Environment)) {
    if ($Environment -match '^\d+$') {
        Write-Host "`nSelecting PAC auth profile index: $Environment" -ForegroundColor Yellow
        pac auth select --index $Environment
    } elseif ($Environment.Length -le 30 -and -not ($Environment.StartsWith("http", [System.StringComparison]::OrdinalIgnoreCase))) {
        Write-Host "`nSelecting PAC auth profile name: $Environment" -ForegroundColor Yellow
        pac auth select --name $Environment
    }
}

# 3. Check Website ID
if ([string]::IsNullOrWhiteSpace($WebsiteId)) {
    Write-Host "`nNo WebsiteId provided or found in .env. Listing available websites in active environment..." -ForegroundColor Yellow
    pac powerpages list
    Write-Error "Please specify -WebsiteId <GUID> or define POWERPAGES_WEBSITE_ID in your .env file."
    exit 1
}

# 4. Resolve target path
if ([System.IO.Path]::IsPathRooted($Path)) {
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
} else {
    $resolvedPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}
if (-not (Test-Path $resolvedPath)) {
    New-Item -ItemType Directory -Path $resolvedPath -Force | Out-Null
}

Write-Host "`nTarget Download Path: $resolvedPath" -ForegroundColor Gray
Write-Host "Website ID:           $WebsiteId" -ForegroundColor Gray
Write-Host "Data Model Version:   $ModelVersion" -ForegroundColor Gray

Write-Host "`nDownloading website from Dataverse..." -ForegroundColor Cyan
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

pac powerpages download --path $resolvedPath --webSiteId $WebsiteId -mv $ModelVersion -o true
$exitCode = $LASTEXITCODE

# PAC CLI strictly uses the website's adx_name (Veylo) for the folder name.
# Automatically move it to orgfile-manager to match the repository structure.
if ($exitCode -eq 0 -and (Test-Path "$resolvedPath/veylo")) {
    Write-Host "`nMigrating files from 'veylo' folder to 'orgfile-manager'..." -ForegroundColor Gray
    Copy-Item -Path "$resolvedPath/veylo\*" -Destination "$resolvedPath/orgfile-manager" -Recurse -Force
    Remove-Item -Path "$resolvedPath/veylo" -Recurse -Force
}

$stopwatch.Stop()

if ($exitCode -eq 0) {
    Write-Host "`n[SUCCESS] Power Pages site downloaded in $([math]::Round($stopwatch.Elapsed.TotalSeconds, 2))s" -ForegroundColor Green
} else {
    Write-Error "PAC powerpages download failed with exit code $exitCode."
    exit $exitCode
}
