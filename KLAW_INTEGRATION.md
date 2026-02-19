# klaw Integration — Web365 ClawBot

Hybrid integration between [klaw](https://github.com/SSaksit23/klaw.sh) (kubectl for AI Agents) and Web365 ClawBot's Python agent system.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                     klaw Control Plane                            │
│                                                                    │
│  CLI: klaw get agents    Slack: @klaw status    Cron: scheduler  │
│                                                                    │
│  ┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐     │
│  │   FINANCE ns    │ │  RESEARCH ns    │ │ OPERATIONS ns   │     │
│  │  accounting-    │ │  data-analysis- │ │  executive-     │     │
│  │  agent          │ │  agent          │ │  agent          │     │
│  │                 │ │  market-        │ │  admin-agent    │     │
│  │                 │ │  analysis-agent │ │                 │     │
│  └────────┬────────┘ └────────┬────────┘ └────────┬────────┘     │
└───────────┼────────────────────┼────────────────────┼─────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌──────────────────────────────────────────────────────────────────┐
│                  klaw ↔ ClawBot Bridge (:9100)                    │
│  POST /dispatch        POST /dispatch/sync        GET /health    │
└──────────────────────────────────────────────────────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌──────────────────────────────────────────────────────────────────┐
│               ClawBot Python Agent System                         │
│                                                                    │
│  agents/cli_runner.py  →  accounting_agent.py                     │
│                        →  data_analysis_agent.py                  │
│                        →  market_analysis_agent.py                │
│                        →  executive_agent.py                      │
│                        →  admin_agent.py                          │
│                                                                    │
│  tools/browser_tools.py  ─→  qualityb2bpackage.com               │
│  services/expense_service.py                                      │
│  services/document_parser.py                                      │
└──────────────────────────────────────────────────────────────────┘
            │
            ▼
┌──────────────────────────────────────────────────────────────────┐
│               Flask-SocketIO Web UI (:5000)                       │
│               (existing chat interface — unchanged)               │
└──────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Install klaw

```bash
# Linux/macOS
curl -fsSL https://klaw.sh/install.sh | sh

# Or build from source
git clone https://github.com/SSaksit23/klaw.sh.git
cd klaw.sh && make build
sudo mv bin/klaw /usr/local/bin/
```

### 2. Run the setup helper

```bash
python klaw_setup.py install
```

### 3. Start the bridge

```bash
python klaw_bridge.py
```

### 4. Register agents with klaw

```bash
klaw apply -f klaw_agents/accounting-agent.yaml
klaw apply -f klaw_agents/data-analysis-agent.yaml
klaw apply -f klaw_agents/market-analysis-agent.yaml
klaw apply -f klaw_agents/executive-agent.yaml
klaw apply -f klaw_agents/admin-agent.yaml
```

### 5. Set up schedules

```bash
klaw apply -f klaw_agents/schedules.yaml
```

## Usage

### CLI — Run agents directly

```bash
# List available agents
python -m agents.cli_runner --list-agents

# Run accounting agent
python -m agents.cli_runner --agent accounting \
  --task '{"action":"process","parameters":{"tour_code":"BTMYSP16N240107","amount":1000}}'

# Run data analysis
python -m agents.cli_runner --agent data_analysis \
  --task '{"action":"scrape","parameters":{"analysis_type":"all"}}'

# Run market analysis
python -m agents.cli_runner --agent market_analysis \
  --task '{"action":"analyze","parameters":{"destination":"Japan"}}'

# Generate executive report
python -m agents.cli_runner --agent executive \
  --task '{"action":"generate_report"}'

# Admin: list expenses
python -m agents.cli_runner --agent admin \
  --task '{"action":"list_expenses"}'
```

### klaw CLI — Orchestrated management

```bash
# List all agents
klaw get agents

# Check specific agent
klaw describe agent accounting-agent

# View logs
klaw logs market-analysis-agent --follow

# Dispatch a task
klaw dispatch "analyze Japan travel packages" --agent market-analysis-agent

# View scheduled jobs
klaw cron list

# Manually trigger a scheduled job
klaw cron trigger weekly-executive-report
```

### Slack — Control from chat

```
@klaw status
@klaw run market-analysis-agent
@klaw ask executive-agent "generate weekly report"
@klaw cron list
@klaw logs accounting-agent
```

### Bridge HTTP API

```bash
# Health check
curl http://localhost:9100/health

# List agents
curl http://localhost:9100/agents

# Async dispatch (returns job ID, poll for result)
curl -X POST http://localhost:9100/dispatch \
  -H "Content-Type: application/json" \
  -d '{"agent":"executive-agent","task":{"action":"generate_report"}}'

# Sync dispatch (waits for result)
curl -X POST http://localhost:9100/dispatch/sync \
  -H "Content-Type: application/json" \
  -d '{"agent":"admin-agent","task":{"action":"list_expenses"}}'

# Check job status
curl http://localhost:9100/jobs/<job_id>
```

## File Structure

```
web365-clawbot/
├── klaw_config.toml              # klaw configuration (namespaces, providers)
├── klaw_bridge.py                # HTTP bridge: klaw → Python agents
├── klaw_setup.py                 # Setup helper (install, status, demo)
├── KLAW_INTEGRATION.md           # This file
│
├── klaw_agents/                  # klaw agent & schedule definitions
│   ├── accounting-agent.yaml
│   ├── data-analysis-agent.yaml
│   ├── market-analysis-agent.yaml
│   ├── executive-agent.yaml
│   ├── admin-agent.yaml
│   └── schedules.yaml
│
├── agents/
│   ├── cli_runner.py             # CLI entry point (klaw invokes this)
│   ├── __main__.py               # python -m agents support
│   ├── assignment_agent.py       # (unchanged — WebSocket routing)
│   ├── accounting_agent.py       # (unchanged)
│   ├── data_analysis_agent.py    # (unchanged)
│   ├── market_analysis_agent.py  # (unchanged)
│   ├── executive_agent.py        # (unchanged)
│   └── admin_agent.py            # (unchanged)
│
├── main.py                       # Flask-SocketIO server (unchanged)
└── ...
```

## Scheduled Jobs

| Job | Schedule | Agent | Description |
|-----|----------|-------|-------------|
| `daily-booking-scrape` | 08:00 daily | data-analysis-agent | Scrape booking data & seller reports |
| `daily-market-scan` | 09:00 daily | market-analysis-agent | Catalog scan & competitive analysis |
| `weekly-executive-report` | Mon 08:30 | executive-agent | Aggregate all data into executive report |
| `hourly-expense-check` | Every hour | admin-agent | Snapshot of latest expense records (disabled by default) |

## Namespace Isolation

| Namespace | Agents | Secrets | Tools |
|-----------|--------|---------|-------|
| **finance** | accounting-agent | OPENAI_API_KEY, WEBSITE_* | browser_tools, data_tools |
| **research** | data-analysis-agent, market-analysis-agent | OPENAI_API_KEY, WEBSITE_*, EXA_API_KEY | browser_tools, itinerary_tools |
| **operations** | executive-agent, admin-agent | OPENAI_API_KEY, WEBSITE_* | browser_tools, analysis_tools |

## Running Both Systems

The existing Flask/SocketIO chat UI and klaw orchestration run side-by-side:

```bash
# Terminal 1: existing web chat interface
python main.py

# Terminal 2: klaw bridge server
python klaw_bridge.py

# Terminal 3: klaw platform (Slack + scheduler)
klaw start
```

The web chat UI uses the same Python agents through the `AssignmentAgent` router. klaw uses the same agents through the `cli_runner.py` bridge. Both paths are supported simultaneously.
