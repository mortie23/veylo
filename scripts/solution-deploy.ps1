<#
.SYNOPSIS
    Packages and deploys (imports) local Dataverse solution changes to a target environment.
.DESCRIPTION
    Packs the local XML/JSON solution source files into a ZIP package and imports it
    into the active Dataverse instance using PAC CLI.
.PARAMETER SolutionName
    The unique name of the solution (Default: from .env or 'VeyloCore').
.PARAMETER Folder
    Path to the directory containing unpacked solution source code (Default: ./solutions/<SolutionName>).
.PARAMETER Environment
    Optional Dataverse environment URL or ID to target before importing.
.PARAMETER WhatIf
    Simulates packing and importing without executing.
.EXAMPLE
    .\solution-deploy.ps1
.EXAMPLE
    .\solution-deploy.ps1 -WhatIf
.EXAMPLE
    .\solution-deploy.ps1 -Environment "https://org123.crm.dynamics.com"
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Position = 0)]
    [string]$SolutionName = "",

    [Parameter(Position = 1)]
    [string]$Folder = "",

    [Parameter()]
    [string]$Environment = "",

    [Parameter()]
    [switch]$SkipPublish = $false
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
Write-Host " Dataverse Solution - Deploy Script     " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Verify PAC CLI
$pacCmd = Get-Command "pac" -ErrorAction SilentlyContinue
if (-not $pacCmd) {
    Write-Error "Microsoft PowerPlatform CLI (pac) is not installed or not found in PATH."
    exit 1
}

# 2. Resolve source folder
if ([System.IO.Path]::IsPathRooted($Folder)) {
    $resolvedFolder = [System.IO.Path]::GetFullPath($Folder)
} else {
    $resolvedFolder = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Folder))
}

if (-not (Test-Path $resolvedFolder)) {
    Write-Error "Target solution directory does not exist: $resolvedFolder"
    exit 1
}

$parentDir = Split-Path -Path $resolvedFolder -Parent
$zipPath = Join-Path $parentDir "$SolutionName.zip"

# 3. Optional Environment / Profile Switch
if (-not [string]::IsNullOrWhiteSpace($Environment)) {
    if ($Environment -match '^\d+$') {
        Write-Host "`nSelecting PAC auth profile index: $Environment" -ForegroundColor Yellow
        pac auth select --index $Environment
    } elseif ($Environment.Length -le 30 -and -not ($Environment.StartsWith("http", [System.StringComparison]::OrdinalIgnoreCase))) {
        Write-Host "`nSelecting PAC auth profile name: $Environment" -ForegroundColor Yellow
        pac auth select --name $Environment
    }
}

# 4. Show active context
Write-Host "`nActive Dataverse Context:" -ForegroundColor Yellow
pac auth list

Write-Host "`nSolution Name:   $SolutionName" -ForegroundColor Gray
Write-Host "Source Folder:   $resolvedFolder" -ForegroundColor Gray
Write-Host "Package Output:  $zipPath" -ForegroundColor Gray

# 5. Execute Pack & Import
if ($PSCmdlet.ShouldProcess($zipPath, "Pack and import Dataverse solution to active environment")) {
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()

    Write-Host "`n[1/2] Packing solution files into ZIP package..." -ForegroundColor Cyan
    pac solution pack --zipfile $zipPath --folder $resolvedFolder --packagetype Unmanaged --clobber $true
    $packExitCode = $LASTEXITCODE

    if ($packExitCode -ne 0) {
        Write-Error "PAC solution pack failed with exit code $packExitCode."
        exit $packExitCode
    }

    Write-Host "`n[2/2] Importing solution into Dataverse..." -ForegroundColor Cyan
    $importArgs = @("solution", "import", "--path", $zipPath, "--force-overwrite")
    if (-not $SkipPublish) {
        $importArgs += "--publish-changes"
    }

    & pac $importArgs
    $importExitCode = $LASTEXITCODE

    $stopwatch.Stop()

    if ($importExitCode -eq 0) {
        Write-Host "`n[SUCCESS] Solution '$SolutionName' deployed to Dataverse in $([math]::Round($stopwatch.Elapsed.TotalSeconds, 2))s" -ForegroundColor Green
    } else {
        Write-Error "PAC solution import failed with exit code $importExitCode."
        exit $importExitCode
    }
} else {
    Write-Host "`n[WHAT-IF] Would run:" -ForegroundColor Magenta
    Write-Host "  pac solution pack --zipfile `"$zipPath`" --folder `"$resolvedFolder`" --packagetype Unmanaged --clobber" -ForegroundColor Gray
    Write-Host "  pac solution import --path `"$zipPath`" --force-overwrite --publish-changes" -ForegroundColor Gray
}
