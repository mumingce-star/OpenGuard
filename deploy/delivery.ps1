# 默认只校验配置。Start/Stop/Build 必须由操作者明确选择。
[CmdletBinding()]
param(
    [ValidateSet('Prepare', 'Build', 'Start', 'Status', 'Stop')]
    [string]$Action = 'Prepare',
    [switch]$EnableP2Write
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$project = 'openguard-delivery-20261030'
$variables = @('OPENGUARD_WEB_PORT', 'OPENGUARD_ENABLE_ASSESSMENTS', 'OPENGUARD_ENABLE_P2',
    'OPENGUARD_P2_READONLY', 'OPENGUARD_P2_DATA_SCOPE', 'OPENGUARD_ENABLE_AI',
    'OPENGUARD_OLLAMA_DOCKER_HOST', 'OPENGUARD_ENABLE_PUBLIC_GIT', 'OPENGUARD_ENABLE_PROFILE_METADATA')
$prior = @{}
try {
    # 防止当前终端继承 Owner 配置覆盖本次 TEST_ONLY 配置。
    foreach ($name in $variables) {
        $prior[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
        Remove-Item -LiteralPath ('Env:' + $name) -ErrorAction SilentlyContinue
    }
    if ($EnableP2Write) {
        $env:OPENGUARD_ENABLE_P2 = '1'
        $env:OPENGUARD_P2_READONLY = '0'
    }
    $compose = @('compose', '-p', $project, '--env-file', (Join-Path $PSScriptRoot 'delivery.env.example'),
        '-f', (Join-Path $PSScriptRoot 'compose.yaml'))
    & docker @compose config --quiet
    if ($LASTEXITCODE -ne 0) { throw 'Compose 配置检查失败。' }
    switch ($Action) {
        'Prepare' { & docker @compose config }
        'Build' { & docker @compose build api web }
        'Start' { & docker @compose up -d --no-build --wait api web }
        'Status' { & docker @compose ps }
        'Stop' { & docker @compose stop }
    }
    if ($LASTEXITCODE -ne 0) { throw ('Docker 操作失败：' + $Action) }
    Write-Output '演示入口：http://127.0.0.1:8086/app/new-scan'
    Write-Output ('持久数据卷：' + $project + '_data；Stop 保留全部数据。')
} finally {
    foreach ($name in $prior.Keys) {
        if ($null -eq $prior[$name]) {
            Remove-Item -LiteralPath ('Env:' + $name) -ErrorAction SilentlyContinue
        } else {
            [Environment]::SetEnvironmentVariable($name, $prior[$name], 'Process')
        }
    }
}
