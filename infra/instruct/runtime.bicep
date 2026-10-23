// App-only release: never redeploy the foundation or its failed Central US environment.
param apiName string
param environmentId string
param identityResourceId string
param registryServer string
param image string
param environmentVariables object
param tags object
param location string = 'eastus2'

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityResourceId}': {} }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: true, targetPort: 8000, transport: 'auto', allowInsecure: false }
      registries: [ { server: registryServer, identity: identityResourceId } ]
    }
    template: {
      scale: { minReplicas: 0, maxReplicas: 1 }
      containers: [
        {
          name: 'api'
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [for variable in items(environmentVariables): {
            name: variable.key
            value: string(variable.value)
          }]
        }
      ]
    }
  }
}

output apiId string = api.id
output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
