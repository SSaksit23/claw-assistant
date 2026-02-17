# Development Plan: Python + LLM (CrewAI) + MCP Tour Charge Automation

**Author:** Manus AI
**Date:** January 19, 2026
**Version:** 1.0

## 1. Introduction

This document outlines a comprehensive development plan for creating a robust, intelligent automation solution for the tour charge expense registration process on the qualityb2bpackage.com website. The proposed system will leverage a multi-agent framework (CrewAI) powered by Large Language Models (LLMs) and will be exposed as a set of tools via the Model Context Protocol (MCP).

This plan is based on the analysis of the existing `auto-expense-register` repository, including the successful fixes for browser automation and the user-provided context documents detailing the desired multi-agent architecture. The goal is to create a standalone, reliable, and scalable Python application that does not depend on external workflow orchestrators like n8n.

## 2. High-Level System Architecture

The system is designed with a modular, three-tier architecture to ensure a clear separation of concerns, making it maintainable and scalable.

1.  **Core Automation Layer (CrewAI):** This is the heart of the system, where a crew of specialized AI agents performs the end-to-end task of registering an expense. It handles all logic, from data preparation to browser interaction and result extraction.
2.  **Tooling Layer (Playwright):** This layer provides the CrewAI agents with the necessary capabilities to interact with a web browser. These are low-level, focused functions that perform specific actions like logging in, filling a form field, or clicking a button.
3.  **Integration Layer (MCP Server):** This is the outermost layer that exposes the core automation functionality to the outside world (e.g., to another AI agent like Manus) through a standardized MCP interface.

### 2.1. Architectural Diagram

The following diagram illustrates the interaction between these components:

![System Architecture](https://private-us-east-1.manuscdn.com/sessionFile/dUC2PS8HFgeoUBZXiALKsd/sandbox/4evUnUyoomQr170yX87Ctb-images_1768803386965_na1fn_L2hvbWUvdWJ1bnR1L2F1dG8tZXhwZW5zZS1yZWdpc3Rlci9hcmNoaXRlY3R1cmVfZGlhZ3JhbQ.png?Policy=eyJTdGF0ZW1lbnQiOlt7IlJlc291cmNlIjoiaHR0cHM6Ly9wcml2YXRlLXVzLWVhc3QtMS5tYW51c2Nkbi5jb20vc2Vzc2lvbkZpbGUvZFVDMlBTOEhGZ2VvVUJaWGlBTEtzZC9zYW5kYm94LzRldlVuVXlvb21RcjE3MHlYODdDdGItaW1hZ2VzXzE3Njg4MDMzODY5NjVfbmExZm5fTDJodmJXVXZkV0oxYm5SMUwyRjFkRzh0Wlhod1pXNXpaUzF5WldkcGMzUmxjaTloY21Ob2FYUmxZM1IxY21WZlpHbGhaM0poYlEucG5nIiwiQ29uZGl0aW9uIjp7IkRhdGVMZXNzVGhhbiI6eyJBV1M6RXBvY2hUaW1lIjoxNzk4NzYxNjAwfX19XX0_&Key-Pair-Id=K2HSFNDJXOU9YS&Signature=QI37QS1eQ2b595fsNvDWGa7A3oARa1aKqgbuPrVV6lJ7S0WCl2p1D-vx2VclP0WQMwf2jmSXQpxyz6fpgACj4Em~5TSA7s8bo5qyTJbKxUzVcCmoAOyug6WN4qz9M9FG8OA18uEUTGY7HIgD3gpulJ2Rrp-SLGKr9-zQbAMyPEmwUhAFlVMP4g0DMYdtBf~I7Nl-CbTU7tqUXvqjusyna8rwHJ9Tgc7q6fI1eMACVb7sAZCvMpXWyGAUZ1RqxpYOR0rUT56Lxit-OZ-7CwuF1-9f8Feo3Lye35Iwia83awHoc4JzHYrKPoMcM1YHiyNf5qlVokFJkrkFvPno8nOhzA__)

## 3. Component Breakdown

This section provides a detailed breakdown of each major component of the application.

### 3.1. Tooling Layer: Browser Tools

This layer is the foundation of the automation. It will consist of a `BrowserManager` singleton to ensure a single, shared browser instance is used across all operations, and a set of focused tools built on top of it.

**File:** `src/tour_charge_automation/tools/browser_tools.py`

| Class / Tool | Description |
| :--- | :--- |
| **`BrowserManager`** | A singleton class to manage the Playwright browser lifecycle (start, get page, close). This is crucial for sharing the same logged-in session across all agents and tasks. |
| **`LoginTool`** | Handles the complete login process, including filling credentials and verifying success by checking for a post-login element. |
| **`FindProgramCodeTool`** | Searches the website for a program code given a tour code. It will use the website's search functionality. |
| **`NavigateToFormTool`** | Navigates the browser to the specific URL for creating a new expense charge. |
| **`FillFormTool`** | The most complex tool. It will use the hybrid JavaScript injection method to reliably interact with the Bootstrap selectpicker dropdowns and other dynamic form elements. It will handle filling all fields, including the main expense and the company expense section. |
| **`ExtractExpenseNumberTool`** | After form submission, this tool will scrape the resulting page to find the newly generated expense number (e.g., `C202614-139454`). |

### 3.2. Core Automation Layer: CrewAI Application

This layer contains the intelligence of the system, orchestrating the tools to perform the complex workflow.

#### 3.2.1. Agent Definitions

**File:** `src/tour_charge_automation/agents.py`

Based on the provided architecture documents, the following agents will be created. Each will be configured with a specific LLM (e.g., `gpt-4o-mini`) and assigned a set of tools.

| Agent | Role | Goal | Tools |
| :--- | :--- | :--- | :--- |
| **Login Agent** | Authentication Specialist | Log in to the system securely. | `LoginTool` |
| **Program Search Agent** | Tour Program Specialist | Find the correct program code for a given tour code. | `FindProgramCodeTool` |
| **Data Preparation Agent** | Data Entry Specialist | Prepare all data needed for the form, including calculating dates and formatting remarks. | None (LLM reasoning only) |
| **Form Access Agent** | Web Navigation Expert | Navigate to the correct expense form page. | `NavigateToFormTool` |
| **Form Submission Agent** | Automation Scripter | Fill and submit the expense form using the prepared data. | `FillFormTool` |
| **Result Retrieval Agent**| Data Extraction Specialist | Retrieve the expense order number after submission. | `ExtractExpenseNumberTool` |

#### 3.2.2. Task Definitions

**File:** `src/tour_charge_automation/tasks.py`

Tasks will be defined to guide the agents. They will be chained together in a sequential process, with the output of one task being passed as the context to the next.

1.  **Login Task:** Instructs the `Login Agent` to log in.
2.  **Find Program Code Task:** Instructs the `Program Search Agent` to find the program code for the given tour code.
3.  **Prepare Data Task:** Instructs the `Data Preparation Agent` to take the tour code, PAX, amount, and the program code (from the previous task's context) and generate a complete JSON object for the form.
4.  **Navigate to Form Task:** Instructs the `Form Access Agent` to go to the expense creation page.
5.  **Submit Form Task:** Instructs the `Form Submission Agent` to use the JSON object from the data preparation task to fill and submit the form.
6.  **Retrieve Result Task:** Instructs the `Result Retrieval Agent` to extract the expense number from the confirmation page.

### 3.3. Integration Layer: MCP Server

This layer makes the entire CrewAI workflow available as a simple, callable tool for other systems.

**File:** `mcp_server.py` (at the root of the project)

This script will initialize and run an MCP server that exposes the automation capabilities. It will not contain any browser or agent logic itself; it will simply import and trigger the main CrewAI orchestration function.

**Exposed MCP Tools:**

| Tool Name | Description | Input Parameters | Output |
| :--- | :--- | :--- | :--- |
| `run_expense_automation` | Runs the full expense automation workflow for a single tour entry. | `tour_code`, `pax`, `amount` | A JSON object with the status (`SUCCESS`/`FAILED`) and the extracted `expense_no`. |
| `extract_packages` | (Optional Enhancement) Extracts a list of tour packages from the website. | `limit` | A JSON object containing a list of package details. |

## 4. Phased Implementation Plan

This project will be implemented in four distinct phases to ensure quality and manage complexity.

### Phase 1: Foundation - Project Setup & Tooling

*   **Objective:** Create the project structure and develop robust, individually testable browser automation tools.
*   **Tasks:**
    1.  Create the directory structure as defined in the `CrewAIImplementationGuide.md`.
    2.  Implement the `BrowserManager` singleton in `browser_tools.py`.
    3.  Implement and unit-test each of the browser tools (`LoginTool`, `FillFormTool`, etc.). The `FillFormTool` must incorporate the proven hybrid JavaScript injection technique.
    4.  Set up the `.env` file for secure credential management.

### Phase 2: Intelligence - Agents & Tasks

*   **Objective:** Define the AI agents and the tasks they need to perform.
*   **Tasks:**
    1.  Implement all agent definitions in `agents.py`, ensuring they have the correct roles, goals, backstories, and assigned tools.
    2.  Implement all task definitions in `tasks.py`. Pay close attention to the `context` parameter to ensure data flows correctly between tasks.
    3.  Configure the LLM to be used by the agents (e.g., `gpt-4o-mini` via OpenAI API).

### Phase 3: Orchestration - Crew & Main Script

*   **Objective:** Bring the agents and tasks together into a functioning crew that can process a single expense entry.
*   **Tasks:**
    1.  Create the `main.py` script.
    2.  Implement the `process_single_entry` function that initializes the `Crew` with the agents and tasks and calls `crew.kickoff()`.
    3.  Implement the main `run_automation` function that reads data from the CSV and calls `process_single_entry` for each row.
    4.  Perform an end-to-end test with a single CSV entry to validate the entire workflow.

### Phase 4: Integration - MCP Server & Finalization

*   **Objective:** Expose the automation workflow as an MCP tool and finalize the project.
*   **Tasks:**
    1.  Create the `mcp_server.py` at the project root.
    2.  In this server, define the `run_expense_automation` MCP tool.
    3.  The tool's implementation will simply call the `run_automation` function from `main.py`.
    4.  Update the `README.md` with detailed instructions on how to install dependencies, set up the `.env` file, and run both the standalone script and the MCP server.
    5.  Clean up the repository, removing any old or unnecessary scripts.

## 5. Conclusion

This development plan provides a clear roadmap for building a sophisticated and reliable automation solution. By combining the intelligence of LLMs and CrewAI with the precision of Playwright and JavaScript injection, the final application will be far more resilient than the original script. The addition of an MCP server provides a modern, standardized way to integrate this capability into larger AI-driven workflows, ensuring the project is not only a solution for today but also a building block for the future.
