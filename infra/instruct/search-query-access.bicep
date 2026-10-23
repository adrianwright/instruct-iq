targetScope = 'resourceGroup'

param searchServiceName string
param apiPrincipalId string

resource search 'Microsoft.Search/searchServices@2025-05-01' existing = {
  name: searchServiceName
}

// Content retrieval remains covered by Search Index Data Reader.
resource metadataReader 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, 'instruct-kb-definition-reader')
  properties: {
    roleName: 'Instruct IQ KB Definition Reader ${uniqueString(resourceGroup().id)}'
    description: 'Read KB definitions to verify the dedicated source mapping; no writes, keys or service configuration.'
    type: 'CustomRole'
    assignableScopes: [resourceGroup().id]
    permissions: [{
      actions: ['Microsoft.Search/searchServices/knowledgeBases/read']
      notActions: []
      dataActions: []
      notDataActions: []
    }]
  }
}

resource assignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, apiPrincipalId, metadataReader.id)
  scope: search
  properties: {
    principalId: apiPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: metadataReader.id
  }
}

output roleDefinitionId string = metadataReader.id
output assignmentId string = assignment.id
