"""
allocate.py
-----------
Aria Automation ABX Action — phpIPAM IP Address Allocation

Triggered during VM provisioning to dynamically allocate the next available
IP address from a designated phpIPAM subnet and register it with the
requested hostname.

Environment Variables (set in Aria Automation ABX Action properties):
    IPAM_URL        Base URL of the phpIPAM API (e.g. https://ipam.lab.local/api)
    IPAM_APP_ID     phpIPAM application ID (e.g. aria)
    IPAM_TOKEN      phpIPAM static API token
    SUBNET_ID       Target subnet ID for allocation (e.g. 3)
    IPAM_VERIFY_SSL Set to "false" to disable SSL verification (lab/dev only)

Author: Randolph Barden
Repo:   github.com/FantasmaV/aria-automation-ipam
"""

import os
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ── Logging ────────────────────────────────────────────────────────────────────
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Constants ──────────────────────────────────────────────────────────────────
IPAM_URL     = os.environ.get("IPAM_URL", "https://your-phpipam-server/api")
IPAM_APP_ID  = os.environ.get("IPAM_APP_ID", "aria")
IPAM_TOKEN   = os.environ.get("IPAM_TOKEN", "")
SUBNET_ID    = os.environ.get("SUBNET_ID", "3")
VERIFY_SSL   = os.environ.get("IPAM_VERIFY_SSL", "true").lower() != "false"

# Retry strategy: 3 attempts, backoff on 500/502/503/504
_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
)


# ── Session Factory ────────────────────────────────────────────────────────────
def _get_session() -> requests.Session:
    """
    Build a requests Session with:
    - Authorization header pre-set
    - Retry adapter mounted for both http and https
    - 10s connect / 30s read timeout enforced per call
    """
    if not IPAM_TOKEN:
        raise EnvironmentError(
            "IPAM_TOKEN environment variable is not set. "
            "Configure it in the ABX Action properties."
        )

    session = requests.Session()
    session.headers.update({
        "token": IPAM_TOKEN,
        "Content-Type": "application/json",
    })
    session.verify = VERIFY_SSL

    adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session


# ── ABX Entry Point ────────────────────────────────────────────────────────────
def handler(context, inputs: dict) -> dict:
    """
    ABX handler called by Aria Automation during resource provisioning.

    Args:
        context: Aria Automation execution context (unused directly).
        inputs:  Dictionary of inputs passed from the Aria blueprint.
                 Expected keys:
                   - resourceName (str): VM or resource name used as hostname.

    Returns:
        dict with keys:
          - ipAddress (str):        Allocated IP address.
          - allocationStatus (str): "success" on successful allocation.
          - subnetId (str):         Subnet the IP was allocated from.
    """
    resource_name = inputs.get("resourceName", "unknown-vm")
    logger.info(f"[allocate] Starting IP allocation for resource: {resource_name}")

    try:
        session   = _get_session()
        ip_address = allocate_ip(session, resource_name)

        logger.info(f"[allocate] Successfully allocated {ip_address} for {resource_name}")
        return {
            "ipAddress":        ip_address,
            "allocationStatus": "success",
            "subnetId":         SUBNET_ID,
        }

    except EnvironmentError as e:
        logger.error(f"[allocate] Configuration error: {e}")
        raise

    except requests.exceptions.ConnectionError as e:
        logger.error(f"[allocate] Cannot reach phpIPAM at {IPAM_URL}: {e}")
        raise

    except requests.exceptions.Timeout:
        logger.error(f"[allocate] Request to phpIPAM timed out.")
        raise

    except requests.exceptions.HTTPError as e:
        logger.error(f"[allocate] HTTP error from phpIPAM: {e.response.status_code} — {e.response.text}")
        raise

    except ValueError as e:
        logger.error(f"[allocate] phpIPAM API returned an error: {e}")
        raise

    except Exception as e:
        logger.error(f"[allocate] Unexpected error during allocation: {e}")
        raise


# ── Core Allocation Logic ──────────────────────────────────────────────────────
def allocate_ip(session: requests.Session, hostname: str) -> str:
    """
    Allocate the next available IP address from the target subnet in phpIPAM
    and register it with the provided hostname.

    Steps:
        1. Query phpIPAM for the first free IP in SUBNET_ID.
        2. Register (reserve) that IP with the given hostname.

    Args:
        session:  Authenticated requests.Session with retry logic applied.
        hostname: Hostname to associate with the allocated IP in phpIPAM.

    Returns:
        str: The allocated IP address (e.g. "192.168.10.45").

    Raises:
        ValueError:               If phpIPAM returns a non-200 application code.
        requests.HTTPError:       If the HTTP response status indicates failure.
        requests.ConnectionError: If phpIPAM is unreachable.
        requests.Timeout:         If the request exceeds the timeout threshold.
    """
    # Step 1 — Get first free IP from subnet
    first_free_url = f"{IPAM_URL}/{IPAM_APP_ID}/subnets/{SUBNET_ID}/first_free/"
    logger.info(f"[allocate] Querying first free IP — subnet {SUBNET_ID}")

    response = session.get(first_free_url, timeout=(10, 30))
    response.raise_for_status()

    data = response.json()

    if data.get("code") != 200:
        raise ValueError(
            f"phpIPAM returned code {data.get('code')}: {data.get('message', 'no message')}"
        )

    ip_address = data.get("data")
    if not ip_address:
        raise ValueError(
            f"phpIPAM returned success but no IP address in response: {data}"
        )

    logger.info(f"[allocate] First free IP identified: {ip_address}")

    # Step 2 — Reserve the IP with hostname
    reserve_url = f"{IPAM_URL}/{IPAM_APP_ID}/addresses/"
    payload = {
        "subnetId": SUBNET_ID,
        "ip":       ip_address,
        "hostname": hostname,
    }

    logger.info(f"[allocate] Reserving {ip_address} with hostname '{hostname}'")
    reserve_response = session.post(reserve_url, json=payload, timeout=(10, 30))
    reserve_response.raise_for_status()

    reserve_data = reserve_response.json()
    if reserve_data.get("code") != 201:
        raise ValueError(
            f"phpIPAM reservation failed — code {reserve_data.get('code')}: "
            f"{reserve_data.get('message', 'no message')}"
        )

    logger.info(f"[allocate] IP {ip_address} successfully reserved in phpIPAM.")
    return ip_address
