# Profile Agent — Strengths Interview & Card Generator

An AI-powered conversational interview agent that discovers a person's unique technical strengths through playful, thoughtful conversation — then generates a collectible-style strengths profile card (Pokémon/Magic the Gathering aesthetic).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Chainlit UI  ←→  FastAPI  ←→  Agent Runtime (BaseAgent)    │
│                                  ↕                          │
│  Stages (YAML) → Runner → Transition Engine                 │
│                                  ↕                          │
│  Services: Extraction | Validation | Compression | Inference│
│                                  ↕                          │
│  Persistence: SQLite (dev) | Cosmos DB + Blob (prod)        │
│                                  ↕                          │
│  Azure OpenAI (GPT-4o + gpt-image-1.5)                     │
└─────────────────────────────────────────────────────────────┘
```

### Dual Deployment Model

- **`web` mode** — Chainlit + FastAPI on Azure Container Apps (port 8000)
- **`foundry` mode** — Azure AI Foundry hosting adapter (port 8088)

Single codebase, same agent logic. Set `RUN_MODE=web` or `RUN_MODE=foundry`.

## Quick Start

### Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- Azure OpenAI resource with GPT-4o and gpt-image-1.5 deployments
- (Optional) Azure AI Foundry project for Foundry deployment

### Local Development

```bash
# Clone and install
git clone <repo-url>
cd skillcard-agent
uv sync

# Configure
cp .env.example .env
# Edit .env with your Azure OpenAI credentials

# Run (web mode)
uv run python -m profile_agent

# Run (foundry mode)
RUN_MODE=foundry uv run python -m profile_agent
```

### Docker

```bash
# Web mode
docker compose up profile-agent-web

# Foundry mode
docker compose up profile-agent-foundry
```

## Project Structure

```
src/profile_agent/
├── agents/                 # BaseAgent implementations
│   ├── interview_agent.py  # Main conversational agent
│   ├── evaluator_agent.py  # Stage completion validation
│   ├── summarizer_agent.py # Guided compression
│   ├── profiler_agent.py   # Skill matrix inference
│   └── foundry_adapter.py  # Foundry hosting wrapper
├── api/                    # FastAPI routes
│   ├── auth.py             # Entra ID authentication
│   ├── sessions.py         # Session CRUD
│   ├── uploads.py          # File upload
│   └── health.py           # Health checks
├── config/                 # Configuration
│   ├── settings.py         # Pydantic Settings
│   ├── logging.py          # Structured logging
│   ├── telemetry.py        # OpenTelemetry + Azure Monitor
│   └── skill_taxonomy.yaml # 19 skill dimensions
├── memory/                 # Persistence layer
│   ├── base.py             # Abstract store protocols
│   ├── implementations/    # SQLite, Cosmos DB, Blob
│   └── *_store.py          # Factory facades
├── models/                 # Pydantic v2 data models
├── prompts/                # Prompt templates
│   └── templates/          # Markdown templates with $-substitution
├── services/               # Business logic services
│   ├── conversation_service.py  # Per-turn 11-step pipeline
│   ├── extraction_service.py    # LLM fact extraction
│   ├── validation_service.py    # Stage completion check
│   ├── compression_service.py   # Guided context compression
│   ├── inference_service.py     # Skill matrix updates
│   └── image_service.py        # Image model integration (gpt-image-1.5)
├── stages/                 # Interview stage framework
│   ├── definitions/        # 10 YAML stage configs
│   ├── runner.py           # Per-stage turn management
│   └── transition_engine.py # Cross-stage flow
├── ui/                     # Chainlit chat interface
├── workflows/              # Multi-step orchestration
├── app.py                  # Main entrypoint
└── __main__.py             # Module runner
infra/                      # Bicep IaC
├── main.bicep              # Orchestration
├── modules/                # ACR, Cosmos, KV, Container Apps, etc.
└── parameters/             # Dev/prod param files
```

## Interview Flow

10 stages, each with YAML-defined prompts, extraction targets, and completion criteria:

1. **Introduction** — Warm welcome, learn name and current role
2. **Heroes & Inspirations** — Who they admire and why
3. **Influences** — Experiences that shaped their approach
4. **Proud Projects** — Work they're most proud of
5. **Shower Thoughts** — What occupies their mind
6. **Hobby Projects** — Side projects and explorations
7. **Aspirations** — Where they want to grow
8. **Collaboration** — How they work with others
9. **Validation** — Confirm the emerging profile
10. **Card Generation** — Generate the strengths card

### Per-Turn Pipeline

Each conversation turn runs through an 11-step pipeline:
1. Append turn to transcript
2. Extract structured facts (LLM)
3. Validate completion criteria (LLM)
4. Identify missing information
5. Compress context if needed (LLM)
6. Persist all data
7. Update skill matrix
8. Emit telemetry
9. Generate next response
10. Present confirmation if stage complete
11. Advance only after confirmation

## Azure Infrastructure

Deploy with Bicep:

```bash
az deployment group create \
  --resource-group <rg-name> \
  --template-file infra/main.bicep \
  --parameters infra/parameters/dev.bicepparam
```

Resources provisioned:
- **Container Apps** — Auto-scaling web host
- **Cosmos DB** (serverless) — Session & profile storage
- **Blob Storage** — Images and generated cards
- **Key Vault** — Secrets management
- **Application Insights** — Telemetry & monitoring
- **Container Registry** — Image storage
- **Managed Identity** — RBAC-based auth for all services

## Testing

```bash
uv run pytest tests/ -v
```

## Configuration

All settings via environment variables (see `.env.example`):

| Variable | Description | Required |
|---|---|---|
| `RUN_MODE` | `web` or `foundry` | Yes |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint | Yes |
| `AZURE_OPENAI_DEPLOYMENT` | Model deployment name | Yes |
| `COSMOS_ENDPOINT` | Cosmos DB endpoint | Prod only |
| `STORAGE_ACCOUNT_NAME` | Storage account | Prod only |
| `ENTRA_TENANT_ID` | Azure AD tenant | Prod only |
| `ENTRA_CLIENT_ID` | App registration client ID | Prod only |

## License

MIT — see [LICENSE](LICENSE) for details.
