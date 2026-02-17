# Auto Expense Register for qualityb2bpackage.com

Automated expense registration and package extraction system for qualityb2bpackage.com with MCP server integration and REST API support.

## Features

- **Package Extraction**: Extract tour packages from the website with full details
- **Expense Registration**: Automated expense form filling and submission
- **MCP Server**: Model Context Protocol server for AI agent integration
- **REST API**: HTTP API for integration with n8n and other automation tools
- **Batch Processing**: Process multiple expenses from CSV files

## Installation

```bash
# Clone the repository
git clone https://github.com/SSaksit23/auto-expense-register.git
cd auto-expense-register

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium
```

## Configuration

Create a `.env` file or set environment variables:

```bash
QB2B_USERNAME=your_username
QB2B_PASSWORD=your_password
```

Or modify the `CONFIG` dictionary in the scripts directly.

## Usage

### 1. Package Extraction

Extract tour packages from the website:

```bash
# Extract packages with basic info
python package_extractor.py --max 50 --output packages

# Extract with full details
python package_extractor.py --max 20 --details --output packages_detailed

# Search by keyword
python package_extractor.py --keyword "ญี่ปุ่น" --max 30

# Run in visible browser mode
python package_extractor.py --max 10
```

### 2. Expense Registration

Register expenses from CSV file:

```bash
# Process first 3 entries (test mode)
python expense_automation_fixed.py --limit 3

# Process all entries
python expense_automation_fixed.py --all

# Process specific range
python expense_automation_fixed.py --start 10 --limit 5

# Run in headless mode
python expense_automation_fixed.py --headless --limit 10

# Use custom CSV file
python expense_automation_fixed.py --csv path/to/your/file.csv --limit 5
```

### 3. REST API Server

Start the API server for n8n integration:

```bash
# Start server on default port 8080
python api_server.py

# Custom host and port
python api_server.py --host 0.0.0.0 --port 3000
```

#### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/login` | Login to website |
| GET | `/packages` | Extract packages |
| GET | `/packages/<id>` | Get package details |
| GET | `/program-code/<tour_code>` | Find program code |
| POST | `/expenses` | Create expense |
| POST | `/batch-expenses` | Create multiple expenses |
| GET | `/config` | Get configuration |
| PUT | `/config` | Update configuration |

#### Example API Calls

```bash
# Login
curl -X POST http://localhost:8080/login

# Get packages
curl http://localhost:8080/packages?limit=10

# Create expense
curl -X POST http://localhost:8080/expenses \
  -H "Content-Type: application/json" \
  -d '{
    "tour_code": "JAPAN7N-001",
    "program_code": "JP-TK001",
    "amount": 5000,
    "pax": 10
  }'

# Batch expenses
curl -X POST http://localhost:8080/batch-expenses \
  -H "Content-Type: application/json" \
  -d '{
    "expenses": [
      {"tour_code": "TOUR1", "program_code": "CODE1", "amount": 1000, "pax": 5},
      {"tour_code": "TOUR2", "program_code": "CODE2", "amount": 2000, "pax": 10}
    ]
  }'
```

### 4. MCP Server

For AI agent integration via Model Context Protocol:

```bash
# Install MCP library
pip install mcp

# Run MCP server
python qb2b_mcp_server.py
```

#### Available MCP Tools

- `login` - Login to qualityb2bpackage.com
- `extract_packages` - Extract tour packages
- `get_package_details` - Get package details by ID
- `find_program_code` - Find program code from tour code
- `create_expense` - Create expense record

## n8n Integration

### Webhook Setup

1. Start the API server: `python api_server.py --port 8080`
2. In n8n, create an HTTP Request node
3. Configure the node to call your API endpoints

### Example n8n Workflow

```json
{
  "nodes": [
    {
      "name": "Get Packages",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "http://your-server:8080/packages",
        "method": "GET"
      }
    },
    {
      "name": "Create Expense",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "http://your-server:8080/expenses",
        "method": "POST",
        "bodyParameters": {
          "tour_code": "={{$json.tour_code}}",
          "program_code": "={{$json.program_code}}",
          "amount": "={{$json.amount}}",
          "pax": "={{$json.pax}}"
        }
      }
    }
  ]
}
```

## CSV File Format

The expense CSV file should have the following columns:

| Column | Description |
|--------|-------------|
| รหัสทัวร์ | Tour code (e.g., JAPAN7N-001) |
| จำนวนลูกค้า หัก หนท. | Number of passengers (PAX) |
| ยอดเบิก | Expense amount in THB |

Example:
```csv
รหัสทัวร์,จำนวนลูกค้า หัก หนท.,ยอดเบิก
JAPAN7N-001,10,5000
KOREA5N-002,8,4000
```

## File Structure

```
auto-expense-register/
├── README.md                    # This file
├── requirements.txt             # Python dependencies
├── config.py                    # Configuration settings
├── .env.example                 # Environment variables template
│
├── # Main Scripts
├── expense_automation_fixed.py  # Fixed expense registration (recommended)
├── package_extractor.py         # Package extraction script
├── mcp_server.py               # Core client library
│
├── # Server Components
├── api_server.py               # REST API server for n8n
├── qb2b_mcp_server.py          # MCP server for AI agents
│
├── # Legacy Scripts
├── robust_automation.py        # Original automation script
├── simple_automation.py        # Simple version
├── tour_charge_automation.py   # Tour charge specific
│
├── # Documentation
├── form_structure_analysis.md  # Form field analysis
├── package_data_structure.md   # Package data structure
│
└── # Data Files
    └── ยอดเบิกอุปกรณ์.csv       # Sample expense data
```

## Troubleshooting

### Common Issues

1. **Login fails**
   - Check username/password in config
   - Ensure the website is accessible
   - Try running in visible mode (without --headless)

2. **Form submission doesn't commit**
   - Use `expense_automation_fixed.py` instead of `robust_automation.py`
   - The fix uses correct selector `input[type="submit"]` instead of `button`

3. **Tour code not found**
   - Verify the tour code exists in the system
   - Check the date range filter (default: 2024-2026)

4. **Playwright browser issues**
   - Run `playwright install chromium` to install browsers
   - Check if running in a headless environment

### Logs

Check the log files for detailed information:
- `expense_automation.log` - Expense automation logs
- `automation.log` - General automation logs

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License
