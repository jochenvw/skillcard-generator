# Deployment Guide — Profile Agent

Step-by-step instructions to provision Azure infrastructure, configure identity, and deploy the application.

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Azure CLI | 2.60+ | `winget install Microsoft.AzureCLI` |
| Bicep CLI | 0.28+ | bundled with Azure CLI |
| Docker Desktop | 24+ | [docker.com](https://docs.docker.com/desktop/) |
| uv | 0.4+ | `winget install astral-sh.uv` |
| Python | 3.12+ | `winget install Python.Python.3.12` |

You also need:

- An Azure subscription with **Owner** or **Contributor + User Access Administrator** role
- An Azure OpenAI resource with **gpt-4o** and **gpt-image-1.5** deployments
- (Optional) An Azure AI Foundry project if deploying in Foundry mode

---

## 1. Authenticate and Set Defaults

```powershell
# Login
az login

# Set the subscription you want to use
az account set --subscription "<your-subscription-id>"

# Confirm
az account show --query "{name:name, id:id, tenantId:tenantId}" -o table
```

Note your **Tenant ID** from the output — you'll need it for Entra ID configuration.

---

## 2. Create Entra ID App Registration (Service Principal)

The app registration provides authentication for end users signing in via the Chainlit UI.

```powershell
# Create the app registration
$APP_NAME = "profileagent-app"
$app = az ad app create `
    --display-name $APP_NAME `
    --sign-in-audience AzureADMyOrg `
    --web-redirect-uris "http://localhost:8000/api/auth/callback" `
    --query "{appId:appId, id:id}" -o json | ConvertFrom-Json

$ENTRA_CLIENT_ID = $app.appId
$ENTRA_OBJECT_ID = $app.id

Write-Host "Client ID: $ENTRA_CLIENT_ID"
```

### Create a client secret

```powershell
$secret = az ad app credential reset `
    --id $ENTRA_OBJECT_ID `
    --display-name "profile-agent-secret" `
    --query "{password:password}" -o json | ConvertFrom-Json

$ENTRA_CLIENT_SECRET = $secret.password

Write-Host "Client Secret: $ENTRA_CLIENT_SECRET"
# ⚠️ Save this immediately — it won't be shown again
```

### Create the backing service principal

```powershell
az ad sp create --id $ENTRA_CLIENT_ID
```

### Add redirect URI for production (after Container App is deployed)

```powershell
# Run this after step 4 when you have the Container App URL
az ad app update `
    --id $ENTRA_OBJECT_ID `
    --web-redirect-uris "http://localhost:8000/api/auth/callback" "https://<container-app-fqdn>/api/auth/callback"
```

---

## 3. Create Resource Group

```powershell
$RESOURCE_GROUP = "rg-profileagent-dev"
$LOCATION = "eastus2"

az group create --name $RESOURCE_GROUP --location $LOCATION
```

---

## 4. Deploy Infrastructure with Bicep

### Gather parameter values

You need these values before deploying:

| Parameter | Source |
|---|---|
| `entraTenantId` | `az account show --query tenantId -o tsv` |
| `entraClientId` | From step 2 (`$ENTRA_CLIENT_ID`) |
| `entraClientSecret` | From step 2 (`$ENTRA_CLIENT_SECRET`) |
| `azureOpenAiEndpoint` | Azure Portal → your OpenAI resource → Keys & Endpoint |
| `azureOpenAiKey` | Azure Portal → your OpenAI resource → Keys & Endpoint |
| `azureOpenAiDeployment` | Name of your GPT-4o deployment (default: `gpt-4o`) |

### Deploy

```powershell
$TENANT_ID = az account show --query tenantId -o tsv
$OPENAI_ENDPOINT = "https://<your-openai-resource>.openai.azure.com"
$OPENAI_KEY = "<your-openai-key>"

az deployment group create `
    --resource-group $RESOURCE_GROUP `
    --template-file infra/main.bicep `
    --parameters `
        environment=dev `
        entraTenantId=$TENANT_ID `
        entraClientId=$ENTRA_CLIENT_ID `
        entraClientSecret=$ENTRA_CLIENT_SECRET `
        azureOpenAiEndpoint=$OPENAI_ENDPOINT `
        azureOpenAiKey=$OPENAI_KEY `
        azureOpenAiDeployment=gpt-4o
```

### Capture outputs

```powershell
$outputs = az deployment group show `
    --resource-group $RESOURCE_GROUP `
    --name main `
    --query "properties.outputs" -o json | ConvertFrom-Json

$ACR_SERVER = $outputs.acrLoginServer.value
$CONTAINER_APP_URL = $outputs.containerAppUrl.value
$COSMOS_ENDPOINT = $outputs.cosmosAccountEndpoint.value
$APPINSIGHTS_CONN = $outputs.appInsightsConnectionString.value
$KEYVAULT_URI = $outputs.keyVaultUri.value

Write-Host "ACR: $ACR_SERVER"
Write-Host "App: $CONTAINER_APP_URL"
Write-Host "Cosmos: $COSMOS_ENDPOINT"
```

### What gets deployed

| Resource | Purpose |
|---|---|
| **User-Assigned Managed Identity** | RBAC auth for all service-to-service communication |
| **Log Analytics Workspace** | Centralized logging |
| **Application Insights** | APM, traces, custom metrics |
| **Container Registry** (Basic) | Docker image storage |
| **Storage Account** + `assets` container | Profile pictures & generated cards |
| **Key Vault** | Entra client secret, OpenAI key |
| **Cosmos DB** (serverless NoSQL) | Sessions, profiles, transcripts |
| **Container Apps Environment** + App | Hosts the web application |

All services are connected via the managed identity with least-privilege RBAC roles:
- ACR Pull on Container Registry
- Storage Blob Data Contributor on Storage Account
- Cosmos DB Built-in Data Contributor on Cosmos DB
- Key Vault Secrets User on Key Vault

---

## 5. Build and Push the Container Image

```powershell
# Extract ACR name from login server (e.g., "profileagentxyz.azurecr.io" → "profileagentxyz")
$ACR_NAME = $ACR_SERVER.Split('.')[0]

# Login to ACR
az acr login --name $ACR_NAME

# Build the image
docker build -t "${ACR_SERVER}/profile-agent:latest" .

# Push
docker push "${ACR_SERVER}/profile-agent:latest"
```

### Update Container App with the new image

The Bicep deployment created the Container App pointing at `profile-agent:latest`. After the first push, the app will pull the image. For subsequent updates:

```powershell
# Build + push a tagged version
$TAG = "v$(Get-Date -Format 'yyyyMMdd-HHmmss')"
docker build -t "${ACR_SERVER}/profile-agent:${TAG}" .
docker push "${ACR_SERVER}/profile-agent:${TAG}"

# Update the container app
$APP_NAME = "profileagent-dev-app"
az containerapp update `
    --name $APP_NAME `
    --resource-group $RESOURCE_GROUP `
    --image "${ACR_SERVER}/profile-agent:${TAG}"
```

---

## 6. Update Entra ID Redirect URI

Now that the Container App is deployed, add the production redirect URI:

```powershell
az ad app update `
    --id $ENTRA_OBJECT_ID `
    --web-redirect-uris `
        "http://localhost:8000/api/auth/callback" `
        "${CONTAINER_APP_URL}/api/auth/callback"
```

---

## 7. Verify Deployment

### Health check

```powershell
Invoke-RestMethod -Uri "${CONTAINER_APP_URL}/health"
# Expected: {"status":"healthy"}

Invoke-RestMethod -Uri "${CONTAINER_APP_URL}/readiness"
# Expected: {"status":"ready"}
```

### Check Container App logs

```powershell
az containerapp logs show `
    --name "profileagent-dev-app" `
    --resource-group $RESOURCE_GROUP `
    --follow
```

### Verify Cosmos DB

```powershell
az cosmosdb sql database list `
    --account-name "profileagent-dev-cosmos" `
    --resource-group $RESOURCE_GROUP `
    --query "[].id" -o table
```

---

## 8. (Optional) Deploy to Azure AI Foundry

If you want the agent available through Foundry in addition to the web UI:

```powershell
$FOUNDRY_ENDPOINT = "https://<resource>.services.ai.azure.com/api/projects/<project>"

# Rebuild with foundry mode
docker build -t "${ACR_SERVER}/profile-agent-foundry:latest" `
    --build-arg RUN_MODE=foundry .
docker push "${ACR_SERVER}/profile-agent-foundry:latest"

# Publish agent metadata to Foundry
python -m profile_agent.scripts.publish_to_foundry `
    --endpoint $FOUNDRY_ENDPOINT `
    --image "${ACR_SERVER}/profile-agent-foundry:latest"
```

---

## Environment-Specific Configuration

### Local Development

```powershell
cp .env.example .env
# Edit .env — set ENVIRONMENT=dev, RUN_MODE=web, and Azure OpenAI credentials
# SQLite is used automatically in dev mode (no Cosmos/Blob needed)

uv sync
uv run python -m profile_agent
```

### Production (Container Apps)

All config is injected via Container Apps environment variables (set by the Bicep deployment in step 4). Secrets are stored in Key Vault and referenced by the managed identity.

---

## Redeployment Checklist

For pushing code changes to an existing deployment:

```powershell
# 1. Build and tag
$TAG = "v$(Get-Date -Format 'yyyyMMdd-HHmmss')"
docker build -t "${ACR_SERVER}/profile-agent:${TAG}" .

# 2. Push
docker push "${ACR_SERVER}/profile-agent:${TAG}"

# 3. Update Container App
az containerapp update `
    --name "profileagent-dev-app" `
    --resource-group $RESOURCE_GROUP `
    --image "${ACR_SERVER}/profile-agent:${TAG}"

# 4. Verify
Invoke-RestMethod -Uri "${CONTAINER_APP_URL}/health"
```

---

## Teardown

To remove all resources:

```powershell
# Remove the resource group (deletes everything)
az group delete --name $RESOURCE_GROUP --yes --no-wait

# Remove the app registration
az ad app delete --id $ENTRA_OBJECT_ID
```
