// Adapted from ../modules/apps.bicep: retain ACA/ACR/SWA design, remove mandatory legacy secrets and ISV settings.
param prefix string
param location string
param environmentLocation string = location
param staticWebLocation string
param registryName string
param apiContainerImage string
param identityResourceId string
param identityPrincipalId string
param identityClientId string
param logAnalyticsCustomerId string
@secure()
param logAnalyticsSharedKey string
param appInsightsConnectionString string
param tags object

var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: environmentLocation == location ? '${prefix}-env' : '${prefix}-env-${environmentLocation}'
  location: environmentLocation
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalyticsCustomerId
        sharedKey: logAnalyticsSharedKey
      }
    }
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identityPrincipalId, acrPullRoleId)
  scope: registry
  properties: {
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: acrPullRoleId
  }
}

resource web 'Microsoft.Web/staticSites@2023-12-01' = {
  name: '${prefix}-web'
  location: staticWebLocation
  tags: tags
  sku: { name: 'Free', tier: 'Free' }
  properties: { allowConfigFileUpdates: true }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = if (!empty(apiContainerImage)) {
  name: '${prefix}-api'
  location: environmentLocation
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityResourceId}': {} }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 8000, transport: 'auto', allowInsecure: false }
      registries: [ { server: registry.properties.loginServer, identity: identityResourceId } ]
    }
    template: {
      scale: { minReplicas: 0, maxReplicas: 1 }
      containers: [
        {
          name: 'api'
          image: apiContainerImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [
            { name: 'AZURE_CLIENT_ID', value: identityClientId }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'CORS_ORIGINS', value: 'https://${web.properties.defaultHostname}' }
          ]
        }
      ]
    }
  }
  dependsOn: [ acrPull ]
}

output resources object = {
  environmentId: environment.id
  registryId: registry.id
  registryEndpoint: registry.properties.loginServer
  webId: web.id
  webUrl: 'https://${web.properties.defaultHostname}'
  apiId: !empty(apiContainerImage) ? api!.id : ''
  apiUrl: !empty(apiContainerImage) ? 'https://${api!.properties.configuration.ingress.fqdn}' : ''
}
