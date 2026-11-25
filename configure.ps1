param([switch]$Replace)

$ErrorActionPreference = 'Stop'

# Run by the user locally. Export-Clixml uses Windows DPAPI for SecureString values.
$larkCredentialPath = Join-Path $PSScriptRoot 'credentials.local.clixml'
if ((Test-Path -LiteralPath $larkCredentialPath) -and -not $Replace) {
    throw 'Credentials already exist. To save new credentials and keep a backup of the old file, run: .\configure.ps1 -Replace'
}
$larkAppId = Read-Host 'Lark App ID (enter locally; do not send it in chat)'
if ([string]::IsNullOrWhiteSpace($larkAppId)) {
    throw 'App ID cannot be empty.'
}
$larkAppSecret = Read-Host 'Lark App Secret (hidden input)' -AsSecureString
if ($larkAppSecret.Length -eq 0) {
    throw 'App Secret cannot be empty.'
}
$larkCredential = [System.Management.Automation.PSCredential]::new($larkAppId.Trim(), $larkAppSecret)
$larkFileSuffix = [Guid]::NewGuid().ToString('N')
$larkTemporaryPath = $larkCredentialPath + '.' + $larkFileSuffix + '.new'
try {
    $larkCredential | Export-Clixml -LiteralPath $larkTemporaryPath -Encoding UTF8
    # User-run setup checks the new file before replacing the existing configuration.
    $larkSavedCredential = Import-Clixml -LiteralPath $larkTemporaryPath -ErrorAction Stop
    if ($larkSavedCredential -isnot [System.Management.Automation.PSCredential] -or
        $larkSavedCredential.UserName -ne $larkCredential.UserName -or
        $larkSavedCredential.Password.Length -ne $larkAppSecret.Length) {
        throw 'The new credential file could not be read correctly.'
    }
    if (Test-Path -LiteralPath $larkCredentialPath) {
        Copy-Item -LiteralPath $larkCredentialPath -Destination ($larkCredentialPath + '.' + $larkFileSuffix + '.bak') -ErrorAction Stop
    }
    Move-Item -LiteralPath $larkTemporaryPath -Destination $larkCredentialPath -Force -ErrorAction Stop
}
catch {
    throw 'Could not save the local encrypted credentials. Existing credentials were not deliberately removed. Use the same Windows account and PowerShell for setup and login. Do not share credential files.'
}
Write-Host 'Saved for this Windows user on this computer. No network request or Lark write was made.'
Write-Host 'Next: .\start.ps1 -Mode login'
