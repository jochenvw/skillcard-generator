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
        // SINGLETON QUEUE INVARIANT — DO NOT CHANGE WITHOUT REVIEW.
        //
        // The image-generation throttle/queue (services/image_queue.py) is an
        // in-process asyncio.Queue. It assumes exactly ONE replica + ONE worker
        // process per cluster. Multiple replicas would each run their own queue
        // and admitter loop, defeating the upstream rate-limit protection.
        //
        // Required:
        //   minReplicas: 1   — admitter task must always be running (no scale-to-zero).
        //   maxReplicas: 1   — only one in-process queue allowed.
        //   uvicorn --workers 1 (verified in Dockerfile / start command).
        //
        // To horizontally scale, the queue would have to move to a shared backend
        // (Azure Service Bus / Redis), or image generation would need to be split
        // into a dedicated single-replica worker container.
        minReplicas: 1
        maxReplicas: 1
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
