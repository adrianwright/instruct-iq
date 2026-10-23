targetScope = 'subscription'

@description('Metadata location for the NEW dedicated resource group; not the Fabric capacity region.')
param location string
param aiLocation string
param searchLocation string
param hostingLocation string
@description('Container Apps environment region; can differ when the hosting region is capacity-constrained.')
param environmentLocation string = hostingLocation
param staticWebLocation string
@description('Empty during foundation provisioning. Set only to a new instructional image after publishing to the new registry.')
param apiContainerImage string = ''

@allowed(['rg-instruct-iq'])
param resourceGroupName string = 'rg-instruct-iq'

@description('Independent approved Fabric ARM ID. Informational only: no capacity resource or role is deployed.')
param fabricCapacityResourceId string

param deployModels bool = false
param chatModelName string = ''
param chatModelVersion string = ''
param chatModelSku string = 'GlobalStandard'
@minValue(1)
param chatModelCapacity int = 1
param embeddingModelName string = ''
param embeddingModelVersion string = ''
param embeddingModelSku string = 'GlobalStandard'
@minValue(1)
param embeddingModelCapacity int = 1

resource group 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: {
    project: 'instruct-iq'
    managedBy: 'instruct-phase-c'
    environment: 'demo'
  }
}

module stack 'resources.bicep' = {
  name: 'instruct-isolated-stack'
  scope: group
  params: {
    aiLocation: aiLocation
    searchLocation: searchLocation
    hostingLocation: hostingLocation
    environmentLocation: environmentLocation
    staticWebLocation: staticWebLocation
    apiContainerImage: apiContainerImage
    deployModels: deployModels
    chatModelName: chatModelName
    chatModelVersion: chatModelVersion
    chatModelSku: chatModelSku
    chatModelCapacity: chatModelCapacity
    embeddingModelName: embeddingModelName
    embeddingModelVersion: embeddingModelVersion
    embeddingModelSku: embeddingModelSku
    embeddingModelCapacity: embeddingModelCapacity
  }
}

output appSubscriptionId string = subscription().subscriptionId
output resourceGroupId string = group.id
output approvedCapacityReference string = fabricCapacityResourceId
output resources object = stack.outputs.resources
