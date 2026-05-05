"""
deallocate.py
-------------
Aria Automation ABX Action — phpIPAM IP Address Deallocation

Triggered during VM destruction/deprovisioning to release the IP address
previously allocated to a resource back to the phpIPAM subnet pool.

Environment Variables (set in Aria Automation ABX Action properties):
    IPAM_URL        Base URL of the phpIPAM API (e.g. https://ipam.lab.local/api)
    IPAM_APP_ID     phpIPAM application ID (e.g. aria)
    IPAM_TOKEN      phpIPAM static API token
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
IPAM_URL    = os.environ.get("IPAM_URL", "https://your-phpipam-server/api")
IPAM_APP_ID = os.environ.get("IPAM_APP_ID", "aria")
IPAM_TOKEN  = os.environ.get("IPAM_TOKEN", "")
VERIFY_SSL  = os.environ.get("IPAM_VERIFY_SSL", "true").lower() != "false"

# Retry strategy: 3 attempts, backoff on 500/502/503/504
_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[500, 502, 503, 504],
    allowed_methods=["GET", "DELETE"],
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
    ABX handler called by Aria Automation during resource destruction.

    Args:
        context: Aria Automation execution context (unused directly).
        inputs:  Dictionary of inputs passed from the Aria blueprint.
                 Expected keys:
                   - ipAddress (str):    The IP address to release.
                   - resourceName (str): VM or resource name for logging.

    Returns:
        dict with keys:
          - ipAddress (str):          The IP address that was released.
          - deallocationStatus (str): "success" on successful release.
    """
    ip_address    = inputs.get("ipAddress", "")
    resource_name = inputs.get("resourceName", "unknown-vm")

    logger.info(f"[deallocate] Starting IP release for resource: {resource_name} — IP: {ip_address}")

    if not ip_address:
        raise ValueError(
            "Input 'ipAddress' is required for deallocation but was not provided."
        )

    try:
        session = _get_session()
        deallocate_ip(session, ip_address, resource_name)

        logger.info(f"[deallocate] Successfully released {ip_address} for {resource_name}")
        return {
            "ipAddress":          ip_address,
            "deallocationStatus": "success",
        }

    except EnvironmentError as e:
        logger.error(f"[deallocate] Configuration error: {e}")
        raise

    except requests.exceptions.ConnectionError as e:
        logger.error(f"[deallocate] Cannot reach phpIPAM at {IPAM_URL}: {e}")
        raise

    except requests.exceptions.Timeout:
        logger.error(f"[deallocate] Request to phpIPAM timed out.")
        raise

    except requests.exceptions.HTTPError as e:
        logger.error(f"[deallocate] HTTP error from phpIPAM: {e.response.status_code} — {e.response.text}")
        raise

    except ValueError as e:
        logger.error(f"[deallocate] phpIPAM API returned an error: {e}")
        raise

    except Exception as e:
        logger.error(f"[deallocate] Unexpected error during deallocation: {e}")
        raise


# ── Core Deallocation Logic ────────────────────────────────────────────────────
def deallocate_ip(session: requests.Session, ip_address: str, resource_name: str) -> None:
    """
    Look up and delete an IP address record from phpIPAM by IP address.

    Steps:
        1. Search phpIPAM for the address record matching ip_address.
        2. Extract the internal phpIPAM address ID.
        3. DELETE the address record to return it to the subnet pool.

    Args:
        session:       Authenticated requests.Session with retry logic applied.
        ip_address:    The IP address string to release (e.g. "192.168.10.45").
        resource_name: Resource name used for log context only.

    Returns:
        None

    Raises:
        ValueError:               If the IP is not found in phpIPAM or the
                                  API returns an unexpected response code.
        requests.HTTPError:       If the HTTP response status indicates failure.
        requests.ConnectionError: If phpIPAM is unreachable.
        requests.Timeout:         If the request exceeds the timeout threshold.
    """
    # Step 1 — Search for the address record by IP
    search_url = f"{IPAM_URL}/{IPAM_APP_ID}/addresses/search/{ip_address}/"
    logger.info(f"[deallocate] Searching phpIPAM for IP: {ip_address}")

    response = session.get(search_url, timeout=(10, 30))
    response.raise_for_status()

    data = response.json()

    if data.get("code") != 200:
        raise ValueError(
            f"phpIPAM search returned code {data.get('code')}: "
            f"{data.get('message', 'IP address not found in phpIPAM')}"
        )

    records = data.get("data", [])
    if not records:
        raise ValueError(
            f"No phpIPAM record found for IP {ip_address}. "
            f"It may have already been released or was never registered."
        )

    # Step 2 — Extract the phpIPAM internal address ID
    address_id = records[0].get("id")
    if not address_id:
        raise ValueError(
            f"phpIPAM returned a record for {ip_address} but it contained no 'id' field: {records[0]}"
        )

    logger.info(f"[deallocate] Found phpIPAM record ID {address_id} for IP {ip_address}")

    # Step 3 — Delete the address record
    delete_url = f"{IPAM_URL}/{IPAM_APP_ID}/addresses/{address_id}/"
    logger.info(f"[deallocate] Deleting phpIPAM record ID {address_id}")

    delete_response = session.delete(delete_url, timeout=(10, 30))
    delete_response.raise_for_status()

    delete_data = delete_response.json()

    if delete_data.get("code") != 200:
        raise ValueError(
            f"phpIPAM deletion failed — code {delete_data.get('code')}: "
            f"{delete_data.get('message', 'no message')}"
        )

    logger.info(
        f"[deallocate] IP {ip_address} (record ID {address_id}) "
        f"successfully released from phpIPAM for resource '{resource_name}'."
    )
