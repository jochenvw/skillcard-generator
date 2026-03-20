// Parameter file for dev environment
using '../main.bicep'

param environment = 'dev'
param baseName = 'profileagent'
param imageTag = 'latest'
param entraTenantId = ''
param entraClientId = ''
param entraClientSecret = ''
param azureOpenAiEndpoint = ''
param azureOpenAiKey = ''
param azureOpenAiDeployment = 'gpt-4o'
param foundryProjectEndpoint = ''
