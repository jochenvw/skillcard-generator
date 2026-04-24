# Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  React UI  ←→  FastAPI  ←→  Stateless Interview Service     │
│                                ↕                            │
│  Stages (YAML) → Loader → Transition Engine                 │
│                                ↕                            │
│  Services: Extraction | Validation | Compression | Inference│
│                                ↕                            │
│  Persistence: SQLite (dev) | Cosmos DB + Blob (prod)        │
│                                ↕                            │
│  Azure AI Foundry (GPT models + gpt-image-2-1)             │
└─────────────────────────────────────────────────────────────┘
```

## Dual Deployment

| Mode | Port | Use case |
|------|------|----------|
| `web` | 8000 | React + FastAPI on Azure Container Apps |
| `foundry` | 8088 | Azure AI Foundry hosting adapter |

Single codebase — set `RUN_MODE=web` or `RUN_MODE=foundry`.

## Project Structure

```
src/profile_agent/
├── agents/              # Agent implementations + Foundry adapter
├── api/                 # FastAPI routes (auth, chat, health)
├── config/              # Settings, logging, telemetry, skill taxonomy
├── models/              # Pydantic v2 data models
├── prompts/templates/   # Markdown prompt templates
├── services/            # Business logic
│   ├── stateless_interview_service.py  # Main SSE streaming chat
│   ├── extraction_service.py           # LLM fact extraction
│   ├── validation_service.py           # Stage completion check
│   ├── compression_service.py          # Context compression
│   ├── inference_service.py            # Skill matrix updates
│   └── image_service.py               # Image generation
├── stages/definitions/  # 10 YAML stage configs
├── workflows/           # Multi-step orchestration
└── app.py               # Entrypoint
frontend/src/
├── components/          # ChatPanel, SkillCard, ProgressPanel, etc.
├── hooks/               # useLocalSession (localStorage state)
└── types/               # TypeScript interfaces
infra/
├── main.bicep           # Orchestration
├── modules/             # ACR, Cosmos, KV, Container Apps, etc.
└── parameters/          # Dev/prod param files
```

## Interview Flow

10 stages, each with YAML-defined prompts, extraction targets, and completion criteria:

| # | Stage | Purpose |
|---|-------|---------|
| 0 | Introduction | Warm welcome, learn name and role |
| 1 | Heroes & Role Models | Who they admire and why |
| 2 | Books, Talks & Quotes | Influences that shaped their thinking |
| 3 | Proudest Projects | Work they're most proud of |
| 4 | Shower Thoughts | What occupies their mind |
| 5 | Side Projects | Hobby builds and explorations |
| 6 | Aspirations | Where they want to grow |
| 7 | Collaboration | How they work with others |
| 8 | Validation | Confirm the emerging profile |
| 9 | Card Generation | Generate the strengths card |

Stages auto-advance after 2–3 turns or when completion criteria are met.

## SSE Streaming Protocol

The chat API uses **AI SDK Data Stream Protocol** over Server-Sent Events:

```
data: {"type": "text-start", "id": "..."}
data: {"type": "text-delta", "id": "...", "delta": "token"}
data: {"type": "text-end", "id": "..."}
data: {"type": "data-stateUpdate", "data": {...}}
data: [DONE]
```

All state is passed per-request (stateless server). The React frontend persists state in `localStorage`.

## Azure Infrastructure

Provisioned via Bicep (`infra/main.bicep`):

| Resource | Purpose |
|----------|---------|
| Container Apps | Auto-scaling web host |
| Cosmos DB (serverless) | Session & profile storage |
| Blob Storage | Images and generated cards |
| Key Vault | Secrets management |
| Application Insights | Telemetry & monitoring |
| Container Registry | Docker image storage |
| Managed Identity | RBAC auth for all services |

## Configuration

All settings via environment variables (see `.env.example`):

| Variable | Description | Required |
|----------|-------------|----------|
| `RUN_MODE` | `web` or `foundry` | Yes |
| `FOUNDRY_PROJECT_ENDPOINT` | Azure AI Foundry project endpoint | Yes |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | Model deployment name | Yes |
| `COSMOS_ENDPOINT` | Cosmos DB endpoint | Prod only |
| `AZURE_STORAGE_ACCOUNT_URL` | Storage account | Prod only |
| `ENTRA_TENANT_ID` | Azure AD tenant | Prod only |
| `ENTRA_CLIENT_ID` | App registration client ID | Prod only |
| `APPINSIGHTS_CONNECTION_STRING` | App Insights connection | Prod only |
