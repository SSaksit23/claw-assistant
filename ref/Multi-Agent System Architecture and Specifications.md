# Multi-Agent System Architecture and Specifications

**Author**: Manus AI

**Date**: 2026-02-17

## 1. System Architecture Overview

This document details the architecture and specifications for the multi-agent system designed to automate and enhance the operations of Quality B2B Package. The system is built upon a modular, agent-based framework, leveraging the power of specialized AI agents to handle distinct business functions. The architecture is designed to be scalable, robust, and seamlessly integrated with the existing web platform and external services.

The proposed architecture is centered around a central **Assignment Agent** that acts as a controller, receiving user requests and delegating them to a team of specialized agents. This hub-and-spoke model ensures a clear flow of information and a separation of concerns, allowing each agent to focus on its core competencies. The system will utilize the **CrewAI framework** for the development and orchestration of these agents, as per the user's preference.

The agents will interact with the Quality B2B Package website through a combination of direct API calls (as defined in the MCP file) and web automation powered by **ClawBot**. **OpenAI's** powerful language models will be used for a variety of tasks, including natural language understanding, data extraction, and report generation. User interaction will be facilitated through the **LINE Messaging API**, providing a conversational interface for initiating tasks and receiving updates.

## 2. Agent Specifications

This section provides a detailed breakdown of each agent's role, responsibilities, and technical specifications.

### 2.1. Assignment Agent

*   **Role**: The central coordinator and task delegator of the multi-agent system.
*   **Responsibilities**:
    *   Receive and interpret user requests from the LINE Messaging API.
    *   Process and extract data from user-provided files (PDF, DOCX, XLSX, CSV).
    *   Define the scope and requirements of each task.
    *   Develop a plan of action and assign tasks to the appropriate specialized agents.
    *   Monitor the progress of tasks and ensure timely completion.
*   **Tools and Integrations**:
    *   **LINE Messaging API**: To communicate with the user.
    *   **OpenAI**: For natural language understanding and task planning.
    *   **File Processing Libraries**: To parse and extract data from various file formats.
*   **Workflow**:
    1.  Receives a new message or file from the user via the LINE Messaging API.
    2.  Uses OpenAI to analyze the user's intent and extract key information.
    3.  If a file is provided, it extracts the relevant data.
    4.  Based on the task, it identifies the appropriate specialized agent(s) to handle the request.
    5.  It formulates a detailed task description and passes it to the assigned agent(s).
    6.  It tracks the status of the task and provides updates to the user as needed.

### 2.2. Accounting Agent

*   **Role**: The financial specialist responsible for all accounting-related tasks.
*   **Responsibilities**:
    *   Create and manage expense orders in the Quality B2B Package system.
    *   Record financial transactions and maintain accurate records.
    *   Process invoices and receipts.
    *   Store and retrieve financial data from the `charges_group` section of the website.
*   **Tools and Integrations**:
    *   **ClawBot**: To automate data entry on the `https://www.qualityb2bpackage.com/charges_group/create` page.
    *   **MCP Endpoints**: To interact with the `charges_group` API for data retrieval and management.
    *   **OpenAI**: For data extraction from invoices and receipts.
*   **Workflow**:
    1.  Receives a task from the Assignment Agent to create an expense order.
    2.  Extracts the necessary financial data from the provided information (e.g., invoice file).
    3.  Uses ClawBot to navigate to the expense creation page and fill in the required fields.
    4.  Submits the form to create the new expense record.
    5.  Verifies that the record has been created successfully and reports back to the Assignment Agent.

### 2.3. Data Analysis Agent

*   **Role**: The data expert responsible for retrieving and analyzing data from the website.
*   **Responsibilities**:
    *   Retrieve booking information from `https://www.qualityb2bpackage.com/booking`.
    *   Retrieve sales and performance data from the report section at `https://www.qualityb2bpackage.com/report/report_seller`.
    *   Analyze data to identify trends, patterns, and insights.
    *   Prepare data for the Executive Agent to use in reports.
*   **Tools and Integrations**:
    *   **ClawBot/MCP Endpoints**: To retrieve data from the booking and report sections of the website.
    *   **Data Analysis Libraries (e.g., Pandas)**: To process and analyze the retrieved data.
    *   **OpenAI**: For summarizing data and generating initial insights.
*   **Workflow**:
    1.  Receives a request from the Assignment Agent or Executive Agent to retrieve and analyze data.
    2.  Navigates to the relevant sections of the website to gather the required data.
    3.  Processes and cleans the data to prepare it for analysis.
    4.  Performs the requested analysis (e.g., trend analysis, sales performance).
    5.  Generates a summary of the findings and passes it to the requesting agent.

### 2.4. Market Analysis Agent

*   **Role**: The market intelligence specialist responsible for competitive and market analysis.
*   **Responsibilities**:
    *   Analyze the company's own product offerings on `https://www.qualityb2bpackage.com/travelpackage`.
    *   Gather information from the web on competitor offerings, pricing, and market trends.
    *   Perform keyword-based research to identify new market opportunities.
    *   Provide insights and recommendations based on the market analysis.
*   **Tools and Integrations**:
    *   **ClawBot**: For web scraping and gathering data from competitor websites.
    *   **Search APIs**: To perform automated web searches.
    *   **OpenAI**: For analyzing unstructured text data and generating market insights.
*   **Workflow**:
    1.  Receives a market analysis request from the Assignment Agent or Executive Agent.
    2.  Analyzes the company's internal product data to establish a baseline.
    3.  Uses web scraping and search tools to gather data on competitors and the market.
    4.  Analyzes the collected data to identify competitive advantages, disadvantages, and opportunities.
    5.  Generates a comprehensive market analysis report and delivers it to the requesting agent.

### 2.5. Admin Agent

*   **Role**: The administrative assistant responsible for record-keeping and data management tasks.
*   **Responsibilities**:
    *   Create and maintain records for expenses and other administrative tasks.
    *   Ensure data accuracy and consistency across the system.
    *   Perform routine data entry and management tasks as required.
*   **Tools and Integrations**:
    *   **ClawBot**: To automate data entry on the `https://www.qualityb2bpackage.com/charges_group/create` page.
    *   **MCP Endpoints**: For interacting with the website's administrative functions.
*   **Workflow**:
    1.  Receives administrative tasks from the Assignment Agent.
    2.  Performs the required data entry or record creation on the website.
    3.  Verifies the accuracy of the entered data.
    4.  Reports the completion of the task to the Assignment Agent.

### 2.6. Executive Agent

*   **Role**: The strategic advisor responsible for high-level reporting and insights.
*   **Responsibilities**:
    *   Aggregate data from the Accounting, Data Analysis, and Market Analysis agents.
    *   Generate comprehensive reports for the executive team.
    *   Provide actionable insights and strategic recommendations.
    *   Summarize key performance indicators and business metrics.
*   **Tools and Integrations**:
    *   **OpenAI**: For report generation, data summarization, and insight creation.
    *   **Data Visualization Libraries**: To create charts and graphs for reports.
*   **Workflow**:
    1.  Receives a request to generate an executive report.
    2.  Gathers the necessary data from the other specialized agents.
    3.  Aggregates and synthesizes the data to create a holistic view of the business.
    4.  Uses OpenAI to generate a narrative report with key findings and recommendations.
    5.  Creates visualizations to support the report.
    6.  Delivers the final report to the user via the Assignment Agent and LINE Messaging API.

## 3. References

[1] Quality B2B Package Website. [https://www.qualityb2bpackage.com/](https://www.qualityb2bpackage.com/)
[2] CrewAI Framework. [https://www.crewai.com/](https://www.crewai.com/)
