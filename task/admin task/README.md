# Tour Charge Automation

A robust, intelligent automation solution for tour charge expense registration on qualityb2bpackage.com. This system leverages a multi-agent framework (CrewAI) powered by Large Language Models and is exposed via the Model Context Protocol (MCP).

## Features

- **Multi-Agent Architecture**: Uses CrewAI with specialized agents for login, program search, form filling, and result extraction
- **Robust Browser Automation**: Playwright-based automation with hybrid JavaScript injection for reliable interaction with dynamic forms
- **MCP Integration**: Exposes functionality via Model Context Protocol for integration with AI assistants
- **Batch Processing**: Process multiple expense entries from CSV files
- **Comprehensive Logging**: Detailed logging for debugging and audit trails

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Server (Integration Layer)           │
│                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────┐  │
│  │process_single_  │  │run_expense_     │  │extract_    │  │
│  │expense          │  │automation       │  │packages    │  │
│  └────────┬────────┘  └────────┬────────┘  └─────┬──────┘  │
└───────────┼────────────────────┼─────────────────┼─────────┘
            │                    │                 │
            ▼                    ▼                 ▼
┌─────────────────────────────────────────────────────────────┐
│                CrewAI (Core Automation Layer)               │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │  Login   │ │ Program  │ │  Form    │ │  Result  │       │
│  │  Agent   │ │  Search  │ │  Submit  │ │ Retrieval│       │
│  │          │ │  Agent   │ │  Agent   │ │  Agent   │       │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘       │
└───────┼────────────┼────────────┼────────────┼─────────────┘
        │            │            │            │
        ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────┐
│               Playwright (Tooling Layer)                    │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │LoginTool │ │FindCode  │ │FillForm  │ │Extract   │       │
│  │          │ │Tool      │ │Tool      │ │Number    │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                             │
│              ┌─────────────────────────┐                    │
│              │    BrowserManager       │                    │
│              │    (Singleton)          │                    │
│              └─────────────────────────┘                    │
└─────────────────────────────────────────────────────────────┘
```

## Project Structure

```
auto-expense/
├── main.py                     # Main entry point for CLI
├── mcp_server_crewai.py        # MCP server launcher
├── requirements.txt            # Python dependencies
├── README.md                   # This file
│
├── src/
│   └── tour_charge_automation/
│       ├── __init__.py
│       ├── config.py           # Configuration management
│       ├── agents.py           # CrewAI agent definitions
│       ├── tasks.py            # CrewAI task definitions
│       ├── crew.py             # Crew orchestration
│       ├── mcp_server.py       # MCP server implementation
│       │
│       └── tools/
│           ├── __init__.py
│           ├── browser_manager.py  # Singleton browser manager
│           └── browser_tools.py    # CrewAI browser tools
│
├── results/                    # Output directory for results
└── *.csv                       # Input CSV files
```

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd auto-expense
   ```

2. **Create a virtual environment** (recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   # or
   source venv/bin/activate  # Linux/Mac
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright browsers**:
   ```bash
   playwright install chromium
   ```

5. **Set up environment variables**:
   Create a `.env` file in the project root:
   ```env
   # QualityB2BPackage.com Credentials
   QB2B_USERNAME=your_username
   QB2B_PASSWORD=your_password
   
   # OpenAI API Configuration (for CrewAI agents)
   OPENAI_API_KEY=your_openai_api_key
   OPENAI_MODEL=gpt-4o-mini
   
   # Browser Settings
   BROWSER_HEADLESS=false
   ```

## Usage

### Command Line Interface

```bash
# Process entries from CSV file
python main.py --csv ยอดเบิกอุปกรณ์.csv --limit 5

# Process a single entry
python main.py --tour-code BTMYSP16N240107 --pax 20 --amount 1000

# Run in headless mode
python main.py --csv data.csv --headless

# Process all entries from CSV
python main.py --csv data.csv --all

# Specify output directory
python main.py --csv data.csv --output-dir my_results
```

### CSV File Format

The input CSV file should have the following columns:
- `รหัสทัวร์` (or `tour_code`): Tour code (e.g., BTMYSP16N240107)
- `จำนวนลูกค้า หัก หนท.` (or `pax`): Number of passengers
- `ยอดเบิก` (or `amount`): Expense amount in THB

Example:
```csv
รหัสทัวร์,จำนวนลูกค้า หัก หนท.,ยอดเบิก
BTMYSP16N240107,20,1000
MC-MYSP1-EK,15,750
```

### MCP Server

To run as an MCP server for integration with AI assistants:

```bash
python mcp_server_crewai.py
```

Configure in your MCP client (e.g., Claude Desktop `claude_desktop_config.json`):
```json
{
    "mcpServers": {
        "tour-charge-automation": {
            "command": "python",
            "args": ["C:\\path\\to\\auto-expense\\mcp_server_crewai.py"],
            "env": {
                "QB2B_USERNAME": "your_username",
                "QB2B_PASSWORD": "your_password",
                "OPENAI_API_KEY": "your_api_key"
            }
        }
    }
}
```

### MCP Tools Available

| Tool | Description | Parameters |
|------|-------------|------------|
| `process_single_expense` | Process a single expense entry | `tour_code`, `pax`, `amount`, `program_code` (optional) |
| `run_expense_automation` | Process multiple entries in batch | `entries` (array), `headless` |
| `extract_packages` | Extract tour packages from website | `limit` |

## Agents

| Agent | Role | Responsibility |
|-------|------|----------------|
| Login Agent | Authentication Specialist | Securely log into the website |
| Program Search Agent | Tour Program Specialist | Find program codes for tour codes |
| Form Access Agent | Web Navigation Expert | Navigate to expense form page |
| Form Submission Agent | Automation Scripter | Fill and submit expense forms |
| Result Retrieval Agent | Data Extraction Specialist | Extract expense numbers after submission |

## Configuration

Configuration is managed through environment variables and the `config.py` module:

| Variable | Description | Default |
|----------|-------------|---------|
| `QB2B_USERNAME` | Website username | Required |
| `QB2B_PASSWORD` | Website password | Required |
| `OPENAI_API_KEY` | OpenAI API key for CrewAI | Required |
| `OPENAI_MODEL` | LLM model to use | `gpt-4o-mini` |
| `BROWSER_HEADLESS` | Run browser headless | `false` |

## Output

Results are saved in the `results/` directory as both CSV and JSON files:
- `expense_results_YYYYMMDD_HHMMSS.csv`
- `expense_results_YYYYMMDD_HHMMSS.json`

Each result contains:
- `tour_code`: The tour code processed
- `program_code`: The program code found
- `pax`: Number of passengers
- `amount`: Expense amount
- `status`: SUCCESS or FAILED
- `expense_no`: Generated expense number (e.g., C202614-139454)
- `error`: Error message if failed
- `timestamp`: Processing timestamp

## Troubleshooting

### Common Issues

1. **Login fails**:
   - Verify credentials in `.env` file
   - Check if the website is accessible
   - Try running without headless mode to see the browser

2. **Program code not found**:
   - The tour code may not exist in the system
   - Date range might need adjustment (currently 01/01/2024 to 31/12/2026)

3. **Form submission fails**:
   - Check if all required fields are being filled
   - Verify the tour code exists in the period dropdown

4. **MCP server won't start**:
   - Ensure MCP library is installed: `pip install mcp`
   - Check Python version (3.9+ required)

### Debug Mode

Run with visible browser for debugging:
```bash
python main.py --csv data.csv --limit 1  # Browser visible by default
```

Check logs in `automation.log` for detailed execution traces.

## Development

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest tests/
```

### Adding New Tools

1. Add tool input schema in `browser_tools.py`
2. Implement the tool class extending `BaseTool`
3. Register in `__init__.py` exports
4. Add corresponding MCP tool definition in `mcp_server.py`

## License

This project is proprietary software for internal use.

## Support

For issues or questions, please contact the development team.
