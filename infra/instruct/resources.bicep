targetScope = 'resourceGroup'

param aiLocation string
param searchLocation string
param hostingLocation string
param environmentLocation string
param staticWebLocation string
param apiContainerImage string
param deployModels bool
param chatModelName string
param chatModelVersion string
param chatModelSku string
param chatModelCapacity int
param embeddingModelName string
param embeddingModelVersion string
param embeddingModelSku string
param embeddingModelCapacity int

var prefix = 'instruct-${uniqueString(resourceGroup().id)}'
var tags = {
  project: 'instruct-iq'
  managedBy: 'instruct-phase-c'
}
var cognitiveUserRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
var searchReaderRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '1407120a-92aa-4202-b7e9-c0e197c71c8f')

resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: '${prefix}-ai'
  location: aiLocation
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  tags: tags
  properties: {
    allowProjectManagement: true
    customSubDomainName: '${prefix}-ai'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: 'instruct-iq'
  location: aiLocation
  identity: { type: 'SystemAssigned' }
  tags: tags
  properties: {
    displayName: 'Instruct IQ'
    description: 'Isolated synthetic instructional grounding'
  }
}

resource chat 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = if (deployModels) {
  parent: foundry
  name: 'instruct-chat'
  sku: { name: chatModelSku, capacity: chatModelCapacity }
  properties: {
    model: { format: 'OpenAI', name: chatModelName, version: chatModelVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource embeddings 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = if (deployModels) {
  parent: foundry
  name: 'instruct-embedding'
  sku: { name: embeddingModelSku, capacity: embeddingModelCapacity }
  properties: {
    model: { format: 'OpenAI', name: embeddingModelName, version: embeddingModelVersion }
    versionUpgradeOption: 'NoAutoUpgrade'
  }
}

resource search 'Microsoft.Search/searchServices@2025-05-01' = {
  name: '${prefix}-search'
  location: searchLocation
  sku: { name: 'standard' }
  identity: { type: 'SystemAssigned' }
  tags: tags
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'Default'
    semanticSearch: 'free'
    disableLocalAuth: true
    publicNetworkAccess: 'enabled'
  }
}

module observability '../modules/observability.bicep' = {
  name: 'instruct-observability'
  params: {
    location: hostingLocation
    logAnalyticsName: '${prefix}-logs'
    appInsightsName: '${prefix}-insights'
    tags: tags
  }
}

module identity '../modules/identity.bicep' = {
  name: 'instruct-api-identity'
  params: {
    location: hostingLocation
    managedIdentityName: '${prefix}-api-identity'
    tags: tags
  }
}

module apps 'apps.bicep' = {
  name: 'instruct-apps'
  params: {
    prefix: prefix
    location: hostingLocation
    environmentLocation: environmentLocation
    staticWebLocation: staticWebLocation
    registryName: 'instruct${uniqueString(resourceGroup().id)}'
    apiContainerImage: apiContainerImage
    identityResourceId: identity.outputs.identityId
    identityPrincipalId: identity.outputs.principalId
    identityClientId: identity.outputs.clientId
    logAnalyticsCustomerId: observability.outputs.logAnalyticsCustomerId
    logAnalyticsSharedKey: observability.outputs.logAnalyticsSharedKey
    appInsightsConnectionString: observability.outputs.appInsightsConnectionString
    tags: tags
  }
}

resource apiSearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, '${prefix}-api-identity', searchReaderRole)
  scope: search
  properties: {
    principalId: identity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: searchReaderRole
  }
}

module apiSearchMetadata 'search-query-access.bicep' = {
  name: 'instruct-search-query-access'
  params: {
    searchServiceName: search.name
    apiPrincipalId: identity.outputs.principalId
  }
}

resource searchModelUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, search.id, cognitiveUserRole)
  scope: foundry
  properties: {
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: cognitiveUserRole
  }
}

resource apiModelUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, '${prefix}-api-identity', cognitiveUserRole)
  scope: foundry
  properties: {
    principalId: identity.outputs.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: cognitiveUserRole
  }
}

output resources object = {
  foundryId: foundry.id
  projectId: project.id
  searchId: search.id
  searchEndpoint: 'https://${search.name}.search.windows.net'
  hosting: apps.outputs.resources
  apiPrincipalId: identity.outputs.principalId
  apiIdentityId: identity.outputs.identityId
  apiIdentityClientId: identity.outputs.clientId
  logsId: resourceId('Microsoft.OperationalInsights/workspaces', '${prefix}-logs')
  insightsId: observability.outputs.appInsightsResourceId
}
