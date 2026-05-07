```
   ┌─────────────────────────────────────────────────┐
   │  ╔═╗╦╔═╦╦  ╦    ╔╦╗╔═╗╔═╗╦╔═                  │
   │  ╚═╗╠╩╗║║  ║     ║║║╣ ║  ╠╩╗                   │
   │  ╚═╝╩ ╩╩╩═╝╩═╝  ═╩╝╚═╝╚═╝╩ ╩                  │
   │                                                 │
   │  interview agent → strengths profile card       │
   │  think pokémon card meets professional profile  │
   └─────────────────────────────────────────────────┘
        ╱╲    ╱╲    built with azure ai foundry
       ╱  ╲  ╱  ╲   react • fastapi • bicep
      ╱    ╲╱    ╲
```

AI-powered conversational agent that discovers your unique technical strengths through a 10-stage interview, then generates a collectible-style profile card.

## Getting Started

**Install:**

| Tool | Install |
|------|---------|
| [Python 3.12+](https://python.org) | `winget install Python.Python.3.12` |
| [uv](https://docs.astral.sh/uv/) | `winget install astral-sh.uv` |
| [Node.js 22+](https://nodejs.org) | `winget install OpenJS.NodeJS` |

**Configure:**

```sh
cp .env.example .env     # fill in FOUNDRY_PROJECT_ENDPOINT + model name
az login                  # for DefaultAzureCredential
```

**Run:**

```sh
.\scripts\dev.ps1        # → http://localhost:8000
```

**Test:**

```sh
uv run --extra dev python -m pytest tests/ -v
cd frontend && npm run lint && npm run build
```

## License

MIT — see [LICENSE](LICENSE).
