# UBP BOT

UBP BOT is a Windows desktop automation application for transaction-status verification and rejection extraction from two banking systems: the OTC BPS portal and the GNB portal.

The application provides separate automation workflows, configurable input and output directories, Excel reporting, operational diagnostics, and safeguards for handling sensitive data.

## Supported Workflows

### OTC BPS Portal
- Operator-assisted portal sign-in, including manual CAPTCHA and OTP steps where required.
- Transaction lookup and result extraction.
- Exclusion of response codes `95` and `98` from rejection reports.
- Approved transactions, including response code `00` and `APPROVED`, are not treated as qualifying rejections.
- Qualifying rejection results are written to `OTC_Rejected_Transactions.xlsx`.

### GNB Portal
- Separate browser profile and automation workflow.
- Transaction lookup and rejection extraction.
- Results are written to `GNB_Rejected_Transactions.xlsx`.

OTC and GNB use separate browser contexts and output workbooks to keep their sessions and reporting workflows isolated.

## Key Capabilities

- **Desktop dashboard:** A graphical interface for starting workflows, monitoring progress, viewing status and selecting folders.
- **Visible portal sessions:** OTC and GNB live browser sessions run visibly so operators can complete CAPTCHA and OTP authentication.
- **Configurable directories:** Choose input and output folders through the folder-browse controls. Selected paths are validated and saved for subsequent application launches.
- **Input monitoring and processing:** File stability checks, queue handling, duplicate detection and archival workflows.
- **Checkpoint recovery:** SQLite-backed processing records support recovery of interrupted work.
- **Excel reporting:** Separate workbooks for OTC and GNB, with spreadsheet formula-injection safeguards.
- **Sensitive-data handling:** Configuration sanitization and log masking for supported credential, identity and payment-data patterns.
- **Diagnostics:** Pre-flight checks for the runtime, dependencies, browser availability and directory permissions.

## Repository Structure

```text
UBP-BOT/
├── main.py
├── README.md
├── pyproject.toml
├── requirements.txt
├── .env.example
├── src/
│   └── ubp_bot/
│       ├── app.py
│       ├── ui/
│       │   ├── dashboard.py
│       │   └── dialogs.py
│       ├── core/
│       │   ├── config.py
│       │   ├── queue_manager.py
│       │   ├── file_detector.py
│       │   └── pipeline.py
│       ├── portals/
│       │   ├── otc_client.py
│       │   └── gnb_client.py
│       ├── services/
│       │   ├── excel_reporter.py
│       │   ├── diagnostics.py
│       │   └── browser_manager.py
│       └── security/
│           ├── secret_manager.py
│           └── log_sanitizer.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── regression/
│   └── fixtures/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── MODULE_REFERENCE.md
│   ├── WORKFLOW_REFERENCE.md
│   ├── SECURITY_CONTROLS.md
│   ├── TESTING.md
│   ├── OPERATIONS_RUNBOOK.md
│   └── DEPLOYMENT_READINESS.md
└── deployment/
    ├── build/
    └── packaging/
```

## Requirements

For source-based execution:

- Windows environment supported by the application dependencies.
- Python 3.10.
- Dependencies installed from `requirements.txt`.
- Playwright browser runtime available to the application.
- Network access to the approved banking portals.

For managed workstation deployment, confirm installation permissions, browser/runtime provisioning, filesystem access and network allowlisting with the responsible IT teams. Do not place credentials, customer data, browser sessions or production reports in the source repository.

## Getting Started

### 1. Obtain the source

Clone the repository from the organization-approved Git hosting location, or use the source package supplied through the approved IT handover process.

### 2. Install dependencies

Open PowerShell in the repository directory:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Provision the Playwright browser runtime according to the workstation's approved installation policy and the application's deployment instructions.

### 3. Launch the application

```powershell
python main.py
```

### 4. Run diagnostics

```powershell
python main.py --diagnostics
```

Review diagnostic results and resolve environment or permission issues before connecting to a live banking portal.

## Testing and Code Quality

Run the automated test suite:

```powershell
python -m pytest -q
```

Run lint checks:

```powershell
python -m ruff check src main.py tests
```

Run the security static-analysis scan:

```powershell
python -m bandit -r src/ubp_bot/ -ll
```

A passing automated test or static-analysis run does not replace live-environment UAT, security assessment, or formal deployment approval.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Module Reference](docs/MODULE_REFERENCE.md)
- [Workflow Reference](docs/WORKFLOW_REFERENCE.md)
- [Security Controls](docs/SECURITY_CONTROLS.md)
- [Testing Guide](docs/TESTING.md)
- [Operations Runbook](docs/OPERATIONS_RUNBOOK.md)
- [Deployment and UAT Guide](docs/DEPLOYMENT_READINESS.md)

## Security and Operational Notes

- Use only approved banking portal accounts and authorized workstation environments.
- Never commit credentials, customer information, production reports, browser profiles or session data.
- Keep application configuration and runtime data in locations approved by IT.
- Restrict access to input files, generated reports, logs and checkpoint databases.
- Validate the application in the designated test environment before any production use.
- Production deployment requires the applicable IT, Information Security and change-management approvals.

