#!/usr/bin/env bash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DHCP Server for IP Cameras — Mac Demo Setup
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#
# Sets up a DHCP server on the USB Ethernet adapter so
# IP cameras can connect and get an address automatically.
#
# Cameras will be on 192.168.2.0/24:
#   Mac:      192.168.2.1
#   Cameras:  192.168.2.10 - 192.168.2.50
#
# Usage:
#   ./setup-dhcp-mac.sh          # Start DHCP server
#   ./setup-dhcp-mac.sh stop     # Stop DHCP server
#   ./setup-dhcp-mac.sh status   # Show connected cameras
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

set -euo pipefail

# ── Configuration ─────────────────────────────
IFACE="${CAMERA_IFACE:-en8}"
SUBNET="192.168.2"
MAC_IP="${SUBNET}.1"
DHCP_RANGE_START="${SUBNET}.10"
DHCP_RANGE_END="${SUBNET}.50"
LEASE_TIME="3600"
BOOTPD_PLIST="/etc/bootpd.plist"

# ── Functions ─────────────────────────────────

start_dhcp() {
    echo "Setting up DHCP server on ${IFACE}..."

    # 1. Assign static IP to the adapter
    echo "  Assigning ${MAC_IP}/24 to ${IFACE}..."
    sudo ifconfig "${IFACE}" inet "${MAC_IP}" netmask 255.255.255.0 up

    # 2. Create bootpd config
    echo "  Writing DHCP config..."
    sudo tee "${BOOTPD_PLIST}" > /dev/null << PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>bootp_enabled</key>
    <false/>
    <key>dhcp_enabled</key>
    <array>
        <string>${IFACE}</string>
    </array>
    <key>Subnets</key>
    <array>
        <dict>
            <key>name</key>
            <string>Camera Network</string>
            <key>net_address</key>
            <string>${SUBNET}.0</string>
            <key>net_mask</key>
            <string>255.255.255.0</string>
            <key>net_range</key>
            <array>
                <string>${DHCP_RANGE_START}</string>
                <string>${DHCP_RANGE_END}</string>
            </array>
            <key>dhcp_router</key>
            <string>${MAC_IP}</string>
            <key>dhcp_domain_name_server</key>
            <array>
                <string>${MAC_IP}</string>
            </array>
            <key>lease_max</key>
            <integer>${LEASE_TIME}</integer>
        </dict>
    </array>
</dict>
</plist>
PLISTEOF

    # 3. Start bootpd
    echo "  Starting DHCP server..."
    sudo /usr/libexec/bootpd 2>/dev/null || true
    sudo launchctl load -w /System/Library/LaunchDaemons/bootps.plist 2>/dev/null || true

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  DHCP server running on ${IFACE}"
    echo ""
    echo "  Mac IP:      ${MAC_IP}"
    echo "  Camera pool: ${DHCP_RANGE_START} - ${DHCP_RANGE_END}"
    echo "  Subnet:      ${SUBNET}.0/24"
    echo ""
    echo "  Plug in cameras via Ethernet switch."
    echo "  Check leases:  ./setup-dhcp-mac.sh status"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

stop_dhcp() {
    echo "Stopping DHCP server..."
    sudo launchctl unload -w /System/Library/LaunchDaemons/bootps.plist 2>/dev/null || true
    sudo killall bootpd 2>/dev/null || true
    echo "Stopped."
}

show_status() {
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  Camera Network Status"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Interface ${IFACE}:"
    ifconfig "${IFACE}" 2>/dev/null | grep "inet " || echo "  Not configured"
    echo ""
    echo "DHCP Leases:"
    if [ -f /var/db/dhcpd_leases ]; then
        cat /var/db/dhcpd_leases
    else
        echo "  No leases yet"
    fi
    echo ""
    echo "ARP table (${SUBNET}.*):"
    arp -a 2>/dev/null | grep "${SUBNET}" || echo "  No devices found"
    echo ""
    echo "Scanning for cameras..."
    for i in $(seq 10 50); do
        if ping -c 1 -W 1 "${SUBNET}.${i}" &>/dev/null; then
            echo "  ${SUBNET}.${i} — ALIVE"
        fi
    done
}

# ── Main ──────────────────────────────────────
case "${1:-start}" in
    start)  start_dhcp ;;
    stop)   stop_dhcp ;;
    status) show_status ;;
    *)      echo "Usage: $0 [start|stop|status]"; exit 1 ;;
esac
