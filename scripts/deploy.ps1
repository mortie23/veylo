<#
.SYNOPSIS
    Deploys (uploads) local Power Pages website changes to Dataverse using PAC CLI.
.DESCRIPTION
    Uploads local website files to Dataverse using the Enhanced Data Model (-mv 2).
    Configuration parameters can be supplied via arguments or loaded from .env.
.PARAMETER Path
    Path to the website folder containing .portalconfig (Default: from .env or ./src/orgfile-manager).
.PARAMETER ModelVersion
    Power Pages data model version (Default: 2 for Enhanced Data Model).
.PARAMETER Environment
    Optional Dataverse environment URL or ID to target before uploading.
.PARAMETER WhatIf
    Simulate the upload action without executing pac powerpages upload.
.EXAMPLE
    .\deploy.ps1
.EXAMPLE
    .\deploy.ps1 -WhatIf
.EXAMPLE
    .\deploy.ps1 -Environment "https://org123.crm.dynamics.com"
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Position = 0)]
    [string]$Path = "",

    [Parameter()]
    [int]$ModelVersion = 0,

    [Parameter()]
    [string]$Environment = ""
)

$ErrorActionPreference = "Stop"

# Load .env if present
. "$PSScriptRoot/dotenv-helper.ps1"
Import-DotEnv

# Resolve parameters with fallback hierarchy: CLI argument -> .env -> defaults
if ([string]::IsNullOrWhiteSpace($Path)) {
    $envPath = [Environment]::GetEnvironmentVariable("POWERPAGES_SITE_PATH", "Process")
    $Path = if (-not [string]::IsNullOrWhiteSpace($envPath)) { $envPath } else { "$PSScriptRoot/../src/orgfile-manager" }
}

if ($ModelVersion -le 0) {
    $envMv = [Environment]::GetEnvironmentVariable("POWERPAGES_MODEL_VERSION", "Process")
    $ModelVersion = if (-not [string]::IsNullOrWhiteSpace($envMv)) { [int]$envMv } else { 2 }
}

if ([string]::IsNullOrWhiteSpace($Environment)) {
    $Environment = [Environment]::GetEnvironmentVariable("DATAVERSE_ENVIRONMENT_URL", "Process")
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " Power Pages - Upload & Deploy Script   " -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 1. Verify PAC CLI
$pacCmd = Get-Command "pac" -ErrorAction SilentlyContinue
if (-not $pacCmd) {
    Write-Error "Microsoft PowerPlatform CLI (pac) is not installed or not found in PATH."
    exit 1
}

# 2. Resolve target path
if ([System.IO.Path]::IsPathRooted($Path)) {
    $resolvedPath = [System.IO.Path]::GetFullPath($Path)
} else {
    $resolvedPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $Path))
}
if (-not (Test-Path $resolvedPath)) {
    Write-Error "Target website directory does not exist: $resolvedPath"
    exit 1
}

$portalConfigPath = Join-Path $resolvedPath ".portalconfig"
if (-not (Test-Path $portalConfigPath)) {
    Write-Warning "No .portalconfig directory found in '$resolvedPath'. Ensure this is a valid downloaded Power Pages website directory."
}

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

Write-Host "`nTarget Path:        $resolvedPath" -ForegroundColor Gray
Write-Host "Data Model Version: $ModelVersion" -ForegroundColor Gray

# 5. Execute Upload
$uploadArgs = @("powerpages", "upload", "--path", $resolvedPath, "-mv", "$ModelVersion")

if ($PSCmdlet.ShouldProcess($resolvedPath, "Upload Power Pages site to Dataverse via PAC CLI")) {
    Write-Host "`nUploading website to Dataverse..." -ForegroundColor Cyan
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    
    & pac $uploadArgs
    $exitCode = $LASTEXITCODE

    $stopwatch.Stop()

    if ($exitCode -eq 0) {
        Write-Host "`n[SUCCESS] Power Pages deployment completed in $([math]::Round($stopwatch.Elapsed.TotalSeconds, 2))s" -ForegroundColor Green
        Write-Host "`nNote: If changes are not immediately visible on your live site, clear the portal cache:" -ForegroundColor Yellow
        Write-Host "  1. In Power Pages Design Studio, click 'Preview' -> 'Sync' / 'Browse website'" -ForegroundColor Gray
        Write-Host "  2. Or navigate to: https://<your-portal-url>/_services/about (while logged in as Admin) and click 'Clear Cache'" -ForegroundColor Gray
    } else {
        Write-Error "PAC powerpages upload failed with exit code $exitCode."
        exit $exitCode
    }
} else {
    Write-Host "`n[WHAT-IF] Would run: pac $($uploadArgs -join ' ')" -ForegroundColor Magenta
}
