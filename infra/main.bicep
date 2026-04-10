// Profile Agent — Main Bicep Orchestration
// Deploys all Azure resources for the interview agent system.

targetScope = 'resourceGroup'

// ─── Parameters ────────────────────────────────────────────────────
@description('Environment name (dev, staging, prod)')
@allowed(['dev', 'staging', 'prod'])
param environment string = 'dev'

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Base name prefix for resources')
@minLength(3)
@maxLength(12)
param baseName string = 'profileagent'

@description('Container image tag')
param imageTag string = 'latest'

@description('Azure AI Foundry project endpoint (primary AI backend)')
param foundryProjectEndpoint string

@description('Resource ID of the Azure AI Services account (for RBAC). Leave empty to skip.')
param cognitiveServicesAccountId string = ''

@description('Entra ID tenant ID (leave empty to disable web UI auth)')
param entraTenantId string = ''

@description('Entra ID client ID for the web app (leave empty to disable web UI auth)')
param entraClientId string = ''

@secure()
@description('Entra ID client secret (leave empty to disable web UI auth)')
param entraClientSecret string = ''


// ─── Variables ─────────────────────────────────────────────────────
var uniqueSuffix = uniqueString(resourceGroup().id, baseName)
var resourcePrefix = '${baseName}-${environment}'

// ─── Modules ───────────────────────────────────────────────────────

module identities 'modules/identities.bicep' = {
  name: 'identities'
  params: {
    location: location
    resourcePrefix: resourcePrefix
  }
}

module monitoring 'modules/monitoring.bicep' = {
  name: 'monitoring'
  params: {
    location: location
    resourcePrefix: resourcePrefix
  }
}

module storage 'modules/storage.bicep' = {
  name: 'storage'
  params: {
    location: location
    uniqueSuffix: uniqueSuffix
    managedIdentityPrincipalId: identities.outputs.principalId
  }
}

module keyvault 'modules/keyvault.bicep' = {
  name: 'keyvault'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    managedIdentityPrincipalId: identities.outputs.principalId
    entraClientSecret: entraClientSecret
  }
}

module containerApps 'modules/container-apps.bicep' = {
  name: 'containerApps'
  params: {
    location: location
    resourcePrefix: resourcePrefix
    imageTag: imageTag
    managedIdentityId: identities.outputs.managedIdentityId
    managedIdentityClientId: identities.outputs.clientId
    containerRegistryLoginServer: storage.outputs.acrLoginServer
    logAnalyticsWorkspaceId: monitoring.outputs.logAnalyticsWorkspaceId
    appInsightsConnectionString: monitoring.outputs.appInsightsConnectionString
    keyVaultUri: keyvault.outputs.keyVaultUri
    entraTenantId: entraTenantId
    entraClientId: entraClientId
    foundryProjectEndpoint: foundryProjectEndpoint
  }
}

// Cognitive Services RBAC — grants Managed Identity access to Azure AI Services
// for both chat completions and image generation
// Note: when the AI Services account is in a DIFFERENT resource group, use the
// CD workflow's "Ensure Cognitive Services RBAC" step instead of this module.
module cognitiveServices 'modules/cognitive-services.bicep' = if (!empty(cognitiveServicesAccountId)) {
  name: 'cognitiveServices'
  params: {
    managedIdentityPrincipalId: identities.outputs.principalId
    cognitiveServicesAccountId: cognitiveServicesAccountId
  }
}

// ─── Outputs ───────────────────────────────────────────────────────
output containerAppUrl string = containerApps.outputs.containerAppUrl
output acrLoginServer string = storage.outputs.acrLoginServer
output appInsightsConnectionString string = monitoring.outputs.appInsightsConnectionString
output keyVaultUri string = keyvault.outputs.keyVaultUri
