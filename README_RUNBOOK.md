# EICH 2 Development Runbook

## Running Tests

CI now enforces the 38+ passing test baseline on every push and pull request via the `CI Tests` GitHub Actions workflow.

### Prerequisites
- Python 3.12+
- Dependencies installed from `requirements.txt`

### Install Dependencies
```bash
python -m pip install -r requirements.txt