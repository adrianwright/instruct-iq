[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$ConfigPath,
    [Parameter(Mandatory)][string]$ParametersPath,
    [ValidateSet('Validate', 'WhatIf')][string]$Mode = 'Validate',
    [string]$ExistingOwnedGroupId = ''
)
$ErrorActionPreference = 'Stop'
$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$parameters = (Get-Content -LiteralPath $ParametersPath -Raw | ConvertFrom-Json).parameters
foreach ($key in @('appSubscriptionId', 'tenantId', 'deploymentId', 'fabricCapacityId')) {
    $null = [guid]::Parse($config.$key)
}
if ($config.capacityResourceId -notmatch '^/subscriptions/([0-9a-f-]{36})/resourceGroups/[^/]+/providers/Microsoft.Fabric/capacities/[^/]+$') {
    throw 'Explicit approved Fabric ARM capacity ID required'
}
if ($parameters.fabricCapacityResourceId.value -ine $config.capacityResourceId) {
    throw 'Capacity ARM ID differs between the two input files'
}
if ($parameters.resourceGroupName -and $parameters.resourceGroupName.value -cne 'rg-instruct-iq') {
    throw 'Only rg-instruct-iq is permitted'
}
if (($parameters | ConvertTo-Json -Depth 30) -match '<|>') {
    throw 'Resolve all placeholder decisions in the local parameter file'
}
if ($parameters.deployModels.value) {
    foreach ($key in @('chatModelName', 'chatModelVersion', 'chatModelSku', 'embeddingModelName', 'embeddingModelVersion', 'embeddingModelSku')) {
        if (-not $parameters.$key.value) { throw "Explicit model decision required: $key" }
    }
}
$image = $parameters.apiContainerImage.value
if ($image -and $image -notmatch '^instruct[a-z0-9]+\.azurecr\.io/instruct-iq@sha256:[0-9a-f]{64}$') {
    throw 'Use a digest-pinned instructional image in the new instructional registry'
}
$template = Join-Path $PSScriptRoot 'main.bicep'
az bicep build --file $template --stdout | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Bicep compilation failed' }
python (Join-Path $PSScriptRoot '..\..\agent\provisioning\instruct\fabric.py') --config $ConfigPath
if ($LASTEXITCODE -ne 0) { throw 'Offline Fabric validation failed' }
if ($Mode -eq 'Validate') { return }
function Read-AzJson([string[]]$Arguments) {
    $result = & az @Arguments --only-show-errors -o json
    if ($LASTEXITCODE -ne 0) { throw 'Explicit-scope Azure read failed' }
    return ($result | ConvertFrom-Json)
}
$account = Read-AzJson -Arguments @('account', 'show', '--subscription', $config.appSubscriptionId)
if ($account.tenantId -ine $config.tenantId -or $account.state -ne 'Enabled') {
    throw 'Application subscription/tenant mismatch'
}
$groupId = "/subscriptions/$($config.appSubscriptionId)/resourceGroups/rg-instruct-iq"
$exists = Read-AzJson -Arguments @('group', 'exists', '--subscription', $config.appSubscriptionId, '--name', 'rg-instruct-iq')
if ($exists) {
    if ($ExistingOwnedGroupId -ine $groupId) { throw 'Existing RG requires its exact previously created resource ID; never adopt a demo RG' }
    $group = Read-AzJson -Arguments @('group', 'show', '--subscription', $config.appSubscriptionId, '--name', 'rg-instruct-iq')
    if ($group.tags.project -ne 'instruct-iq' -or $group.tags.managedBy -ne 'instruct-phase-c') {
        throw 'Existing RG lacks instructional ownership tags'
    }
}
az deployment sub what-if --subscription $config.appSubscriptionId --location $parameters.location.value `
    --name instruct-iq-preflight --template-file $template --parameters "@$ParametersPath"
if ($LASTEXITCODE -ne 0) { throw 'What-if failed; no deployment was attempted' }
