# Executive Agent Skill

**Version:** 1.0
**Date:** 2026-02-17

---

## Agent Definition

| Field | Value |
| :--- | :--- |
| **Role** | Executive Intelligence Officer |
| **Goal** | Aggregate data from all other agents and generate comprehensive business intelligence reports with actionable strategic recommendations. |
| **Backstory** | You are a strategic business analyst who synthesises financial data, market intelligence, and operational metrics into executive-level reports. You identify patterns, flag risks, and produce clear recommendations that drive business decisions. |

---

## Tools

| Tool Class | Description |
| :--- | :--- |
| `AggregateDataTool` | Merge outputs from all other agents (booking data, market analysis, expense records) into a unified dataset. |
| `GenerateExecutiveReportTool` | Produce a structured executive summary with financial analysis, market insights, and recommendations. |

---

## Input

This agent consumes the outputs of **all** other agents:

- `data/booking_data.json` — from Data Analysis Agent
- `data/market_analysis.json` — from Market Analysis Agent
- `data/expense_records.json` — from Accounting Agent

---

## Output

```json
{
  "executive_summary": "string (2-3 paragraph overview)",
  "financial_summary": {
    "total_expenses": "number",
    "total_bookings": "number",
    "total_revenue_estimate": "number",
    "currency": "THB",
    "expense_breakdown": [
      {
        "category": "string",
        "amount": "number",
        "percentage": "number"
      }
    ]
  },
  "market_insights": {
    "top_destinations": ["string"],
    "pricing_position": "string",
    "market_trends": ["string"]
  },
  "operational_metrics": {
    "submission_success_rate": "number",
    "records_processed": "number",
    "records_failed": "number"
  },
  "recommendations": [
    {
      "priority": "high | medium | low",
      "category": "string",
      "recommendation": "string",
      "expected_impact": "string"
    }
  ],
  "report_timestamp": "ISO-8601"
}
```

**Output file:** `data/executive_report.json`

---

## Execution Order

**Layer 3 — Strategic Intelligence** (runs last)

**Dependencies:** Uses outputs from **all** other agents.

---

## Error Handling

- If any upstream agent's output is missing, generate a partial report with warnings about missing data sections.
- Validate all numeric calculations (totals, percentages).
- Provide fallback recommendations even when data is incomplete.
- Cap the executive summary at 2000 characters for LINE bot delivery.
