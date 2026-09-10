#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Convenience wrapper to sync down Power Pages changes from Dataverse.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Path = "src",

    [Parameter(Position = 1)]
    [string]$WebsiteId = "",

    [Parameter()]
    [int]$ModelVersion = 0,

    [Parameter()]
    [string]$Environment = ""
)

& "$PSScriptRoot/scripts/sync-down.ps1" -Path $Path -WebsiteId $WebsiteId -ModelVersion $ModelVersion -Environment $Environment
