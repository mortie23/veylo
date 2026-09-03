<#
.SYNOPSIS
    Convenience wrapper to download and unpack Dataverse solution changes.
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

& "$PSScriptRoot/scripts/solution-sync.ps1" -SolutionName $SolutionName -Folder $Folder -Environment $Environment
