# Data Analysis Agent Skill

**Version:** 2.0
**Date:** 2026-02-17

---

## Agent Definition

| Field | Value |
| :--- | :--- |
| **Role** | Data Retrieval & Itinerary Analysis Specialist |
| **Goal** | Extract, validate, and analyse comprehensive booking data, financial data, and travel itineraries from multiple sources (website, uploaded documents, PDFs). |
| **Backstory** | You are an experienced data analyst who specialises in web scraping, document parsing, and travel industry intelligence. You navigate complex web interfaces to pull booking records, parse itinerary PDFs to extract structured tour data, and compare products across destinations, pricing, and value. You validate and standardise every field before passing the data downstream. |

---

## Tools

### Layer 1 — Web Data Collection (existing)

| Tool Class | Description |
| :--- | :--- |
| `ScrapeBookingDataTool` | Navigate to `/booking`, extract booking records into structured JSON. |
| `ScrapeSellerReportTool` | Navigate to `/report/report_seller`, extract seller performance data. |
| `ValidateExtractedDataTool` | Validate completeness of scraped data (field checks, date parsing, numeric validation). |

### Layer 1B — Itinerary Analysis (new, from itin-analyzer prototype)

| Tool Function | Description |
| :--- | :--- |
| `analyze_itinerary_tool` | Parse an itinerary file (PDF, DOCX, TXT) and extract structured data: tour name, duration, destinations, pricing, flights, inclusions/exclusions, daily breakdown. |
| `compare_itineraries_tool` | Compare 2+ analysed itineraries side by side with a competitive analysis matrix. |
| `market_intelligence_tool` | Run the full market intelligence pipeline: Extract → Analyse Themes → Web Research → Aggregate → Report. |
| `extract_pdf_text_tool` | Extract raw text from PDF files using PyMuPDF with Thai/price/table detection and quality scoring. |
| `generate_recommendations_tool` | Generate strategic product positioning and pricing recommendations from itinerary analyses. |
| `batch_analyze_directory_tool` | Scan a directory for itinerary files, analyse each one, then optionally run comparison and market intelligence. |

---

## Itinerary Analysis Capabilities

### Structured Data Extraction
For each itinerary document, the agent extracts:
- **Tour Name** and **Duration** (days/nights)
- **Destinations** (cities and countries)
- **Pricing** (by period, with currency)
- **Flights** (flight numbers, origins, destinations, times)
- **Inclusions** and **Exclusions**
- **Daily Breakdown** (day-by-day activities, meals, locations)

### Competitive Comparison
When 2+ itineraries are provided:
- Product Comparison Matrix (duration, price/day, destinations, meals, activities)
- Value Analysis (price-to-value ratio)
- Strengths & Weaknesses per product
- Target Customer Profiles
- Market positioning recommendations

### Market Intelligence Pipeline
End-to-end market analysis:
1. **Extract** — Parse and clean all uploaded documents
2. **Analyse** — Identify dominant destinations, themes, duration patterns, activities
3. **Web Research** — Search for competitor products using EXA API
4. **Aggregate** — Build a knowledge graph (entities + relationships)
5. **Report** — Generate a comprehensive strategic market report

### Bilingual Support
- Auto-detects Thai and English text
- Handles mixed Thai/English documents
- Normalises Thai text spacing around numbers
- Preserves Thai price formats (บาท, THB)

---

## Input

This agent accepts:

### For Web Data Collection
- An active browser session (authenticated via `LoginTool`)
- Website URLs configured in `Config`:
  - `BOOKING_URL` → `/booking`
  - `REPORT_SELLER_URL` → `/report/report_seller`

### For Itinerary Analysis
- Uploaded files (PDF, DOCX, TXT) via:
  - WebSocket: Upload a file and say "analyze itinerary"
  - REST API: `POST /api/itinerary/analyze`
- Multiple files for comparison: `POST /api/itinerary/compare`
- Multiple files for market intelligence: `POST /api/itinerary/market-intelligence`

---

## Output

### Booking Data Output (unchanged)
```json
{
  "booking_data": [...],
  "report_data": [...],
  "extraction_timestamp": "ISO-8601",
  "validation_summary": { ... }
}
```
**Output file:** `data/booking_data.json`

### Itinerary Analysis Output
```json
{
  "status": "success",
  "data": {
    "tourName": "Japan Golden Route 8D6N",
    "duration": "8 Days / 6 Nights",
    "destinations": ["Tokyo", "Osaka", "Kyoto", "Mount Fuji"],
    "pricing": [{"period": "Jan-Mar 2026", "price": 49900, "currency": "THB"}],
    "flights": [{"flightNumber": "TG660", "origin": "Bangkok", "destination": "Tokyo", ...}],
    "inclusions": ["Round-trip flights", "Hotel accommodation", ...],
    "exclusions": ["Travel insurance", "Personal expenses", ...],
    "dailyBreakdown": [
      {"day": 1, "title": "Bangkok - Tokyo", "activities": "...", "meals": ["Dinner"], "locations": ["Narita Airport", "Shinjuku"]}
    ]
  },
  "language": "English",
  "metadata": { "total_pages": 4, "quality_score": "high" }
}
```
**Output file:** `data/itinerary_<name>.json`

### Market Intelligence Output
```json
{
  "success": true,
  "pipeline_steps": { "extract": {...}, "analyze_themes": {...}, "web_research": {...}, "aggregate": {...}, "report": {...} },
  "dominant_themes": { "main_destination": "Japan", "main_theme": "cultural", "top_destinations": {...}, "top_themes": {...} },
  "web_research": { "packages_found": [...], "prices_found": [...] },
  "knowledge_graph": { "entities": [...], "relationships": [...] },
  "final_report": "## Executive Summary\n..."
}
```
**Output file:** `data/market_intelligence.json`

---

## API Endpoints

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/itinerary/analyze` | Analyse a single itinerary file |
| `POST` | `/api/itinerary/compare` | Compare 2+ itinerary files |
| `POST` | `/api/itinerary/market-intelligence` | Run market intelligence pipeline |
| `POST` | `/api/itinerary/recommendations` | Generate strategic recommendations |
| `POST` | `/api/itinerary/extract-pdf` | Extract raw text from PDF |

---

## Execution Order

**Layer 1 — Data Collection** (runs first, no dependencies)

---

## Error Handling

- Retry failed page navigations with exponential backoff (max 3 attempts).
- If booking page structure changes, log a detailed warning with the HTML snippet and return partial data.
- Validate every extracted record; invalid records are excluded but logged.
- If PDF extraction yields low-quality text (< 100 chars/page), log a warning and attempt alternate extraction methods.
- If the entire extraction fails, return an empty dataset with an error summary so downstream agents can handle gracefully.
- Web research gracefully degrades if EXA API key is not configured.
