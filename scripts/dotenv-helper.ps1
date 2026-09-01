function Import-DotEnv {
    [CmdletBinding()]
    param(
        [Parameter()]
        [string]$Path = "$PSScriptRoot/../.env"
    )

    $resolved = [System.IO.Path]::GetFullPath($Path)
    if (Test-Path $resolved) {
        Get-Content $resolved | ForEach-Object {
            $line = $_.Trim()
            if (-not [string]::IsNullOrWhiteSpace($line) -and -not $line.StartsWith("#")) {
                $parts = $line -split "=", 2
                if ($parts.Length -eq 2) {
                    $key = $parts[0].Trim()
                    $val = $parts[1].Trim().Trim('"').Trim("'")
                    if (-not [string]::IsNullOrWhiteSpace($key) -and -not [Environment]::GetEnvironmentVariable($key, "Process")) {
                        [Environment]::SetEnvironmentVariable($key, $val, "Process")
                    }
                }
            }
        }
    }
}
