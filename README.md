# aria-automation-ipam

**Aria Automation ABX Actions for phpIPAM Integration**

Automates IP address allocation and release during VM provisioning and deprovisioning in VMware Aria Automation (formerly vRealize Automation). Built as extensibility actions (ABX) in Python, these actions integrate directly with a phpIPAM server to manage IP assignments without manual intervention.

---

## Overview

When a VM is provisioned through an Aria Automation blueprint, the `allocate` action fires to claim the next available IP from a designated phpIPAM subnet and register it with the VM hostname. When the VM is destroyed, the `deallocate` action fires to search for and release that IP back to the pool.

```
Aria Blueprint → Day 2 Event → ABX Action → phpIPAM API
                  Provision  →  allocate  →  POST /addresses
                  Destroy    → deallocate →  DELETE /addresses/{id}
```

---

## Repository Structure

```
aria-automation-ipam/
├── .github/
│   └── workflows/
│       └── test.yml              # CI pipeline — runs on push and PR to main
├── abx-actions/
│   ├── allocate-ip/
│   │   └── allocate.py           # ABX handler: allocate next free IP from subnet
│   └── deallocate-ip/
│       └── deallocate.py         # ABX handler: search and release IP by address
├── tests/
│   ├── test_allocate.py          # Unit tests for allocate action
│   └── test_deallocate.py        # Unit tests for deallocate action
└── README.md
```

---

## Prerequisites

- VMware Aria Automation 8.x or later with ABX extensibility enabled
- phpIPAM server with API access enabled and an application token created
- Python 3.10+ (for local development and testing)
- `requests` and `urllib3` Python packages

---

## Environment Variables

Both ABX actions are configured entirely through environment variables set in the **Aria Automation ABX Action properties**. No credentials are hardcoded.

| Variable | Required | Description |
|---|---|---|
| `IPAM_URL` | ✅ | Base URL of the phpIPAM API (e.g. `https://ipam.lab.local/api`) |
| `IPAM_APP_ID` | ✅ | phpIPAM application ID (e.g. `aria`) |
| `IPAM_TOKEN` | ✅ | phpIPAM static API token |
| `SUBNET_ID` | ✅ | Target subnet ID for allocation (e.g. `3`) |
| `IPAM_VERIFY_SSL` | ❌ | Set to `false` to disable SSL verification (lab/dev only) |

---

## ABX Actions

### `allocate.py` — IP Allocation

Triggered on VM **provisioning**. Queries phpIPAM for the first available IP in the configured subnet, then registers it with the VM hostname.

**Inputs (from Aria blueprint):**

| Key | Type | Description |
|---|---|---|
| `resourceName` | string | VM name — used as the hostname in phpIPAM |

**Outputs:**

| Key | Type | Description |
|---|---|---|
| `ipAddress` | string | Allocated IP address |
| `allocationStatus` | string | `success` on completion |
| `subnetId` | string | Subnet the IP was allocated from |

**Flow:**
1. Query `GET /subnets/{subnetId}/first_free/` for next available IP
2. Register IP with hostname via `POST /addresses/`
3. Return allocated IP to the Aria blueprint for NIC configuration

---

### `deallocate.py` — IP Release

Triggered on VM **destruction**. Searches phpIPAM for the IP address record and deletes it to return the IP to the available pool.

**Inputs (from Aria blueprint):**

| Key | Type | Description |
|---|---|---|
| `ipAddress` | string | IP address to release |
| `resourceName` | string | VM name — used for logging only |

**Outputs:**

| Key | Type | Description |
|---|---|---|
| `ipAddress` | string | The IP address that was released |
| `deallocationStatus` | string | `success` on completion |

**Flow:**
1. Search phpIPAM for record via `GET /addresses/search/{ip}/`
2. Extract internal phpIPAM address ID from response
3. Delete record via `DELETE /addresses/{id}/`

---

## Resilience & Error Handling

Both actions implement production-grade reliability patterns:

- **Retry logic** — 3 attempts with exponential backoff on `500/502/503/504` responses
- **Typed exceptions** — separate handling for `ConnectionError`, `Timeout`, `HTTPError`, `ValueError`, and `EnvironmentError`
- **Input validation** — missing required inputs raise immediately with descriptive messages
- **Response validation** — phpIPAM application-level codes checked independently of HTTP status
- **Structured logging** — prefixed log lines (`[allocate]` / `[deallocate]`) for easy filtering in Aria log viewer

---

## Running Tests Locally

```bash
# Install dependencies
pip install pytest pytest-cov requests urllib3

# Run all tests
pytest tests/ -v

# Run with coverage report
pytest tests/ -v --cov=abx-actions --cov-report=term-missing

# Run a specific test file
pytest tests/test_allocate.py -v
pytest tests/test_deallocate.py -v
```

Tests use `unittest.mock` to simulate phpIPAM API responses — no live phpIPAM instance required.

---

## CI Pipeline

The GitHub Actions workflow (`.github/workflows/test.yml`) runs automatically on every push and pull request to `main`. It tests against Python 3.10, 3.11, and 3.12 and reports coverage.

---

## Deploying to Aria Automation

1. In Aria Automation, navigate to **Extensibility → Actions**
2. Create a new ABX action for each script (`allocate.py`, `deallocate.py`)
3. Set runtime to **Python 3.10** (or later)
4. Add the environment variables from the table above in the action **Inputs/Constants** section
5. Set the handler to `allocate.handler` or `deallocate.handler` respectively
6. Add `requests` and `urllib3` as dependencies
7. Wire each action to the appropriate blueprint event:
   - `allocate` → **Compute Allocation** event
   - `deallocate` → **Compute Destroy** event

---

## Author

**Randolph Barden** — [@FantasmaV](https://github.com/FantasmaV)

Senior VCF / Aria Automation Engineer | VMware by Broadcom
