# Web365 ClawBot

A multi-agent system that automates travel operations on [qualityb2bpackage.com](https://www.qualityb2bpackage.com/) -- expense recording, data analysis, market intelligence, and executive reporting -- all through a real-time chat interface.

## Features

- **Multi-Agent Architecture** -- Six specialist agents coordinated by a central Assignment Agent that routes user requests via natural language understanding (OpenAI).
- **Expense Automation** -- Upload a CSV, Excel, or PDF invoice and the system extracts line items, detects currency, logs into the website, fills the charges form, and submits automatically.
- **Itinerary Analysis** -- Parse travel itinerary PDFs, compare multiple itineraries side-by-side, and run a full market intelligence pipeline.
- **Self-Improving** -- Agents log learnings, errors, and best practices to markdown files and consult them before future tasks.
- **Multi-User** -- Each user signs in with their own website credentials and gets an isolated browser session. Supports up to 10 concurrent users.
- **Cloud-Ready** -- Dockerfile and one-command deployment script for Google Cloud Run.

## Architecture

```
                            +-------------------+
                            | Assignment Agent  |  <-- Central coordinator
                            +--------+----------+
                                     |
         +------------+---------+----+----+---------+------------+
         |            |         |         |         |            |
   Accounting    Data Analyst  Market   Admin    Executive    (General)
     Agent         Agent       Agent    Agent     Agent
         |            |         |         |         |
         +-----+------+---------+---------+---------+
               |
        +------+-------+
        | Browser Pool |  <-- Per-user Chromium instances
        +--------------+
               |
    qualityb2bpackage.com
```

### Agents

| Agent | Purpose |
|-------|---------|
| **Assignment** | Classifies intent and delegates to the right specialist |
| **Accounting** | Automates expense form filling and submission |
| **Data Analysis** | Scrapes bookings and seller reports |
| **Market Analysis** | Analyses travel packages, pricing, and trends |
| **Admin** | Lists and searches existing records |
| **Executive** | Aggregates everything into a strategic report |

### Services

| Service | Purpose |
|---------|---------|
| `expense_service` | 7-step expense recording workflow |
| `document_parser` | Extracts structured data from CSV/Excel/PDF/DOCX via LLM |
| `itinerary_analyzer` | Itinerary parsing, comparison, and market intelligence |
| `learning_service` | Self-improving agent memory (learnings, errors, feature requests) |
| `n8n_integration` | Optional workflow automation via n8n webhooks |

## Quick Start

### Prerequisites

- Python 3.11+
- An OpenAI API key
- A qualityb2bpackage.com account

### Install

```bash
git clone https://github.com/SSaksit23/claw-assistant.git
cd claw-assistant

pip install -r requirements.txt
playwright install chromium
```

### Configure

Create a `.env` file in the project root:

```env
OPENAI_API_KEY=sk-...

# Optional: set defaults for single-user local development
WEBSITE_USERNAME=your_username
WEBSITE_PASSWORD=your_password

# Browser
HEADLESS_MODE=True
BROWSER_TIMEOUT=30000

# Flask
SECRET_KEY=change-me-in-production
FLASK_ENV=development
FLASK_DEBUG=True
FLASK_PORT=5000
```

> In multi-user mode (Cloud Run), each user enters their own website credentials on the login page. The `WEBSITE_USERNAME` / `WEBSITE_PASSWORD` env vars are only used as fallback defaults.

### Run

```bash
python main.py
```

Open [http://localhost:5000](http://localhost:5000). You'll see a login page -- enter your qualityb2bpackage.com credentials, then use the chat to interact with the agents.

## Project Structure

```
web365-clawbot/
├── main.py                      # Entry point (Flask-SocketIO + eventlet)
├── config.py                    # Centralized configuration from .env
├── requirements.txt             # Python dependencies
├── Dockerfile                   # Production container image
├── deploy.sh                    # Google Cloud Run deployment script
├── .env                         # Environment variables (not committed)
│
├── agents/                      # Multi-agent system
│   ├── assignment_agent.py      #   Central coordinator / intent router
│   ├── accounting_agent.py      #   Expense recording automation
│   ├── data_analysis_agent.py   #   Booking & report extraction
│   ├── market_analysis_agent.py #   Travel package analysis
│   ├── admin_agent.py           #   Record management & lookups
│   └── executive_agent.py       #   Executive intelligence reports
│
├── services/                    # Business logic
│   ├── expense_service.py       #   7-step expense workflow
│   ├── document_parser.py       #   CSV/Excel/PDF/DOCX parsing + LLM
│   ├── itinerary_analyzer.py    #   Itinerary analysis & comparison
│   ├── learning_service.py      #   Self-improving agent memory
│   └── n8n_integration.py       #   n8n workflow integration
│
├── tools/                       # Reusable utilities
│   ├── browser_manager.py       #   Per-session Chromium pool
│   ├── browser_tools.py         #   Playwright automation helpers
│   ├── itinerary_tools.py       #   Itinerary analysis tools
│   ├── analysis_tools.py        #   Data aggregation utilities
│   └── data_tools.py            #   CSV/Excel processing
│
└── app/                         # Flask web application
    ├── __init__.py              #   App factory + session config
    ├── routes.py                #   HTTP routes + auth + REST API
    ├── websocket.py             #   WebSocket event handlers
    ├── templates/
    │   ├── login.html           #   Login page
    │   └── chat.html            #   Chat interface
    └── static/
        ├── css/chat.css
        └── js/chat.js
```

## REST API

All API endpoints are available at `/api/*`. The n8n integration uses these for workflow automation.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/expenses` | Create a single expense record |
| `POST` | `/api/batch-expenses` | Batch process multiple expenses |
| `POST` | `/api/parse` | Parse an uploaded file (no submission) |
| `GET`  | `/api/packages` | List travel packages |
| `POST` | `/api/itinerary/analyze` | Analyse a single itinerary |
| `POST` | `/api/itinerary/compare` | Compare multiple itineraries |
| `POST` | `/api/itinerary/market-intelligence` | Full market intelligence pipeline |
| `GET`  | `/api/export/<job_id>` | Download CSV report for a job |
| `GET`  | `/health` | Health check (no auth required) |

## Deploy to Google Cloud Run

### Prerequisites

- [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) installed and authenticated
- A GCP project with billing enabled

### Deploy

```bash
# Set your project and OpenAI key
gcloud config set project YOUR_PROJECT_ID
export OPENAI_API_KEY=sk-...

# Deploy (builds container in the cloud + deploys to Cloud Run)
bash deploy.sh
```

This deploys with:
- 4 GB memory, 2 vCPUs
- 1 always-on instance (no cold starts)
- Session affinity (sticky WebSocket connections)
- HTTPS automatically provided by Cloud Run

### Configuration

Environment variables are set via Cloud Run. To update after deployment:

```bash
gcloud run services update clawbot \
  --region asia-southeast1 \
  --set-env-vars "OPENAI_API_KEY=sk-new-key"
```

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | Yes | Shared OpenAI API key |
| `SECRET_KEY` | Yes | Session encryption key (auto-generated on first deploy) |
| `HEADLESS_MODE` | No | `True` (default in production) |
| `MAX_BROWSER_INSTANCES` | No | Max concurrent browsers (default: 10) |
| `BROWSER_IDLE_TIMEOUT` | No | Browser idle timeout in seconds (default: 1800) |

## How It Works

### Expense Recording Flow

1. User uploads a PDF/CSV invoice via the chat
2. **Document Parser** extracts line items using LLM (detects currency, charge types)
3. **Accounting Agent** launches a browser, logs into qualityb2bpackage.com
4. For each tour group: navigates to the charges form, selects the program, fills expenses, submits
5. Returns a summary table with order numbers and a downloadable CSV report

### Multi-User Sessions

Each user who logs in gets:
- An encrypted session cookie (8-hour lifetime)
- Their own isolated Chromium browser instance
- Independent login state on qualityb2bpackage.com

The browser pool evicts idle sessions after 30 minutes and enforces a max of 10 concurrent browsers.

## Dependencies

| Package | Purpose |
|---------|---------|
| Flask + Flask-SocketIO | Web framework + real-time WebSocket |
| eventlet | Async networking for SocketIO |
| Playwright | Browser automation (Chromium) |
| OpenAI | LLM for intent classification and document parsing |
| pandas | Data manipulation |
| pdfplumber / PyMuPDF | PDF text extraction |
| python-docx / openpyxl | DOCX and Excel file handling |
| exa-py | Web research for market intelligence (optional) |

## License

Private -- internal use only.
