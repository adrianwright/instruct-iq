# Offline wrapper contract tests. Shadow all external commands and input reads.
$ErrorActionPreference = 'Stop'
$global:InstructTestConfigJson = @{
    appSubscriptionId = '11111111-1111-1111-1111-111111111111'
    tenantId = '22222222-2222-2222-2222-222222222222'
    deploymentId = '33333333-3333-3333-3333-333333333333'
    fabricCapacityId = '44444444-4444-4444-4444-444444444444'
    capacityResourceId = '/subscriptions/55555555-5555-5555-5555-555555555555/resourceGroups/shared/providers/Microsoft.Fabric/capacities/approved'
} | ConvertTo-Json
$global:InstructTestParameters = @{
    parameters = @{
        location = @{ value = 'centralus' }
        fabricCapacityResourceId = @{ value = '/subscriptions/55555555-5555-5555-5555-555555555555/resourceGroups/shared/providers/Microsoft.Fabric/capacities/approved' }
        deployModels = @{ value = $false }
    }
}
$global:InstructTestCalls = @()
function Get-Content {
    param($LiteralPath, [switch]$Raw)
    if ($LiteralPath -eq 'config') { return $global:InstructTestConfigJson }
    if ($LiteralPath -eq 'parameters') { return ($global:InstructTestParameters | ConvertTo-Json -Depth 20) }
    throw 'Unexpected file read'
}
function az {
    $global:InstructTestCalls += ,@($args)
    $global:LASTEXITCODE = 0
    switch ("$($args[0]) $($args[1])") {
        'bicep build' { return }
        'account show' { return '{"tenantId":"22222222-2222-2222-2222-222222222222","state":"Enabled"}' }
        'group exists' { return 'false' }
        'deployment sub' {
            if ($args[2] -ne 'what-if') { throw 'Writes forbidden' }
            return
        }
        default { throw "Unexpected Azure command: $args" }
    }
}
function python {
    $global:InstructTestCalls += ,@('python', $args)
    $global:LASTEXITCODE = 0
}
& (Join-Path $PSScriptRoot 'prepare.ps1') -ConfigPath config -ParametersPath parameters
if ($global:InstructTestCalls.Count -ne 2 -or $global:InstructTestCalls[0][0] -ne 'bicep') {
    throw 'Default validation must not contact Azure'
}
$global:InstructTestCalls = @()
& (Join-Path $PSScriptRoot 'prepare.ps1') -ConfigPath config -ParametersPath parameters -Mode WhatIf
if ($global:InstructTestCalls.Count -ne 5) { throw 'Unexpected preflight command count' }
if (-not ($global:InstructTestCalls[-1] -contains '11111111-1111-1111-1111-111111111111')) {
    throw 'What-if must explicitly target application subscription'
}
$global:InstructTestParameters.parameters.resourceGroupName = @{ value = 'demo' }
$global:InstructTestCalls = @()
$rejected = $false
try {
    & (Join-Path $PSScriptRoot 'prepare.ps1') -ConfigPath config -ParametersPath parameters
} catch {
    $rejected = $_.Exception.Message -eq 'Only rg-instruct-iq is permitted'
}
if (-not $rejected -or $global:InstructTestCalls.Count) { throw 'Wrong RG must fail before external commands' }
Write-Output '3 offline preparation wrapper checks passed'
