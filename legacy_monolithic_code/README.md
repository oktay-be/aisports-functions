# Turkish Sports News API

A RESTful API that aggregates sports news content from multiple sources about Turkey and Turkish football (particularly Fenerbahçe).

## Features

- **News Aggregation** from NewsAPI, FotMob, and web scraping
- **RESTful Architecture** with well-defined endpoints
- **Validation with Pydantic** for type safety
- **Caching System** for performance optimization
- **Trend Analysis** for Turkish sports topics
- **Environment-based Configuration** with dotenv
- **Docker Support** for easy deployment

## Installation

### Prerequisites
- Python 3.9+
- pip package manager

### Setup

1. Ceate a virtual environment using Python 3.12:

   python3.12 -m venv .venv
   .venv\Scripts\activate

2. Install dependencies:


# Step 1 Using pip-compile (recommended)
python -m pip install pip-tools==7.3.0
pip-compile requirements.in --output-file requirements.txt

# Step 2
python -m pip install -r requirements.txt

3. Configure environment:
cp .env.example .env
# Edit .env to add your NewsAPI key and other credentials

## Usage

### Running the API

```bash
# Start the API server
python app.py

# Or use Make
make run
```

By default, the API runs at `http://localhost:5000`.

### API Endpoints

All endpoints use POST method for consistent parameter handling and easier frontend integration.

| Endpoint | Description | Request Body Example |
|----------|-------------|----------------------|
| `/api/news` | Full-featured news search | `{"keywords": ["Fenerbahçe"], "team_ids": [8650], "languages": ["tr", "en"], ...}` |
| `/api/trending` | Get trending topics | `{"keywords": ["Turkey", "football"], "limit": 10}` |
| `/api/scrape` | Scrape website | `{"urls": ["https://example.com/sports"], "keywords": ["Fenerbahçe"]}` |

Examples:
```bash
# News search (full-featured)
curl -X POST http://localhost:5000/api/news \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["Fenerbahçe", "Süper Lig"], "limit": 5, "sources": ["newsapi"]}'

# Get trending topics
curl -X POST http://localhost:5000/api/trending \
  -H "Content-Type: application/json" \
  -d '{"keywords": ["Turkey", "football"], "limit": 5}'

# Scrape a website
curl -X POST http://localhost:5000/api/scrape \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com/sports"], "keywords": ["Fenerbahçe", "Transfer"]}'
```

## Development

### Docker

```bash
# Build and run with Docker
docker build -t turkish-sports-api .
docker run -p 5000:5000 --env-file .env turkish-sports-api
```

### Makefile Commands

```bash
make setup      # Install dependencies
make run        # Start the API server
make test       # Run tests
make lint       # Run linting
make clean      # Clean cache files
make docker-build
make docker-run
```

### Running Tests with Pytest

This project uses `pytest` for running automated tests.

To run the tests, ensure your virtual environment is activated:
```cmd
.venv\\Scripts\\activate
```

Then, from the project root directory (`c:\\Users\\oktay\\Documents\\aisports`), you can use the following commands:

**Running All Tests:**
```cmd
pytest
```

**Running Specific Tests:**

You can run tests in a specific file:
```cmd
pytest tests/unit/scraping/test_config.py
```

Or a specific test function:
```cmd
pytest tests/unit/scraping/test_config.py::test_my_specific_config_feature
```

**Checking Code Coverage:**

This project uses `pytest-cov` to measure code coverage.

*   **View coverage report in the terminal (shows missing lines):**
    ```cmd
    pytest --cov=capabilities --cov-report=term-missing tests/unit
    ```
    *(You can also run this for `tests/integration` or all tests by adjusting the path)*

*   **Generate an HTML coverage report:**
    ```cmd
    pytest --cov=capabilities --cov-report=html:cov_html tests/unit
    ```
    After running this, you can open `c:\\\\Users\\\\oktay\\\\Documents\\\\aisports\\\\cov_html\\\\index.html` in your web browser to see a detailed interactive report.

*   **Checking coverage for a specific module:**

    If you want to see the coverage for a single module (e.g., `config.py`) based on its specific test file (e.g., `test_config.py`), you can target the `--cov` flag more precisely:
    ```cmd
    pytest --cov=capabilities.scraping.config --cov-report=term-missing tests/unit/scraping/test_config.py
    ```
    And for an HTML report for that specific module:
    ```cmd
    pytest --cov=capabilities.scraping.config --cov-report=html:cov_html_config tests/unit/scraping/test_config.py
    ```
    (This will create a separate HTML report in `cov_html_config` for just that module).

You should see output indicating the status of the tests (e.g., number of tests passed, failed, or skipped) and code coverage percentages. Our goal is to achieve at least 90% coverage for the `capabilities` module.

### Key Project Files

```
├── api/                # API models and routes
├── capabilities/       # Core business logic
├── helpers/            # Configuration helpers
├── tests/              # Test suite
├── utils/              # Utilities and constants
├── app.py              # Main entry point
├── Dockerfile
├── requirements.in     # Source for dependencies
└── requirements.txt    # Generated dependencies (via pip-compile)
```

## Acknowledgements

- [NewsAPI](https://newsapi.org/) - News data
- [FotMob](https://www.fotmob.com/) - Football data
- [Flask](https://flask.palletsprojects.com/) - API framework
- [Pydantic](https://pydantic-docs.helpmanual.io/) - Data validation

## License

MIT
