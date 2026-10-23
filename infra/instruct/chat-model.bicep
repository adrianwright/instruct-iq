targetScope = 'resourceGroup'

@description('Explicit approved Foundry account name; no shared deployment default.')
param foundryAccountName string
param deploymentName string = 'instruct-chat-luna'
@allowed([
  'gpt-5.6-luna'
  'gpt-5.6-sol'
  'gpt-5.6-terra'
])
@description('Exact catalog identifier. Explicit variant selection is required; no fallback.')
param modelName string
@minValue(1)
param capacity int = 5

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: foundryAccountName
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: foundry
  name: deploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: capacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: modelName
      version: '2026-07-09'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

output deploymentId string = chat.id
output deploymentName string = chat.name
