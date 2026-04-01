// Cognitive Services RBAC — grants the Managed Identity access to Azure AI Services
// Required for both chat completions (OpenAI) and image generation (gpt-image)

param managedIdentityPrincipalId string

@description('Resource ID of the Azure AI Services / Cognitive Services account')
param cognitiveServicesAccountId string

// Cognitive Services User — allows inference calls (chat, images, embeddings)
var cognitiveServicesUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource cognitiveServicesRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cognitiveServicesAccountId, managedIdentityPrincipalId, cognitiveServicesUserRoleId)
  scope: cognitiveServicesAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', cognitiveServicesUserRoleId)
    principalId: managedIdentityPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// Reference the existing Cognitive Services account
resource cognitiveServicesAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: last(split(cognitiveServicesAccountId, '/'))
}
