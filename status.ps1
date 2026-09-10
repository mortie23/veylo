#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Convenience wrapper to check PAC environment and website status.
#>
[CmdletBinding()]
param()

& "$PSScriptRoot/scripts/status.ps1"
