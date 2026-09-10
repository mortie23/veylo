#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Downloads and unpacks the latest Dataverse solution changes into local Git source files.
.DESCRIPTION
    Exports an unmanaged solution from the active Dataverse instance using PAC CLI
    and unpacks it into the solutions folder as version-controlled XML/JSON files.
.PARAMETER SolutionName
    The unique name of the solution in Dataverse (Default: from .env or 'VeyloCore').
.PARAMETER Folder
    Path to the directory where the unpacked source code is stored (Default: ./solutions/<SolutionName>).
.PARAMETER Environment
    Optional Dataverse environment URL or ID.
.EXAMPLE
    .\solution-sync.ps1
.EXAMPLE
    .\solution-sync.ps1 -SolutionName "VeyloCore"
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$SolutionName = "",

    [Parameter(Position = 1)]
    [string]$Folder = "",

    [Parameter()]
    [string]$Environment = ""
)

$ErrorActionPreference = "Stop"

# Load .env if present
. "$PSScriptRoot/dotenv-helper.ps1"
Import-DotEnv

if ([string]::IsNullOrWhiteSpace($SolutionName)) {
    $envSolution = [Environment]::GetEnvironmentVariable("DATAVERSE_SOLUTION_NAME", "Process")
    $SolutionName = if (-not [string]::IsNullOrWhiteSpace($envSolution)) { $envSolution } else { "VeyloCore" }
}

if ([string]::IsNullOrWhiteSpace($Folder)) {
    $Folder = "$PSScriptRoot/../solutions/$SolutionName"
}

if ([string]::IsNullOrWhiteSpace($Environment)) {
    $Environment = [Environment]::GetEnvironmentVariable("DATAVERSE_ENVIRONMENT_URL", "Process")
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Dataverse Solution - Sync Down Script  " -ForegroundColor Cyan
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

# 3. Resolve destination paths
if ([System.IO.Path]::IsPathRooted($Folder)) {
    $resolvedFolder = [System.IO.Path]::GetFullPath($Folder)
} else {
    $resolvedFolder = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Folder))
}

$parentDir = Split-Path -Path $resolvedFolder -Parent
if (-not (Test-Path $parentDir)) {
    New-Item -ItemType Directory -Path $parentDir -Force | Out-Null
}

$zipPath = Join-Path $parentDir "$SolutionName.zip"

Write-Host "`nSolution Name:   $SolutionName" -ForegroundColor Gray
Write-Host "Target Folder:   $resolvedFolder" -ForegroundColor Gray
Write-Host "Intermediate:    $zipPath" -ForegroundColor Gray

# 4. Export Solution from Dataverse
Write-Host "`n[1/2] Exporting unmanaged solution from Dataverse..." -ForegroundColor Cyan
$stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

pac solution export --name $SolutionName --path $zipPath --managed $false --overwrite
$exportExitCode = $LASTEXITCODE

if ($exportExitCode -ne 0) {
    Write-Error "PAC solution export failed with exit code $exportExitCode."
    exit $exportExitCode
}

# 5. Unpack Solution into Git Source
Write-Host "`n[2/2] Unpacking solution components into source tree..." -ForegroundColor Cyan

pac solution unpack --zipfile $zipPath --folder $resolvedFolder --packagetype Unmanaged --allowDelete $true --allowWrite $true --clobber $true
$unpackExitCode = $LASTEXITCODE

$stopwatch.Stop()

if ($unpackExitCode -eq 0) {
    Write-Host "`n[SUCCESS] Solution '$SolutionName' synchronized into git in $([math]::Round($stopwatch.Elapsed.TotalSeconds, 2))s" -ForegroundColor Green
    Write-Host "Run 'git status' to review updated schema files." -ForegroundColor Yellow
} else {
    Write-Error "PAC solution unpack failed with exit code $unpackExitCode."
    exit $unpackExitCode
}
