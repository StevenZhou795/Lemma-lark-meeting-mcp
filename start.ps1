param(
    [ValidateSet('mcp', 'login')]
    [string]$Mode = 'mcp'
)

$ErrorActionPreference = 'Stop'
$larkOriginalAppId = $env:APP_ID
$larkOriginalAppSecret = $env:APP_SECRET
$larkOriginalUserToken = $env:USER_ACCESS_TOKEN

# Credentials are passed through the environment, never command-line arguments.
if ((-not $env:APP_ID -or -not $env:APP_SECRET) -and (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'credentials.local.clixml'))) {
    try {
        $larkCredential = Import-Clixml -LiteralPath (Join-Path $PSScriptRoot 'credentials.local.clixml') -ErrorAction Stop
        if ($larkCredential -isnot [System.Management.Automation.PSCredential]) {
            throw 'Invalid credential type.'
        }
        $larkPassword = $larkCredential.GetNetworkCredential().Password
        if ([string]::IsNullOrWhiteSpace($larkCredential.UserName) -or [string]::IsNullOrEmpty($larkPassword)) {
            throw 'Empty credential.'
        }
    }
    catch {
        [Console]::Error.WriteLine('Cannot read the local encrypted credentials. The file may be damaged or belong to a different Windows user/computer. No Lark request was made. Run: .\configure.ps1 -Replace, using this same Windows account and PowerShell, then retry login. Do not share the credential file.')
        exit 1
    }
    $env:APP_ID = $larkCredential.UserName
    $env:APP_SECRET = $larkPassword
    $larkPassword = $null
}
if (-not $env:APP_ID -or -not $env:APP_SECRET) {
    [Console]::Error.WriteLine('Run configure.ps1 locally, or set APP_ID and APP_SECRET before starting Lark MCP. Do not send credentials in chat.')
    exit 1
}

$larkPackage = '@larksuiteoapi/lark-mcp@0.5.1'
$larkTools = @(
    'bitable.v1.appTableField.list'
    'bitable.v1.appTableRecord.list'
    'bitable.v1.appTableRecord.search'
    'bitable.v1.appTableRecord.batchGet'
    'bitable.v1.appTableRecord.batchCreate'
    'bitable.v1.appTableRecord.batchUpdate'
    'contact.v3.user.batchGetId'
)

# Prevent a USER_ACCESS_TOKEN inherited from another application overriding OAuth.
Remove-Item -LiteralPath 'Env:USER_ACCESS_TOKEN' -ErrorAction SilentlyContinue
# dotenv in the official CLI reads the cwd. Keep it away from the website's .env.
Push-Location -LiteralPath $PSScriptRoot
try {
    if ($Mode -eq 'login') {
        & npx.cmd --yes $larkPackage login --domain 'https://open.larksuite.com'
    }
    else {
        & npx.cmd --yes $larkPackage mcp --domain 'https://open.larksuite.com' --mode stdio --language zh --token-mode user_access_token --oauth --tools ($larkTools -join ',')
    }
    $larkExitCode = $LASTEXITCODE
}
finally {
    $env:APP_ID = $larkOriginalAppId
    $env:APP_SECRET = $larkOriginalAppSecret
    $env:USER_ACCESS_TOKEN = $larkOriginalUserToken
    Pop-Location
}
exit $larkExitCode
