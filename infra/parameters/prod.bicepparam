// Parameter file for production environment
using '../main.bicep'

param environment = 'prod'
param baseName = 'profileagent'
param imageTag = 'latest'
param entraTenantId = ''
param entraClientId = ''
param entraClientSecret = ''
param azureOpenAiEndpoint = ''
param azureOpenAiKey = ''
param azureOpenAiDeployment = 'gpt-4o'
param foundryProjectEndpoint = ''
param cognitiveServicesAccountId = ''
