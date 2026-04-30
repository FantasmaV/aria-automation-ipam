import requests
import logging

IPAM_URL = "https://your-phpipam-server/api"
IPAM_APP_ID = "aria"
IPAM_TOKEN = "YOUR_PHPIPAM_TOKEN"
SUBNET_ID = "3"

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(context, inputs):
    resource_name = inputs.get("resourceName", "unknown-vm")
    logger.info(f"Allocating IP for resource: {resource_name}")
    try:
        ip_address = allocate_ip(resource_name)
        return {"ipAddress": ip_address, "allocationStatus": "success"}
    except Exception as e:
        logger.error(f"IP allocation failed: {str(e)}")
        raise

def allocate_ip(hostname):
    headers = {"token": IPAM_TOKEN, "Content-Type": "application/json"}
    url = f"{IPAM_URL}/{IPAM_APP_ID}/subnets/{SUBNET_ID}/first_free/"
    response = requests.get(url, headers=headers, verify=False)
    response.raise_for_status()
    data = response.json()
    if data.get("code") != 200:
        raise ValueError(f"phpIPAM error: {data.get('message')}")
    ip_address = data["data"]
    reserve_url = f"{IPAM_URL}/{IPAM_APP_ID}/addresses/"
    payload = {"subnetId": SUBNET_ID, "ip": ip_address, "hostname": hostname}
    r = requests.post(reserve_url, json=payload, headers=headers, verify=False)
    r.raise_for_status()
    return ip_address