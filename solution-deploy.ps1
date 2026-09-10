#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Convenience wrapper to pack and deploy Dataverse solution changes.
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

& "$PSScriptRoot/scripts/solution-deploy.ps1" -SolutionName $SolutionName -Folder $Folder -Environment $Environment -SkipPublish:$SkipPublish -WhatIf:$WhatIfPreference
