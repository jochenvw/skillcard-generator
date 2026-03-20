Create a production-grade Azure-native Python project using uv, the latest Microsoft Agent Framework, and Microsoft Foundry SDKs.

Goal:
Build an interview-style agent system that runs on Azure, is deployable to the new Microsoft Foundry, has a modern ChatGPT-like web UI secured with Microsoft Entra ID, stores resumable session memory, uploads/stores profile pictures in Azure Blob Storage, emits rich OpenTelemetry-based telemetry into Application Insights / Log Analytics, and ends by generating both:
1. a structured profile summary
2. a stylized “Pokémon / Magic-like strengths card” image based on the user’s photo and inferred strengths, inspired by the “baseball card” concept

Important:
- This is a real Azure deployment target, not just local code.
- The stack must run on Azure.
- The agent must be publishable/deployable to the new Microsoft Foundry / Foundry agent surfaces using the current SDK approach.
- Use thin wrappers around fast-evolving Foundry APIs so future SDK changes are isolated.
- Favor production realism over toy examples.

==================================================
TECHNICAL STACK
==================================================

Required:
- Python 3.12+
- uv for package/env management
- latest Microsoft Agent Framework
- latest Microsoft Foundry SDK / client libraries needed to create, publish, and invoke the agent
- Azure-hosted runtime
- Bicep for infrastructure as code
- OpenTelemetry for traces, metrics, and logs
- Azure Application Insights + Log Analytics workspace
- Azure Blob Storage for uploaded profile pictures and generated card assets
- Microsoft Entra ID authentication for the web app
- modern ChatGPT-like open-source web UI library re-used rather than building raw HTML from scratch

Preferred UI choice:
- Use Chainlit as the web-based chat UI because it is Python-native, chat-oriented, and can be adapted for a ChatGPT-like experience with Entra ID authentication.
- If Chainlit integration becomes too constraining for Entra auth + custom file upload + polished UX, create a small custom FastAPI backend plus Chainlit frontend integration layer, but still reuse Chainlit as much as possible.

Azure hosting preference:
- Azure Container Apps for app hosting
- managed identity wherever possible
- no secrets in code
- Key Vault integration for secrets/config where appropriate

==================================================
BUSINESS SCENARIO
==================================================

This system interviews a person in a fun, reflective, story-driven way to build a strengths/profile card.

The interview should uncover:
- technical strengths
- architecture strengths
- software engineering interests
- cloud/platform knowledge
- collaboration/stakeholder style
- aspirations
- values and motivations
- hobby and side-project signals
- influential people, books, videos, and quotes

The interaction should NOT feel like corporate HR.
It should feel intelligent, playful, reflective, and strengths-oriented.

Example question themes:
- Who are your heroes and why?
- What project are you disproportionately proud of?
- What sort of technical problem makes you lose track of time?
- What do you think about in the shower?
- What side projects have you built evenings/weekends?
- What role do you aspire to?
- What quote, book, talk, or person shaped how you think?
- Tell me you care about craftsmanship without telling me you care about craftsmanship.
- Tell me you’re into systems thinking without saying “systems thinking.”

At the end, generate:
1. a structured textual profile summary
2. a fantasy-style card with:
   - stylized portrait based on uploaded picture
   - title/class/archetype
   - strengths/powers
   - flavor text
   - signature domains
   - optional rarity/theme
This should use Azure OpenAI image generation capability on Azure.

==================================================
CORE ARCHITECTURE
==================================================

Build a clean, maintainable project with these layers:

1. Agent runtime layer
- uses Microsoft Agent Framework for the agent runtime
- uses session-based state management
- supports resumable sessions
- supports workflows where helpful
- includes local DevUI support for debugging
- includes Foundry publishing/deployment hooks or scripts

2. Custom stage framework
- stages are NOT native Agent Framework constructs
- implement them as an application-level abstraction
- stages are defined declaratively in YAML
- stages can be added/removed/edited without changing core orchestration logic
- each stage supports:
  - id
  - title
  - purpose
  - user_experience_goal
  - opening_prompt
  - follow_up_style
  - completion_criteria
  - extraction_targets
  - validation_rules
  - confirmation_required
  - next_stage
  - retry_policy
  - max_turns_before_compaction
  - summarization_policy
  - profile_mapping_rules

3. Memory/state layer
Persist by session_id:
- current stage
- raw transcript
- stage summaries
- extracted facts
- inferred profile signals
- skills matrix
- user confirmation checkpoints
- uploaded image metadata/blob references
- generated card metadata/blob references
- audit timestamps

Implement pluggable persistence:
- default local SQLite
- Azure production store (Cosmos DB or Azure SQL; choose the one that fits best and justify in README)
- Blob Storage for binary assets

4. Compression/summarization layer
Implement guided compression, not generic summarization.
Preserve:
- concrete examples
- motivations and values
- technical domains mentioned
- inferred strengths
- unresolved ambiguities
- evidence snippets
- open questions still needed

Maintain 3 memory layers:
- raw transcript
- distilled stage summary
- durable cross-stage profile memory

5. Inference/profile layer
Infer a profile/skills matrix behind the scenes from conversational evidence.

Skill areas should include:
- identity
- networking
- governance
- infrastructure
- application development
- data
- relational databases
- NoSQL
- graph databases
- AI / ML / GenAI
- containers / orchestration
- security
- performance optimization
- system design
- cloud design patterns
- architecture methods / formal methods
- stakeholder management
- collaboration / influence
- broader software engineering craftsmanship

For each dimension, track:
- score: unknown / emerging / working / strong / expert
- confidence: low / medium / high
- evidence list
- source stages
- missing evidence / gaps

6. Final artifact generation layer
Final stage should produce:
A. textual profile summary
B. stylized card spec
C. image generation prompt
D. generated card asset
E. metadata stored in Blob

Support:
- user uploads a real profile picture
- picture stored in Azure Blob Storage
- image prompt uses the picture as input reference when supported
- if direct reference-image support is unavailable in a chosen flow, isolate the image-generation adapter and implement the best available Azure-compatible path
- save generated image and prompt metadata

==================================================
WEB UI REQUIREMENTS
==================================================

Build a web-based UI that feels modern and chat-centric.

Requirements:
- ChatGPT-like conversational UX
- user can authenticate with Microsoft Entra ID
- user can start/resume sessions
- user can upload a profile picture
- user can see current stage/progress
- user can review and confirm stage summaries
- user can view final profile summary
- user can view/download final card image

Preferred implementation:
- reuse Chainlit as the chat UI foundation
- wrap/adapt it to support:
  - Entra authentication
  - session persistence
  - file upload to Blob
  - current-stage indicator
  - final artifact display

If needed:
- add a thin FastAPI layer for auth/session/blob APIs
- use reverse proxy or middleware as appropriate
- keep architecture simple enough to run in Azure Container Apps

==================================================
AZURE INFRASTRUCTURE
==================================================

Provide full Bicep templates for the Azure stack.

Provision at minimum:
- Resource Group targeting pattern documented in README
- Azure Container Apps Environment
- Azure Container App for backend/UI
- Azure Container Registry
- Log Analytics Workspace
- Application Insights
- Azure Storage Account with Blob containers
- Key Vault
- Managed Identity / User Assigned Managed Identity if useful
- Cosmos DB or Azure SQL for session/profile persistence
- Microsoft Foundry / Azure AI project resources or the required Foundry-compatible Azure resources as far as can reasonably be automated
- role assignments for managed identity access to:
  - Blob Storage
  - App Insights/monitoring as needed
  - Key Vault secrets
  - Foundry/Azure AI resources as needed

Also provide:
- parameters files for dev/test/prod
- outputs for URLs, resource names, managed identity principal IDs, etc.
- notes/TODOs where Foundry deployment steps still require CLI/manual post-provision actions

==================================================
OBSERVABILITY / TELEMETRY
==================================================

Instrumentation must be first-class.

Use OpenTelemetry-based instrumentation throughout and export to Azure Monitor / Application Insights.

Instrument:
- session start/end
- stage enter/exit
- stage completion/failure/retry
- validation loops
- summarization/compression events
- profile inference updates
- image upload events
- image generation events
- final artifact generation
- authentication events where appropriate
- errors/exceptions

Emit traces, structured logs, and metrics.

Important business metrics to expose:
- number of active sessions
- number of users currently in each stage
- average turns per stage
- stage drop-off rates
- time spent per stage
- confirmation rejection rates
- percentage of users reaching final card generation
- image generation failure rate
- resume-session rate

Design telemetry so dashboards can answer:
- how many people are in what stage right now?
- where do users get stuck?
- which stages are too long?
- which prompts produce poor completion?
- how often do people reject the generated summary?

Include:
- OpenTelemetry setup
- correlation IDs
- session_id and stage_id in trace/log attributes
- guidance for Application Insights workbook/dashboard creation

==================================================
FOUNDATION PROJECT STRUCTURE
==================================================

Create a clean structure similar to:

.
├─ pyproject.toml
├─ uv.lock
├─ README.md
├─ .env.example
├─ infra/
│  ├─ main.bicep
│  ├─ modules/
│  │  ├─ container-apps.bicep
│  │  ├─ monitoring.bicep
│  │  ├─ storage.bicep
│  │  ├─ keyvault.bicep
│  │  ├─ database.bicep
│  │  ├─ identities.bicep
│  │  └─ foundry.bicep
│  └─ parameters/
│     ├─ dev.bicepparam
│     ├─ test.bicepparam
│     └─ prod.bicepparam
├─ scripts/
│  ├─ publish_to_foundry.py
│  ├─ seed_local_data.py
│  ├─ create_app_reg_notes.md
│  └─ dev_run.sh
├─ src/
│  └─ profile_agent/
│     ├─ app.py
│     ├─ api/
│     │  ├─ fastapi_app.py
│     │  ├─ auth.py
│     │  ├─ sessions.py
│     │  ├─ uploads.py
│     │  └─ health.py
│     ├─ ui/
│     │  ├─ chainlit_app.py
│     │  ├─ adapters/
│     │  └─ components/
│     ├─ config/
│     │  ├─ settings.py
│     │  ├─ logging.py
│     │  ├─ telemetry.py
│     │  └─ skill_taxonomy.yaml
│     ├─ agents/
│     │  ├─ interview_agent.py
│     │  ├─ evaluator_agent.py
│     │  ├─ summarizer_agent.py
│     │  ├─ profiler_agent.py
│     │  └─ foundry_adapter.py
│     ├─ workflows/
│     │  ├─ interview_workflow.py
│     │  ├─ synthesis_workflow.py
│     │  └─ card_generation_workflow.py
│     ├─ stages/
│     │  ├─ loader.py
│     │  ├─ models.py
│     │  ├─ runner.py
│     │  ├─ transition_engine.py
│     │  └─ definitions/
│     │     ├─ 00_introduction.yaml
│     │     ├─ 10_heroes.yaml
│     │     ├─ 20_influences.yaml
│     │     ├─ 30_proud_projects.yaml
│     │     ├─ 40_shower_thoughts.yaml
│     │     ├─ 50_hobby_projects.yaml
│     │     ├─ 60_aspirations.yaml
│     │     ├─ 70_collaboration.yaml
│     │     ├─ 80_validation.yaml
│     │     └─ 90_card_generation.yaml
│     ├─ memory/
│     │  ├─ base.py
│     │  ├─ session_store.py
│     │  ├─ transcript_store.py
│     │  ├─ profile_store.py
│     │  ├─ asset_store.py
│     │  └─ implementations/
│     │     ├─ sqlite_store.py
│     │     ├─ cosmos_store.py
│     │     └─ blob_store.py
│     ├─ services/
│     │  ├─ conversation_service.py
│     │  ├─ compression_service.py
│     │  ├─ extraction_service.py
│     │  ├─ validation_service.py
│     │  ├─ inference_service.py
│     │  ├─ image_service.py
│     │  ├─ asset_service.py
│     │  ├─ foundry_publish_service.py
│     │  └─ session_service.py
│     ├─ tools/
│     │  ├─ save_memory_tool.py
│     │  ├─ load_session_tool.py
│     │  ├─ stage_status_tool.py
│     │  ├─ confirm_summary_tool.py
│     │  └─ upload_picture_tool.py
│     ├─ prompts/
│     │  ├─ interview/
│     │  ├─ extraction/
│     │  ├─ validation/
│     │  ├─ compression/
│     │  ├─ synthesis/
│     │  └─ card_generation/
│     ├─ models/
│     │  ├─ conversation.py
│     │  ├─ stage_state.py
│     │  ├─ profile.py
│     │  ├─ skill_matrix.py
│     │  ├─ evidence.py
│     │  ├─ assets.py
│     │  └─ llm_contracts.py
│     └─ tests/
│        ├─ test_stage_loader.py
│        ├─ test_transition_engine.py
│        ├─ test_extraction_service.py
│        ├─ test_compression_service.py
│        ├─ test_profile_inference.py
│        ├─ test_image_service.py
│        ├─ test_auth_flow.py
│        └─ test_end_to_end_interview.py

==================================================
CONVERSATION ORCHESTRATION
==================================================

After every user turn, do ALL of the following:
1. append raw turn to transcript
2. extract structured facts from turn
3. validate completion criteria for current stage
4. compute missing information / next best question
5. if context is getting long, run guided compression
6. persist transcript + distilled memory + evidence
7. update inferred profile signals
8. emit telemetry spans/metrics/logs
9. generate next assistant turn
10. if stage complete, present confirmation summary
11. only transition after confirmation or acceptable auto-advance policy

==================================================
FINAL CARD GENERATION
==================================================

The final stage should:
1. produce a structured summary of the person
2. synthesize a “class/archetype”
3. derive 4-8 strengths/powers from evidence
4. create flavor text
5. generate an image prompt for a stylized card

Image concept:
- Pokémon / Magic-like fantasy profile card
- uses the uploaded photo as reference input where supported
- stylize portrait
- include strengths as “abilities” or “powers”
- include title/class
- include affinity/domains
- make it playful but respectful, not childish unless configured

Persist:
- original uploaded image metadata
- prompt used for generation
- model/deployment used
- generated image URL/blob path
- generation timestamp
- optional thumbnail versions

==================================================
SECURITY / AUTH
==================================================

Implement Microsoft Entra ID authentication for the web experience.

Requirements:
- enterprise-style sign-in
- no anonymous production access
- preserve user identity in session metadata
- use managed identity for Azure resource access wherever possible
- use Key Vault for secrets that cannot be replaced by managed identity
- document Entra app registration requirements in README
- document redirect URI setup
- document local-dev auth mode vs Azure-deployed auth mode

==================================================
PROMPT / MODELING REQUIREMENTS
==================================================

Use typed structured outputs via Pydantic models for at least:
- StageExtractionResult
- StageValidationResult
- GuidedCompressionResult
- ProfileSignal
- SkillAssessment
- EvidenceRecord
- SessionSnapshot
- CardSpec
- ImageGenerationRequest
- ImageGenerationResult

Create robust prompt sets for:
- interview behavior
- extraction behavior
- validation behavior
- compression behavior
- synthesis behavior
- card generation behavior

Interview tone:
- intelligent
- reflective
- playful
- strengths-oriented
- not HR-ish
- not robotic
- story-driven
- “show, don’t tell”

==================================================
DEV / PROD EXPERIENCE
==================================================

Support:
- local development with DevUI
- local SQLite fallback
- optional local mock blob/image mode
- Azure production deployment
- Foundry publishing/deployment script
- clear README commands using uv
- linting/formatting/typing/tests

README must explain:
- how to bootstrap with uv
- how to run locally
- how to run Chainlit/FastAPI locally
- how to configure Entra auth
- how to deploy infra with Bicep
- how to deploy app container
- how to publish/register/deploy the agent to the new Microsoft Foundry
- how to configure Blob Storage
- how the session persistence works
- how to add/edit stages
- how telemetry is emitted and queried
- how final card generation works

==================================================
QUALITY BAR
==================================================

Write this as if a senior/staff engineer will maintain it.
Prioritize:
- modularity
- strong typing
- extensibility
- enterprise clarity
- thin wrappers around fast-changing SDKs
- realistic Azure patterns
- observability by default
- well-factored infrastructure code

Add TODO comments only where genuinely necessary, especially for:
- specific Foundry SDK publish nuances that may evolve
- exact Azure image-generation deployment names
- dashboard/workbook hardening
- future admin analytics UI

==================================================
DELIVERABLES
==================================================

Generate the complete project:
- source code
- Bicep templates
- config files
- YAML stage files
- auth integration scaffolding
- telemetry scaffolding
- tests
- README
- deployment scripts
- sample session data
- sample generated card spec
- sample dashboard/query notes for Application Insights / Log Analytics

After generating the project, also provide:
1. architecture overview
2. file-by-file explanation
3. uv commands
4. Azure deployment steps
5. Foundry publish/deploy steps
6. where to change/add stages
7. how telemetry metrics map to business questions