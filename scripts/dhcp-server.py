#!/usr/bin/env python3
"""
Minimal DHCP server for Reolink cameras on macOS.

Assigns 192.168.2.10 to whatever device asks on the en10 interface.
Run with: sudo python3 dhcp-server.py

Kill with: sudo kill $(pgrep -f dhcp-server.py)
"""

import socket
import struct
import signal
import sys
import os

IFACE = os.environ.get("CAMERA_IFACE", "en10")
IFACE_IP = os.environ.get("IFACE_IP", "192.168.2.1")
OFFER_IP = os.environ.get("OFFER_IP", "192.168.2.10")
BCAST = os.environ.get("BCAST", "192.168.2.255")
SUBNET = "255.255.255.0"
LEASE = 3600
MAGIC = b'\x63\x82\x53\x63'
IP_BOUND_IF = 25  # macOS setsockopt

def shutdown(sig, frame):
    print("[dhcp] Stopped")
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

if_idx = socket.if_nametoindex(IFACE)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, struct.pack('I', if_idx))
sock.bind(('', 67))

print(f"[dhcp] Listening on {IFACE} (idx={if_idx}), serving {OFFER_IP}")


def parse_opts(data):
    opts = {}
    i = data.index(MAGIC) + 4
    while i < len(data) and data[i] != 255:
        if data[i] == 0:
            i += 1
            continue
        code, length = data[i], data[i + 1]
        opts[code] = data[i + 2:i + 2 + length]
        i += 2 + length
    return opts


def build_reply(req, msg_type):
    r = bytearray(576)
    r[0] = 2
    r[1:4] = req[1:4]
    r[4:8] = req[4:8]
    r[10:12] = b'\x80\x00'  # broadcast flag
    struct.pack_into('!4s', r, 16, socket.inet_aton(OFFER_IP))
    struct.pack_into('!4s', r, 20, socket.inet_aton(IFACE_IP))
    r[28:44] = req[28:44]
    i = 236
    r[i:i + 4] = MAGIC
    i += 4
    for code, val in [
        (53, bytes([msg_type])),
        (54, socket.inet_aton(IFACE_IP)),
        (51, struct.pack('!I', LEASE)),
        (1, socket.inet_aton(SUBNET)),
        (3, socket.inet_aton(IFACE_IP)),
        (6, socket.inet_aton("8.8.8.8")),
    ]:
        r[i] = code
        i += 1
        r[i] = len(val)
        i += 1
        r[i:i + len(val)] = val
        i += len(val)
    r[i] = 255
    return bytes(r)


while True:
    data, addr = sock.recvfrom(4096)
    if len(data) < 240:
        continue
    try:
        opts = parse_opts(data)
    except (ValueError, IndexError):
        continue
    if 53 not in opts:
        continue
    mac = ':'.join(f'{b:02x}' for b in data[28:34])
    mt = opts[53][0]
    if mt == 1:  # DISCOVER
        print(f"[dhcp] DISCOVER {mac} -> OFFER {OFFER_IP}", flush=True)
        sock.sendto(build_reply(data, 2), (BCAST, 68))
    elif mt == 3:  # REQUEST
        print(f"[dhcp] REQUEST  {mac} -> ACK {OFFER_IP}", flush=True)
        sock.sendto(build_reply(data, 5), (BCAST, 68))
