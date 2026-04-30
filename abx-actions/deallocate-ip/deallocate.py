import requests
import logging

IPAM_URL = "https://your-phpipam-server/api"
IPAM_APP_ID = "aria"
IPAM_TOKEN = "YOUR_PHPIPAM_TOKEN"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(context, inputs):
    ip_address = inputs.get("address", "")
    resource_name = inputs.get("resourceName", "unknown-vm")
    if not ip_address:
        return {"deallocationStatus": "skipped"}
    try:
        delete_ip(ip_address)
        return {"deallocationStatus": "success", "releasedIp": ip_address}
    except Exception as e:
        logger.error(f"IP deallocation failed: {str(e)}")
        raise

def delete_ip(ip_address):
    headers = {"token": IPAM_TOKEN, "Content-Type": "application/json"}
    search_url = f"{IPAM_URL}/{IPAM_APP_ID}/addresses/search/{ip_address}/"
    response = requests.get(search_url, headers=headers, verify=False)
    response.raise_for_status()
    data = response.json()
    if not data.get("data"):
        raise ValueError(f"IP {ip_address} not found")
    record_id = data["data"][0]["id"]
    delete_url = f"{IPAM_URL}/{IPAM_APP_ID}/addresses/{record_id}/"
    r = requests.delete(delete_url, headers=headers, verify=False)
    r.raise_for_status()