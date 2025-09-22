#!/usr/bin/env python3

import argparse
import json
import logging
import os
import subprocess
import sys
import time
from typing import Optional

import requests

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

CF_API = os.getenv("CF_API", "https://api.cloudflare.com/client/v4")
RRTYPE = os.getenv("RRTYPE", "A")
PROXIED = os.getenv("PROXIED", "false").lower() == "true"

DNS_SERVER = os.getenv("DNS_SERVER", "1.1.1.1")
CUSTOM_LOOKUP_CMD = os.getenv("CUSTOM_LOOKUP_CMD")


def load_from_file(file_path: Optional[str]) -> Optional[str]:
    if file_path and os.path.isfile(file_path):
        with open(file_path, "r") as f:
            return f.read().strip()
    return None


API_KEY = load_from_file(os.getenv("API_KEY_FILE")) or os.getenv("API_KEY")
ZONE = load_from_file(os.getenv("ZONE_FILE")) or os.getenv("ZONE")
SUBDOMAIN = load_from_file(os.getenv("SUBDOMAIN_FILE")) or os.getenv("SUBDOMAIN")
EMAIL = os.getenv("EMAIL")


def get_headers():
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if EMAIL:
        headers["X-Auth-Email"] = EMAIL  # type: ignore
        headers["X-Auth-Key"] = API_KEY or ""
    else:
        headers["Authorization"] = f"Bearer {API_KEY or ''}"
    return headers


def api_call(method: str, url: str, data=None) -> dict:
    headers = get_headers()
    try:
        if method.upper() == "GET":
            resp = requests.get(url, headers=headers, timeout=10)
        elif method.upper() == "POST":
            resp = requests.post(url, headers=headers, json=data, timeout=10)
        elif method.upper() == "PATCH":
            resp = requests.patch(url, headers=headers, json=data, timeout=10)
        elif method.upper() == "DELETE":
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
    resp = api_call("GET", url)
    return resp.get("success", False)


def get_zone_id(zone: str) -> Optional[str]:
    url = f"{CF_API}/zones?name={zone}"
    resp = api_call("GET", url)
    zones = resp.get("result", [])
    return zones[0]["id"] if zones else None


def get_dns_record_id(zone_id: str, name: str, rrtype: str) -> Optional[str]:
    url = f"{CF_API}/zones/{zone_id}/dns_records?type={rrtype}&name={name}"
    resp = api_call("GET", url)
    records = resp.get("result", [])
    return records[0]["id"] if records else None


def create_dns_record(
    zone_id: str, name: str, content: str, rrtype: str, proxied: bool
) -> Optional[str]:
    data = {
        "type": rrtype,
        "name": name,
        "content": content,
        "proxied": proxied,
        "ttl": 1,
    }
    url = f"{CF_API}/zones/{zone_id}/dns_records"
    resp = api_call("POST", url, data)
    return resp.get("result", {}).get("id")


def update_dns_record(
    zone_id: str, record_id: str, name: str, content: str, rrtype: str, proxied: bool
) -> bool:
    data = {"type": rrtype, "name": name, "content": content, "proxied": proxied}
    url = f"{CF_API}/zones/{zone_id}/dns_records/{record_id}"
    resp = api_call("PATCH", url, data)
    return resp.get("success", False)


def delete_dns_record(zone_id: str, record_id: str) -> bool:
    url = f"{CF_API}/zones/{zone_id}/dns_records/{record_id}"
    resp = api_call("DELETE", url)
    return resp.get("success", False)


def get_dns_record_ip(zone_id: str, record_id: str) -> Optional[str]:
    url = f"{CF_API}/zones/{zone_id}/dns_records/{record_id}"
    resp = api_call("GET", url)
    return resp.get("result", {}).get("content")


def get_public_ip(rrtype: str) -> Optional[str]:
    if rrtype == "A":
        # Try Cloudflare DNS
        logging.info("Trying Cloudflare DNS for IPv4")
        try:
            result = subprocess.run(
                ["dig", "+short", f"@{DNS_SERVER}", "ch", "txt", "whoami.cloudflare"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ip = result.stdout.strip().strip('"')
            if ip and len(ip) <= 15:  # IPv4 length
                logging.info(f"Got IP from Cloudflare DNS: {ip}")
                return ip
        except Exception as e:
            logging.warning(f"Cloudflare DNS failed: {e}")
        # Fallback to OpenDNS
        logging.info("Trying OpenDNS for IPv4")
        try:
            result = subprocess.run(
                ["dig", "+short", "myip.opendns.com", "@resolver1.opendns.com"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ip = result.stdout.strip()
            if ip:
                logging.info(f"Got IP from OpenDNS: {ip}")
                return ip
        except Exception as e:
            logging.warning(f"OpenDNS failed: {e}")
        # HTTP fallbacks
        http_services = [
            ("https://ipinfo.io", lambda resp: resp.json().get("ip")),
            ("https://api.ipify.org", lambda resp: resp.text.strip()),
            ("https://icanhazip.com", lambda resp: resp.text.strip()),
            ("https://checkip.amazonaws.com", lambda resp: resp.text.strip()),
            ("https://httpbin.org/ip", lambda resp: resp.json().get("origin")),
            ("https://api.myip.com", lambda resp: resp.json().get("ip")),
        ]
        for url, extractor in http_services:
            logging.info(f"Trying HTTP fallback: {url}")
            try:
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                ip = extractor(resp)
                if ip:
                    logging.info(f"Got IP from {url}: {ip}")
                    return ip
            except Exception as e:
                logging.warning(f"HTTP fallback {url} failed: {e}")
        logging.error("All IPv4 IP detection methods failed")
        return None
    elif rrtype == "AAAA":
        # IPv6
        logging.info("Trying Cloudflare DNS for IPv6")
        try:
            result = subprocess.run(
                [
                    "dig",
                    "+short",
                    "@2606:4700:4700::1111",
                    "-6",
                    "ch",
                    "txt",
                    "whoami.cloudflare",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ip = result.stdout.strip().strip('"')
            if ip:
                logging.info(f"Got IPv6 from Cloudflare DNS: {ip}")
                return ip
        except Exception as e:
            logging.warning(f"Cloudflare IPv6 DNS failed: {e}")
        # HTTP fallbacks
        http_services = [
            ("https://ifconfig.co", lambda resp: resp.text.strip()),
            ("https://api6.ipify.org", lambda resp: resp.text.strip()),
            ("https://icanhazip.com", lambda resp: resp.text.strip()),
            ("https://checkip.amazonaws.com", lambda resp: resp.text.strip()),
            ("https://httpbin.org/ip", lambda resp: resp.json().get("origin")),
            ("https://api.myip.com", lambda resp: resp.json().get("ip")),
        ]
        for url, extractor in http_services:
            logging.info(f"Trying HTTP fallback: {url}")
            try:
                resp = requests.get(url, timeout=5)
                resp.raise_for_status()
                ip = extractor(resp)
                if ip:
                    logging.info(f"Got IPv6 from {url}: {ip}")
                    return ip
            except Exception as e:
                logging.warning(f"HTTP fallback {url} failed: {e}")
        logging.error("All IPv6 IP detection methods failed")
        return None
    return None


def get_custom_ip(cmd: str) -> Optional[str]:
    logging.info(f"Running custom IP command: {cmd}")
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=10
        )
        ip = result.stdout.strip()
        if ip:
            logging.info(f"Got IP from custom command: {ip}")
            return ip
        else:
            logging.warning("Custom command returned empty output")
    except Exception as e:
        logging.error(f"Custom command failed: {e}")
    return None


def get_current_ip() -> Optional[str]:
    if CUSTOM_LOOKUP_CMD:
        ip = get_custom_ip(CUSTOM_LOOKUP_CMD)
    else:
        ip = get_public_ip(RRTYPE)
    if not ip:
        logging.error("Failed to get current IP")
    return ip


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
        "CF_ZONE_ID": zone_id,
        "CF_RECORD_ID": record_id,
        "CF_RECORD_NAME": dns_name,
    }
    os.makedirs("/config", exist_ok=True)
    with open("/config/cloudflare.conf", "w") as f:
        json.dump(config, f)


def update():
    if not os.path.exists("/config/cloudflare.conf"):
        logging.error("Config file not found")
        return

    with open("/config/cloudflare.conf", "r") as f:
        config = json.load(f)

    zone_id = config["CF_ZONE_ID"]
    record_id = config["CF_RECORD_ID"]
    dns_name = config["CF_RECORD_NAME"]

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


def run():
    setup()
    import schedule

    schedule.every(5).minutes.do(update)
    while True:
        schedule.run_pending()
        time.sleep(60)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["setup", "update", "run"])
    args = parser.parse_args()

    if args.action == "setup":
        setup()
    elif args.action == "update":
        update()
    elif args.action == "run":
        run()


if __name__ == "__main__":
    main()
