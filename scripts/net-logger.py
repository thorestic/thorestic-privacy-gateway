#!/usr/bin/env python3
import subprocess
import threading
import time
import re
from pathlib import Path
from datetime import datetime

LOG_DIR = Path("/var/log/thorestic-gateway")
LOG_DIR.mkdir(parents=True, exist_ok=True)

DNS_LOG = LOG_DIR / "dns.log"
CONN_LOG = LOG_DIR / "connections.log"
COMBINED_LOG = LOG_DIR / "combined.log"

def write_log(kind: str, message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} [{kind}] {message}\n"

    target = {
        "DNS": DNS_LOG,
        "CONNECTION": CONN_LOG,
    }.get(kind, COMBINED_LOG)

    with target.open("a", encoding="utf-8") as f:
        f.write(line)

    with COMBINED_LOG.open("a", encoding="utf-8") as f:
        f.write(line)

def parse_dns_line(line: str) -> str | None:
    # مثال:
    # IP 192.168.50.26.60767 > 192.168.50.1.53: 1234+ A? google.com. (28)
    m = re.search(r'IP\s+(\d+\.\d+\.\d+\.\d+)\.\d+\s+>\s+(\d+\.\d+\.\d+\.\d+)\.53:.*?\s([A-Z]+)\?\s+([^\s]+)', line)
    if not m:
        return None

    client_ip = m.group(1)
    dns_server = m.group(2)
    query_type = m.group(3)
    domain = m.group(4).rstrip(".")

    return f"Client {client_ip} asked DNS {dns_server} for {domain} [{query_type}]"

def parse_connection_line(line: str) -> str | None:
    # مثال:
    # IP 192.168.50.26.50297 > 17.253.122.204.443: Flags [SEW], ...
    m = re.search(r'IP\s+(\d+\.\d+\.\d+\.\d+)\.(\d+)\s+>\s+(\d+\.\d+\.\d+\.\d+)\.(\d+):', line)
    if not m:
        return None

    src_ip = m.group(1)
    src_port = m.group(2)
    dst_ip = m.group(3)
    dst_port = m.group(4)

    service = {
        "80": "HTTP",
        "443": "HTTPS",
        "53": "DNS",
        "22": "SSH",
        "123": "NTP",
        "5223": "Apple Push",
        "3478": "STUN",
    }.get(dst_port, "Unknown")

    return f"Client {src_ip}:{src_port} -> {dst_ip}:{dst_port} ({service})"

def run_dns_logger():
    cmd = [
        "tcpdump",
        "-i", "eth0",
        "-l",
        "-n",
        "udp port 53 or tcp port 53"
    ]

    while True:
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )

            if process.stdout:
                for line in process.stdout:
                    parsed = parse_dns_line(line.strip())
                    if parsed:
                        write_log("DNS", parsed)

            process.wait()
        except Exception as e:
            write_log("DNS", f"Logger error: {e}")

        time.sleep(2)

def run_connection_logger():
    cmd = [
        "tcpdump",
        "-i", "eth0",
        "-l",
        "-n",
        "(tcp[tcpflags] & tcp-syn != 0)"
    ]

    while True:
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                bufsize=1,
            )

            if process.stdout:
                for line in process.stdout:
                    parsed = parse_connection_line(line.strip())
                    if parsed:
                        write_log("CONNECTION", parsed)

            process.wait()
        except Exception as e:
            write_log("CONNECTION", f"Logger error: {e}")

        time.sleep(2)

def main():
    threads = [
        threading.Thread(target=run_dns_logger, daemon=True),
        threading.Thread(target=run_connection_logger, daemon=True),
    ]

    for t in threads:
        t.start()

    while True:
        time.sleep(60)

if __name__ == "__main__":
    main()
