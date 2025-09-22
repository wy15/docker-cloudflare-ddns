#!/usr/bin/env python3

import os
import sys
import json
import logging
import argparse
import subprocess
import socket
import requests
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

CF_API = os.getenv('CF_API', 'https://api.cloudflare.com/client/v4')
RRTYPE = os.getenv('RRTYPE', 'A')
PROXIED = os.getenv('PROXIED', 'false').lower() == 'true'
DELETE_ON_STOP = os.getenv('DELETE_ON_STOP', 'false').lower() == 'true'
DNS_SERVER = os.getenv('DNS_SERVER', '1.1.1.1')
INTERFACE = os.getenv('INTERFACE')
CUSTOM_LOOKUP_CMD = os.getenv('CUSTOM_LOOKUP_CMD')

def load_from_file(file_path: Optional[str]) -> Optional[str]:
    if file_path and os.path.isfile(file_path):
        with open(file_path, 'r') as f:
            return f.read().strip()
    return None

API_KEY = load_from_file(os.getenv('API_KEY_FILE')) or os.getenv('API_KEY')
ZONE = load_from_file(os.getenv('ZONE_FILE')) or os.getenv('ZONE')
SUBDOMAIN = load_from_file(os.getenv('SUBDOMAIN_FILE')) or os.getenv('SUBDOMAIN')
EMAIL = os.getenv('EMAIL')

def get_headers():
    headers: dict[str, str] = {'Content-Type': 'application/json'}
    if EMAIL:
        headers['X-Auth-Email'] = EMAIL  # type: ignore
        headers['X-Auth-Key'] = API_KEY or ''
    else:
        headers['Authorization'] = f'Bearer {API_KEY or ""}'
    return headers

def api_call(method: str, url: str, data=None) -> dict:
    headers = get_headers()
    try:
        if method.upper() == 'GET':
            resp = requests.get(url, headers=headers, timeout=10)
        elif method.upper() == 'POST':
            resp = requests.post(url, headers=headers, json=data, timeout=10)
        elif method.upper() == 'PATCH':
            resp = requests.patch(url, headers=headers, json=data, timeout=10)
        elif method.upper() == 'DELETE':
            resp = requests.delete(url, headers=headers, timeout=10)
        else:
            raise ValueError(f"Unsupported method: {method}")
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as e:
        logging.error(f"API call failed: {e}")
        return {}

def verify_token() -> bool:
    url = f"{CF_API}/user/tokens/verify" if not EMAIL else f"{CF_API}/user"
    resp = api_call('GET', url)
    return resp.get('success', False)

def get_zone_id(zone: str) -> Optional[str]:
    url = f"{CF_API}/zones?name={zone}"
    resp = api_call('GET', url)
    zones = resp.get('result', [])
    return zones[0]['id'] if zones else None

def get_dns_record_id(zone_id: str, name: str, rrtype: str) -> Optional[str]:
    url = f"{CF_API}/zones/{zone_id}/dns_records?type={rrtype}&name={name}"
    resp = api_call('GET', url)
    records = resp.get('result', [])
    return records[0]['id'] if records else None

def create_dns_record(zone_id: str, name: str, content: str, rrtype: str, proxied: bool) -> Optional[str]:
    data = {
        'type': rrtype,
        'name': name,
        'content': content,
        'proxied': proxied,
        'ttl': 1
    }
    url = f"{CF_API}/zones/{zone_id}/dns_records"
    resp = api_call('POST', url, data)
    return resp.get('result', {}).get('id')

def update_dns_record(zone_id: str, record_id: str, name: str, content: str, rrtype: str, proxied: bool) -> bool:
    data = {
        'type': rrtype,
        'name': name,
        'content': content,
        'proxied': proxied
    }
    url = f"{CF_API}/zones/{zone_id}/dns_records/{record_id}"
    resp = api_call('PATCH', url, data)
    return resp.get('success', False)

def delete_dns_record(zone_id: str, record_id: str) -> bool:
    url = f"{CF_API}/zones/{zone_id}/dns_records/{record_id}"
    resp = api_call('DELETE', url)
    return resp.get('success', False)

def get_dns_record_ip(zone_id: str, record_id: str) -> Optional[str]:
    url = f"{CF_API}/zones/{zone_id}/dns_records/{record_id}"
    resp = api_call('GET', url)
    return resp.get('result', {}).get('content')

def get_public_ip(rrtype: str) -> Optional[str]:
    if rrtype == 'A':
        # Try Cloudflare DNS
        try:
            result = subprocess.run(['dig', '+short', f'@{DNS_SERVER}', 'ch', 'txt', 'whoami.cloudflare'], capture_output=True, text=True, timeout=5)
            ip = result.stdout.strip().strip('"')
            if len(ip) <= 15:  # IPv4 length
                return ip
        except:
            pass
        # Fallback to OpenDNS
        try:
            result = subprocess.run(['dig', '+short', 'myip.opendns.com', '@resolver1.opendns.com'], capture_output=True, text=True, timeout=5)
            return result.stdout.strip()
        except:
            pass
        # HTTP fallback
        try:
            resp = requests.get('https://ipinfo.io', timeout=5)
            return resp.json().get('ip')
        except:
            return None
    elif rrtype == 'AAAA':
        # IPv6
        try:
            result = subprocess.run(['dig', '+short', '@2606:4700:4700::1111', '-6', 'ch', 'txt', 'whoami.cloudflare'], capture_output=True, text=True, timeout=5)
            ip = result.stdout.strip().strip('"')
            return ip
        except:
            pass
        # HTTP fallback
        try:
            resp = requests.get('https://ifconfig.co', timeout=5)
            return resp.text.strip()
        except:
            return None
    return None

def get_local_ip(interface: str, rrtype: str) -> Optional[str]:
    try:
        af = 'inet' if rrtype == 'A' else 'inet6'
        result = subprocess.run(['ip', 'addr', 'show', interface], capture_output=True, text=True, timeout=5)
        for line in result.stdout.splitlines():
            if line.strip().startswith(af):
                ip = line.split()[1].split('/')[0]
                return ip
    except:
        return None
    return None

def get_custom_ip(cmd: str) -> Optional[str]:
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return result.stdout.strip()
    except:
        return None

def get_current_ip() -> Optional[str]:
    if CUSTOM_LOOKUP_CMD:
        return get_custom_ip(CUSTOM_LOOKUP_CMD)
    elif INTERFACE:
        return get_local_ip(INTERFACE, RRTYPE)
    else:
        return get_public_ip(RRTYPE)

def get_dns_name() -> str:
    assert ZONE is not None
    return f"{SUBDOMAIN}.{ZONE}" if SUBDOMAIN else ZONE

def setup():
    if not API_KEY or not ZONE:
        logging.error("API_KEY and ZONE are required")
        sys.exit(1)

    if not verify_token():
        logging.error("Invalid Cloudflare credentials")
        sys.exit(1)

    zone_id = get_zone_id(ZONE)
    if not zone_id:
        logging.error(f"Zone {ZONE} not found")
        sys.exit(1)

    logging.info(f"DNS Zone: {ZONE} ({zone_id})")

    current_ip = get_current_ip()
    if not current_ip:
        logging.error("Failed to get current IP")
        sys.exit(1)

    dns_name = get_dns_name()
    record_id = get_dns_record_id(zone_id, dns_name, RRTYPE)

    if not record_id:
        logging.info(f"Creating DNS record for {dns_name}")
        record_id = create_dns_record(zone_id, dns_name, current_ip, RRTYPE, PROXIED)
        if not record_id:
            logging.error(f"Failed to create DNS record for {dns_name}")
            sys.exit(1)

    logging.info(f"DNS Record: {dns_name} ({record_id})")

    config = {
        'CF_ZONE_ID': zone_id,
        'CF_RECORD_ID': record_id,
        'CF_RECORD_NAME': dns_name
    }
    os.makedirs('/config', exist_ok=True)
    with open('/config/cloudflare.conf', 'w') as f:
        json.dump(config, f)

    # Set cron
    cron_line = f"{os.getenv('CRON', '*/5 * * * *')}\t/etc/cont-init.d/50-ddns\n"
    with open('/var/spool/cron/crontabs/root', 'w') as f:
        f.write(cron_line)

def update():
    if not os.path.exists('/config/cloudflare.conf'):
        logging.error("Config file not found")
        return

    with open('/config/cloudflare.conf', 'r') as f:
        config = json.load(f)

    zone_id = config['CF_ZONE_ID']
    record_id = config['CF_RECORD_ID']
    dns_name = config['CF_RECORD_NAME']

    dns_ip = get_dns_record_ip(zone_id, record_id)
    current_ip = get_current_ip()

    if not current_ip:
        logging.error("Failed to get current IP")
        return

    if current_ip != dns_ip:
        logging.info(f"Updating DNS record {dns_name} from {dns_ip} to {current_ip}")
        if update_dns_record(zone_id, record_id, dns_name, current_ip, RRTYPE, PROXIED):
            logging.info(f"DNS record updated successfully")
        else:
            logging.error("Failed to update DNS record")
    else:
        logging.info(f"No update needed for {dns_name} ({dns_ip})")

def cleanup():
    if not os.path.exists('/config/cloudflare.conf'):
        return

    with open('/config/cloudflare.conf', 'r') as f:
        config = json.load(f)

    if not DELETE_ON_STOP:
        logging.info("DNS record deletion disabled")
        return

    zone_id = config['CF_ZONE_ID']
    record_id = config['CF_RECORD_ID']
    dns_name = config['CF_RECORD_NAME']

    logging.info(f"Deleting DNS record {dns_name}")
    if delete_dns_record(zone_id, record_id):
        logging.info("DNS record deleted successfully")
    else:
        logging.error("Failed to delete DNS record")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['setup', 'update', 'cleanup'])
    args = parser.parse_args()

    if args.action == 'setup':
        setup()
    elif args.action == 'update':
        update()
    elif args.action == 'cleanup':
        cleanup()

if __name__ == '__main__':
    main()