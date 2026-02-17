# Agent Skills Integration Guide

**Version:** 1.0

**Date:** 2026-02-16

**Author:** Manus AI

---

## 1. Overview

This guide provides a comprehensive overview of the four specialized agent skills and how they integrate within the multi-agent system. Each skill is designed to be modular, reusable, and independently testable while working seamlessly together in the overall workflow.

---

## 2. Agent Skills Summary

### 2.1 Data Analysis Agent Skill

**Location:** `/home/ubuntu/skills/data_analysis_agent/SKILL.md`

**Purpose:** Extract and validate booking and financial data from the QualityB2BPackage website.

**Key Responsibilities:**
- Retrieve booking records from `/booking` endpoint
- Extract seller performance reports from `/report/report_seller` endpoint
- Validate and standardize all data
- Store cleaned data in structured format (JSON/CSV)

**Tools Required:**
- BrowserAutomationTool
- DataExtractionTool
- DataValidationTool
- FileTool
- DateTimeTool

**Output:** Structured JSON with booking data and report data

**Execution Order:** First (Layer 1 - Data Collection)

---

### 2.2 Market Analysis Agent Skill

**Location:** `/home/ubuntu/skills/market_analysis_agent/SKILL.md`

**Purpose:** Analyze market trends, competitive landscape, and product positioning.

**Key Responsibilities:**
- Analyze own products from `/travelpackage` endpoint
- Perform competitive market research
- Identify market trends and opportunities
- Evaluate pricing strategies and recommendations

**Tools Required:**
- BrowserAutomationTool
- WebScrapingTool
- DataAnalysisTool
- ComparisonTool
- VisualizationTool

**Output:** Market analysis with competitive positioning and recommendations

**Execution Order:** Second (Layer 1 - Data Collection)

**Dependencies:** Uses output from Data Analysis Agent

---

### 2.3 Accounting Agent Skill

**Location:** `skill/accounting_agent/SKILL.md`

**Purpose:** Receive financial documents, perform financial analysis (price verification, date validation, currency checks), standardise data into a structured JSON schema, and route results to the Admin Agent (for expense registration) or Data Analysis Agent (for reporting).

**Key Responsibilities:**
- Receive invoices/receipts/confirmations from the Assignment Agent (PDF, DOCX, XLSX, images)
- Extract text using OCR and file parsers
- Perform financial validation (line-item totals, date logic, currency codes, duplicate detection)
- Standardise data into the Standardised Invoice JSON Schema
- Translate descriptions (Chinese/Thai → English)
- Classify and route: `expense_register` → Admin Agent, `analysis_only` → Data Analysis Agent

**Core Workflow (4 Steps):**
1. **Receive** — Accept file or data from Assignment Agent
2. **Analyse** — Extract text, validate prices/dates/currencies/totals
3. **Define** — Map to standardised JSON, translate, classify expense type
4. **Route** — Send to Admin Agent (for web registration) or Data Analysis Agent (for reporting)

**Tools Required:**
- ReceiveDocumentTool
- ExtractTextTool (pdfplumber, python-docx, openpyxl, pytesseract)
- FinancialAnalysisTool (LLM-powered validation)
- CurrencyValidationTool
- StandardiseInvoiceTool
- TranslateFieldsTool
- ClassifyExpenseTool
- RouteToAdminTool
- RouteToAnalysisTool
- SaveFinancialRecordTool

**Output:** Standardised invoice JSON with analysis results and routing decision

**Execution Order:** Second (Layer 2 - Financial Intelligence)

**Dependencies:** Receives tasks from Assignment Agent; routes expense data to Admin Agent

---

### 2.4 Admin Agent Skill

**Location:** `skill/admin_agent/SKILL.md`

**Purpose:** Execute browser-based administrative operations — register expenses on the website, manage tour packages, and validate data integrity.

**Key Responsibilities:**
- **Receive pre-analysed expense data from the Accounting Agent** and register it on `/charges_group/create`
- Manage tour-package listings on `/travelpackage`
- Perform batch CSV processing for expense records
- Validate data integrity between source files and website records
- Handle Bootstrap selectpicker dropdowns via hybrid JavaScript injection

**Tools Required:**
- LoginTool
- NavigateToPageTool
- SetDateRangeFilterTool
- SelectProgramAndTourTool
- FillChargesFormTool
- SubmitFormTool
- ExtractExpenseNumberTool
- ManageTourPackageTool
- ExtractPackageListTool
- LoadCSVTool
- DataIntegrityCheckTool
- CloseBrowserTool

**Output:** Expense creation results (with expense numbers), package management results, and data integrity reports

**Execution Order:** Third (Layer 3 - Operational Execution)

**Dependencies:** Receives `expense_register` routed data from the **Accounting Agent**; receives direct tasks from the Assignment Agent

---

### 2.5 Executive Agent Skill

**Location:** `skill/executive_agent/SKILL.md`

**Purpose:** Aggregate data and generate strategic insights and recommendations.

**Key Responsibilities:**
- Aggregate outputs from all other agents
- Perform financial and business performance analysis
- Generate comprehensive reports
- Develop actionable recommendations

**Tools Required:**
- DataAggregationTool
- AnalysisEngine
- VisualizationTool
- ReportGenerationTool
- RecommendationEngine

**Output:** Executive report with strategic insights and recommendations

**Execution Order:** Fourth (Layer 3 - Strategic Intelligence)

**Dependencies:** Uses outputs from all other agents

---

## 3. Workflow Integration

### 3.1 Complete Workflow Sequence

```
START (LINE Trigger / File Upload)
    ↓
[1. Data Analysis Agent]  ─── Layer 1: Data Collection
├─ Extract booking data
├─ Extract report data
└─ Output: booking_data.json
    ↓
[2. Market Analysis Agent]  ─── Layer 1: Data Collection
├─ Analyze own products
├─ Research competitors
└─ Output: market_analysis.json
    ↓
[3. Accounting Agent]  ─── Layer 2: Financial Intelligence
├─ RECEIVE: invoice/receipt from Assignment Agent
├─ ANALYSE: extract text, validate prices/dates/currencies
├─ DEFINE: standardise to JSON, translate, classify
├─ ROUTE:
│   ├─ expense_register → Admin Agent
│   └─ analysis_only   → Data Analysis Agent
└─ Output: financial_records.json
    ↓
[4. Admin Agent]  ─── Layer 3: Operational Execution
├─ Receive expense_data from Accounting Agent
├─ Fill & submit charges form on website
├─ Manage tour packages
├─ Validate data integrity
└─ Output: admin_records.json
    ↓
[5. Executive Agent]  ─── Layer 4: Strategic Intelligence
├─ Aggregate all data
├─ Perform analysis
└─ Output: executive_report.json
    ↓
LINE Bot
├─ Format report
└─ Send to user
    ↓
END (Report delivered to user)
```

### 3.2 Data Flow Between Agents

```
User uploads file (invoice/receipt/CSV) via LINE
    ↓
Assignment Agent
├─ Detects intent: financial document
└─ Delegates to Accounting Agent
    ↓
Accounting Agent (Layer 2: Financial Intelligence)
├─ RECEIVE → ANALYSE → DEFINE → ROUTE
├─ expense_register ──→ Admin Agent (Layer 3)
│                       ├─ Fill charges form on website
│                       └─ admin_records.json ──────────────┐
├─ analysis_only ──→ Data Analysis Agent (Layer 1)          │
│                   ├─ booking_data.json ──────────────────┐│
│                   └─→ Market Analysis Agent              ││
│                       └─ market_analysis.json ──────────┐││
└─ financial_records.json ───────────────────────────────┐│││
                                                         ↓↓↓↓
                                                    Executive Agent (Layer 4)
                                                    └─ executive_report.json
                                                        ↓
                                                    LINE Bot
                                                        ↓
                                                    User
```

---

## 4. Implementation Steps

### Step 1: Set Up Agent Definitions

Define each agent with its specific role, goal, and backstory as specified in each skill:

```python
from crewai import Agent

# Data Analysis Agent
data_analysis_agent = Agent(
    role="Data Retrieval Specialist",
    goal="Extract and validate comprehensive booking and financial data.",
    backstory="An experienced data analyst...",
    tools=[booking_scraper, report_parser, data_validator],
    verbose=True
)

# Market Analysis Agent
market_analysis_agent = Agent(
    role="Market Intelligence Specialist",
    goal="Provide comprehensive competitive intelligence and market insights.",
    backstory="A seasoned market analyst...",
    tools=[product_analyzer, competitor_research, trend_analyzer],
    verbose=True
)

# Accounting Agent
accounting_agent = Agent(
    role="Financial Intelligence Specialist",
    goal="Receive financial documents, perform analysis, standardise data, and route to Admin or Data Analysis.",
    backstory="A senior financial analyst with deep expertise in travel-industry accounting...",
    tools=[receive_document, extract_text, financial_analysis, currency_validation,
           standardise_invoice, translate_fields, classify_expense,
           route_to_admin, route_to_analysis, save_financial_record],
    verbose=True
)

# Admin Agent
admin_agent = Agent(
    role="Administrative Operations Specialist",
    goal="Automate administrative record-keeping, tour-package management, and data-entry tasks.",
    backstory="A meticulous administrative professional...",
    tools=[navigate_page, set_date_range, select_program_tour, fill_charges_form,
           submit_form, extract_expense_no, manage_package, extract_package_list,
           load_csv, integrity_check],
    verbose=True
)

# Executive Agent
executive_agent = Agent(
    role="Executive Intelligence Officer",
    goal="Provide comprehensive business intelligence and actionable recommendations.",
    backstory="A strategic business analyst...",
    tools=[data_aggregator, analysis_engine, report_generator, recommendation_engine],
    verbose=True
)
```

### Step 2: Define Tasks for Each Agent

Create tasks that align with each agent's responsibilities:

```python
from crewai import Task

# Task 1: Data Extraction
data_extraction_task = Task(
    description="Extract booking data and financial reports from the QualityB2BPackage website.",
    expected_output="Structured booking and report data in JSON format.",
    agent=data_analysis_agent,
    output_file="booking_data.json"
)

# Task 2: Market Analysis
market_analysis_task = Task(
    description="Analyze own products and competitive market landscape.",
    expected_output="Comprehensive market analysis with competitive positioning.",
    agent=market_analysis_agent,
    output_file="market_analysis.json"
)

# Task 3: Financial Analysis & Routing
financial_analysis_task = Task(
    description="Receive financial documents, extract data, validate prices/dates/currencies, standardise to JSON, and route to Admin Agent (expense_register) or Data Analysis Agent (analysis_only).",
    expected_output="Standardised invoice JSON with analysis results and routing decision.",
    agent=accounting_agent,
    output_file="financial_records.json"
)

# Task 4: Administrative Record-Keeping
admin_record_task = Task(
    description="Create charge records, manage packages, and validate data integrity.",
    expected_output="Admin records with expense numbers and integrity report.",
    agent=admin_agent,
    output_file="admin_records.json"
)

# Task 5: Executive Reporting
executive_reporting_task = Task(
    description="Aggregate all data and generate executive report with recommendations.",
    expected_output="Executive summary with actionable insights.",
    agent=executive_agent,
    output_file="executive_report.json"
)
```

### Step 3: Create the Crew

Combine all agents and tasks into a crew with sequential processing:

```python
from crewai import Crew, Process

crew = Crew(
    agents=[
        data_analysis_agent,
        market_analysis_agent,
        accounting_agent,
        admin_agent,
        executive_agent
    ],
    tasks=[
        data_extraction_task,
        market_analysis_task,
        financial_analysis_task,
        admin_record_task,
        executive_reporting_task
    ],
    process=Process.sequential,
    verbose=True
)
```

### Step 4: Execute the Crew

Trigger the crew execution from the LINE webhook:

```python
def trigger_crew_execution():
    result = crew.kickoff()
    return result
```

---

## 5. Tool Requirements by Agent

### 5.1 Data Analysis Agent Tools

| Tool Name | Purpose | Implementation |
| :--- | :--- | :--- |
| **BrowserAutomationTool** | Navigate web pages | Playwright-based |
| **DataExtractionTool** | Parse HTML/JSON | BeautifulSoup/Regex |
| **DataValidationTool** | Check data quality | Custom validation logic |
| **FileTool** | Read/write files | Python file I/O |
| **DateTimeTool** | Handle dates | Python datetime |

### 5.2 Market Analysis Agent Tools

| Tool Name | Purpose | Implementation |
| :--- | :--- | :--- |
| **BrowserAutomationTool** | Navigate websites | Playwright-based |
| **WebScrapingTool** | Extract product data | BeautifulSoup/Selenium |
| **DataAnalysisTool** | Statistical analysis | Pandas/NumPy |
| **ComparisonTool** | Compare products | Custom comparison logic |
| **VisualizationTool** | Create charts | Matplotlib/Plotly |

### 5.3 Accounting Agent Tools

| Tool Name | Purpose | Implementation |
| :--- | :--- | :--- |
| **ReceiveDocumentTool** | Accept files from Assignment Agent | Python file I/O |
| **ExtractTextTool** | Extract text from documents | pdfplumber, python-docx, openpyxl, pytesseract |
| **FinancialAnalysisTool** | Validate prices, dates, currencies | LLM-powered analysis |
| **CurrencyValidationTool** | ISO 4217 validation, exchange rates | Custom + external API |
| **StandardiseInvoiceTool** | Map data to JSON schema | LLM + Pydantic models |
| **TranslateFieldsTool** | Translate descriptions to English | LLM (OpenAI) |
| **ClassifyExpenseTool** | Classify and determine routing | LLM + rule-based logic |
| **RouteToAdminTool** | Send expense data to Admin Agent | Inter-agent messaging |
| **RouteToAnalysisTool** | Send data to Data Analysis Agent | Inter-agent messaging |
| **SaveFinancialRecordTool** | Persist processed records | Python file I/O (JSON) |

### 5.4 Admin Agent Tools

| Tool Name | Purpose | Implementation |
| :--- | :--- | :--- |
| **LoginTool** | Authenticate with website | Playwright-based |
| **NavigateToPageTool** | Navigate to target pages | Playwright navigation |
| **SetDateRangeFilterTool** | Set date filter inputs | Playwright fill |
| **SelectProgramAndTourTool** | Handle Bootstrap selectpicker | jQuery injection |
| **FillChargesFormTool** | Fill charges form fields | Playwright + JS injection |
| **SubmitFormTool** | Submit forms | Playwright click |
| **ExtractExpenseNumberTool** | Capture expense numbers | CSS selector + regex |
| **ManageTourPackageTool** | CRUD for tour packages | Playwright-based |
| **ExtractPackageListTool** | Scrape package table | Playwright + parsing |
| **LoadCSVTool** | Load/validate CSV input | Python csv/pandas |
| **DataIntegrityCheckTool** | Cross-validate data | Custom comparison logic |
| **CloseBrowserTool** | Close browser session | Playwright cleanup |

### 5.5 Executive Agent Tools

| Tool Name | Purpose | Implementation |
| :--- | :--- | :--- |
| **DataAggregationTool** | Combine data sources | Pandas merge/concat |
| **AnalysisEngine** | Perform analysis | Pandas/NumPy/SciPy |
| **VisualizationTool** | Create dashboards | Matplotlib/Plotly |
| **ReportGenerationTool** | Generate reports | Jinja2/ReportLab |
| **RecommendationEngine** | Generate insights | Custom ML/heuristics |

---

## 6. Configuration and Environment Variables

### 6.1 Agent-Specific Configuration

```python
# config.py

AGENT_CONFIG = {
    "data_analysis": {
        "enabled": True,
        "timeout": 300,
        "max_iterations": 20,
        "verbose": True
    },
    "market_analysis": {
        "enabled": True,
        "timeout": 300,
        "max_iterations": 20,
        "verbose": True
    },
    "accounting": {
        "enabled": True,
        "timeout": 300,
        "max_iterations": 20,
        "verbose": True
    },
    "admin": {
        "enabled": True,
        "timeout": 300,
        "max_iterations": 25,
        "verbose": True
    },
    "executive": {
        "enabled": True,
        "timeout": 300,
        "max_iterations": 20,
        "verbose": True
    }
}
```

### 6.2 Environment Variables

```bash
# Data Analysis Agent
DATA_AGENT_ENABLED=True
BOOKING_PAGE_URL=https://www.qualityb2bpackage.com/booking
REPORT_PAGE_URL=https://www.qualityb2bpackage.com/report/report_seller

# Market Analysis Agent
MARKET_AGENT_ENABLED=True
PRODUCT_PAGE_URL=https://www.qualityb2bpackage.com/travelpackage
MARKET_RESEARCH_ENABLED=True

# Accounting Agent
ACCOUNTING_AGENT_ENABLED=True
CHARGES_FORM_URL=https://www.qualityb2bpackage.com/charges_group/create

# Admin Agent
ADMIN_AGENT_ENABLED=True
ADMIN_CHARGES_URL=https://www.qualityb2bpackage.com/charges_group/create
ADMIN_PACKAGE_URL=https://www.qualityb2bpackage.com/travelpackage
ADMIN_BOOKING_URL=https://www.qualityb2bpackage.com/booking

# Executive Agent
EXECUTIVE_AGENT_ENABLED=True
REPORT_GENERATION_ENABLED=True
```

---

## 7. Error Handling and Recovery

### 7.1 Agent-Level Error Handling

Each agent should implement error handling for its specific domain:

**Data Analysis Agent:**
- Handle network timeouts when fetching data
- Validate data completeness and flag missing fields
- Retry failed extractions with exponential backoff

**Market Analysis Agent:**
- Handle blocked requests from competitor sites
- Manage rate limiting for web scraping
- Use cached data when live data is unavailable

**Accounting Agent:**
- Handle unsupported file formats gracefully
- Retry text extraction with OCR fallback if primary parser fails
- Retry LLM calls once with more explicit prompts on malformed output
- Block routing only on critical validation errors (missing grand_total, unknown currency)
- Attach all warnings/errors to output so downstream agents are aware
- Save pending records if destination agent is unavailable

**Admin Agent:**
- Retry login and form submissions with exponential backoff
- Take screenshots on every error for debugging
- Validate CSV rows before processing (skip invalid, log reason)
- Handle Bootstrap selectpicker failures with jQuery injection retry
- Report data integrity discrepancies without auto-correcting

**Executive Agent:**
- Handle missing data from other agents
- Validate analysis results
- Provide fallback recommendations

### 7.2 Crew-Level Error Handling

```python
try:
    result = crew.kickoff()
except Exception as e:
    logger.error(f"Crew execution failed: {str(e)}")
    # Send error notification to user
    notify_user_of_error(str(e))
```

---

## 8. Testing Strategy

### 8.1 Unit Tests for Each Agent

```python
# test_data_analysis_agent.py
def test_booking_data_extraction():
    agent = create_data_analysis_agent()
    task = create_data_extraction_task(agent)
    result = agent.execute(task)
    assert result["status"] == "success"

# test_market_analysis_agent.py
def test_market_analysis():
    agent = create_market_analysis_agent()
    task = create_market_analysis_task(agent)
    result = agent.execute(task)
    assert "recommendations" in result

# test_accounting_agent.py
def test_expense_recording():
    agent = create_accounting_agent()
    task = create_expense_recording_task(agent)
    result = agent.execute(task)
    assert result["successful_records"] > 0

# test_executive_agent.py
def test_executive_reporting():
    agent = create_executive_agent()
    task = create_executive_reporting_task(agent)
    result = agent.execute(task)
    assert "executive_summary" in result
```

### 8.2 Integration Tests

```python
# test_integration.py
def test_full_workflow():
    crew = create_crew()
    result = crew.kickoff()
    
    # Verify all agents executed
    assert result["data_analysis"]["status"] == "success"
    assert result["market_analysis"]["status"] == "success"
    assert result["accounting"]["status"] == "success"
    assert result["executive"]["status"] == "success"
```

---

## 9. Monitoring and Logging

### 9.1 Agent Execution Logging

Each agent should log its activities:

```python
import logging

logger = logging.getLogger(__name__)

def execute_agent(agent, task):
    logger.info(f"Starting {agent.role} execution")
    try:
        result = agent.execute(task)
        logger.info(f"Completed {agent.role} execution successfully")
        return result
    except Exception as e:
        logger.error(f"Error in {agent.role}: {str(e)}")
        raise
```

### 9.2 Performance Metrics

Track performance for each agent:

```python
METRICS = {
    "data_analysis": {
        "execution_time": 0,
        "success_rate": 0,
        "data_quality_score": 0
    },
    "market_analysis": {
        "execution_time": 0,
        "success_rate": 0,
        "insight_quality_score": 0
    },
    "accounting": {
        "execution_time": 0,
        "success_rate": 0,
        "accuracy_score": 0
    },
    "executive": {
        "execution_time": 0,
        "success_rate": 0,
        "recommendation_quality_score": 0
    }
}
```

---

## 10. Deployment Checklist

- [ ] All four agent skills are properly defined
- [ ] Tools for each agent are implemented and tested
- [ ] Environment variables are configured
- [ ] Database schema is created (if using database storage)
- [ ] Unit tests for each agent pass
- [ ] Integration tests for the full workflow pass
- [ ] Error handling is implemented for all agents
- [ ] Logging is configured for all agents
- [ ] LINE webhook is properly configured
- [ ] Monitoring and alerting are set up
- [ ] Documentation is complete
- [ ] Deployment to production is approved

---

## 11. Quick Reference: Agent Skills Locations

| Agent | Skill Location | Status |
| :--- | :--- | :--- |
| **Data Analysis** | `skill/data_analysis_agent/SKILL.md` | ✅ Created |
| **Market Analysis** | `skill/market_analysis_agent/SKILL.md` | ✅ Created |
| **Accounting** | `skill/accounting_agent/SKILL.md` | ✅ Created |
| **Admin** | `skill/admin_agent/SKILL.md` | ✅ Created |
| **Executive** | `skill/executive_agent/SKILL.md` | ✅ Created |

---

## 12. Next Steps

1. **Review Skills:** Review each skill document to understand the agent's role and responsibilities.
2. **Implement Tools:** Implement the required tools for each agent.
3. **Create Agents:** Define the agents using the specifications in each skill.
4. **Define Tasks:** Create tasks that align with each agent's responsibilities.
5. **Build Crew:** Combine agents and tasks into a crew.
6. **Test:** Run unit and integration tests to verify functionality.
7. **Deploy:** Deploy the system to production.

---

**End of Integration Guide**
