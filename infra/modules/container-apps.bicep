// Container Apps — hosts the agent web application

param location string
param resourcePrefix string
param imageTag string
param managedIdentityId string
param managedIdentityClientId string
param containerRegistryLoginServer string
param logAnalyticsWorkspaceId string
param appInsightsConnectionString string
param keyVaultUri string
param entraTenantId string
param entraClientId string
param foundryProjectEndpoint string

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${resourcePrefix}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: reference(logAnalyticsWorkspaceId, '2023-09-01').customerId
        sharedKey: listKeys(logAnalyticsWorkspaceId, '2023-09-01').primarySharedKey
      }
    }
  }
}

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${resourcePrefix}-app'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        {
          server: containerRegistryLoginServer
          identity: managedIdentityId
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'profile-agent'
          image: '${containerRegistryLoginServer}/profile-agent:${imageTag}'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'RUN_MODE', value: 'web' }
            { name: 'ENVIRONMENT', value: 'prod' }
            { name: 'AZURE_CLIENT_ID', value: managedIdentityClientId }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_CLIENT_ID', value: entraClientId }
            { name: 'KEY_VAULT_URI', value: keyVaultUri }
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsightsConnectionString }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
          ]
        }
      ]
      scale: {
        // Keep one replica warm to avoid cold-start latency on long-running endpoints
        // like /api/regenerate, which can otherwise hit the 240s ingress timeout (504).
        minReplicas: 1
        maxReplicas: 5
        rules: [
          {
            name: 'http-scale'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'
