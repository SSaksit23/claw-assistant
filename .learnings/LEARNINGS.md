# Agent Learnings

Corrections, knowledge gaps, and best practices discovered during operation.
Agents consult this file before performing tasks to avoid repeating mistakes.

---

## [LRN-20260219-001] best_practice

**Logged**: 2026-02-19T11:46:08.695240
**Agent**: Accounting Agent
**Priority**: critical
**Status**: pending
**Area**: backend

### Summary
Use single form row with combined total instead of multiple rows

### Details
The charges form only reliably supports ONE expense row per submission. When an invoice has multiple line items (tour fare, single supplement, service fee), combine them into a single row with the TOTAL amount in price[] and the detailed breakdown in description and remark fields. Do NOT attempt to click add-row buttons.

### Suggested Action
Always combine line items into one row with total amount

### Metadata
- Source: agent_operation
- Related Files: tools/browser_tools.py, services/expense_service.py
- Tags: form_filling, total_amount, line_items

---
