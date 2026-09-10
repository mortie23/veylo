#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Convenience wrapper to deploy Power Pages changes.
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

& "$PSScriptRoot/scripts/deploy.ps1" -Path $Path -ModelVersion $ModelVersion -Environment $Environment -WhatIf:$WhatIfPreference
