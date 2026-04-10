// Parameter file for dev environment
using '../main.bicep'

param environment = 'dev'
param baseName = 'profileagent'
param imageTag = 'latest'
param foundryProjectEndpoint = ''
// Cognitive Services RBAC — resource ID of the AI Services account
param cognitiveServicesAccountId = ''
// Entra auth — leave empty for anonymous mode, fill in after first deploy
param entraTenantId = ''
param entraClientId = ''
param entraClientSecret = ''
// Direct OpenAI — leave empty when using Foundry
param azureOpenAiEndpoint = ''
param azureOpenAiKey = ''
param azureOpenAiDeployment = 'gpt-4o'
