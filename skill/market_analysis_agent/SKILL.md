# Market Analysis Agent Skill

**Version:** 2.0
**Date:** 2026-02-17

---

## Agent Definition

| Field | Value |
| :--- | :--- |
| **Role** | Market Intelligence Specialist |
| **Goal** | Provide comprehensive competitive intelligence and market insights by analysing product offerings, pricing strategies, itinerary documents, and market trends. |
| **Backstory** | You are a seasoned market analyst in the travel industry. You scrape product catalogues, parse itinerary PDFs, compare pricing and destinations, identify trends, and produce actionable market positioning recommendations. You leverage the full market intelligence pipeline (Extract → Analyse → Web Research → Aggregate → Report) to deliver data-driven insights. |

---

## Tools

### Web-Based Market Data (existing)

| Tool Class | Description |
| :--- | :--- |
| `ScrapeProductCatalogTool` | Navigate to `/travelpackage`, extract product listings (name, price, dates, destination). |
| `AnalyzeMarketDataTool` | Compare products by destination, price range, and departure frequency. Produces a structured JSON report. |

### Itinerary-Based Market Intelligence (new, from itin-analyzer prototype)

| Tool Function | Description |
| :--- | :--- |
| `market_intelligence_tool` | Full pipeline: Extract → Analyse Themes → Web Research → Aggregate Knowledge Graph → Generate Report. |
| `compare_itineraries_tool` | Side-by-side competitive analysis of 2+ itineraries with comparison matrix. |
| `generate_recommendations_tool` | Strategic product positioning, pricing, and market opportunity recommendations. |
| `batch_analyze_directory_tool` | Scan a directory of itinerary files, analyse all, then run comparison + market intelligence. |

---

## Market Intelligence Pipeline

The agent's primary workflow for document-based analysis:

### Step 1: EXTRACT
- Parse uploaded PDF/DOCX/TXT files using PyMuPDF
- Clean and normalise text (Thai/English bilingual support)
- Validate minimum text quality thresholds

### Step 2: ANALYSE THEMES
- Extract destinations, themes (beach/adventure/cultural/luxury/budget/family)
- Identify duration patterns, activities, target audiences
- Aggregate into dominant theme counters (top destinations, top themes)

### Step 3: WEB RESEARCH (optional, requires EXA_API_KEY)
- Search for competitor tour packages matching dominant themes
- Extract pricing data from search results
- Find competitor operators and their offerings

### Step 4: AGGREGATE
- Build knowledge graph structure:
  - **Destination entities** with product counts, themes, activities
  - **Product entities** with destinations, themes, duration, audience
  - **Competitor entities** from web research with URLs and prices
  - **Relationships** (product → visits → destination)

### Step 5: REPORT
- Generate comprehensive strategic report covering:
  1. Executive Summary
  2. Market Overview
  3. Product Portfolio Analysis
  4. Competitive Landscape
  5. Pricing Intelligence
  6. Strategic Recommendations
  7. Opportunities & Threats (SWOT)

---

## Input

- Booking data output from the **Data Analysis Agent** (`data/booking_data.json`)
- An active browser session for scraping the product catalogue
- Uploaded itinerary documents (PDF, DOCX, TXT) for market intelligence
- Website URL configured in `Config`:
  - `TRAVEL_PACKAGE_URL` → `/travelpackage`

---

## Output

### Web-Based Product Analysis
```json
{
  "products": [
    {
      "package_name": "string",
      "program_code": "string",
      "destination": "string",
      "price": "number",
      "currency": "string",
      "departure_dates": ["YYYY-MM-DD"],
      "duration_days": "number",
      "airline": "string"
    }
  ],
  "analysis": {
    "total_products": "number",
    "destinations_summary": { ... },
    "pricing_insights": ["string"],
    "recommendations": ["string"]
  },
  "analysis_timestamp": "ISO-8601"
}
```
**Output file:** `data/market_analysis.json`

### Market Intelligence Pipeline Output
```json
{
  "success": true,
  "pipeline_steps": { ... },
  "dominant_themes": {
    "main_destination": "Japan",
    "main_theme": "cultural",
    "top_destinations": {"Tokyo": 5, "Osaka": 3},
    "top_themes": {"cultural": 4, "adventure": 2}
  },
  "web_research": {
    "packages_found": [...],
    "prices_found": [...]
  },
  "knowledge_graph": {
    "entities": [...],
    "relationships": [...]
  },
  "final_report": "## Executive Summary\n..."
}
```
**Output file:** `data/market_intelligence.json`

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/itinerary/market-intelligence` | Run full market intelligence pipeline |
| `POST` | `/api/itinerary/compare` | Compare 2+ itinerary files |
| `POST` | `/api/itinerary/recommendations` | Generate strategic recommendations |
| `GET` | `/api/packages` | List travel packages from website |

---

## Execution Order

**Layer 1 — Data Collection** (runs second, after Data Analysis Agent)

**Dependencies:** Uses output from Data Analysis Agent for cross-referencing booking volumes with product availability.

---

## Error Handling

- If the product catalogue page is unavailable, return cached data (if any) with a staleness warning.
- Handle pagination if the product list spans multiple pages.
- If price extraction fails for a product, set price to `null` and flag it in the validation summary.
- Rate-limit requests to avoid being blocked by the server.
- Web research gracefully degrades if `EXA_API_KEY` is not set.
- PDF extraction falls back through 3 methods (text → blocks → dict) for complex layouts.
