#!/usr/bin/env python3

import re
import sys
import subprocess

import tabulate
import hurry.filesize

def parse_conn_spec(s):
    try:
        # Example: ESTABLISHED 14 seconds ago, 10.0.0.2[foo]...10.0.0.1[10.0.0.1]
        return re.search(r'.*ESTABLISHED\s+(.*)ago,\s(.*)\[(.*)\]\.\.\.(.*)\[(.*)\].*', s).groups()
    except AttributeError:
        # No active SAs found, so we have nothing to display
        print("No established security associations found.")
        print("Use \"show vpn ipsec sa verbose\" to view inactive and connecting tunnels.")
        sys.exit(0)

def parse_sa_counters(s):
    bytes_in, bytes_out = None, None
    try:
        # Example with traffic: AES_CBC_256/HMAC_SHA2_256_128/ECP_521, 2382660 bytes_i (1789 pkts, 2s ago), 2382660 bytes_o ...
        bytes_in, bytes_out = re.search(r'\s+(\d+)\s+bytes_i\s\(.*pkts,.*\),\s+(\d+)\s+bytes_o', s).groups()
    except AttributeError:
        try:
            # Example without traffic: 3DES_CBC/HMAC_MD5_96/MODP_1024, 0 bytes_i, 0 bytes_o, rekeying in 45 minutes
            bytes_in, bytes_out = re.search(r'\s+(\d+)\s+bytes_i,\s+(\d+)\s+bytes_o,\s+rekeying', s).groups()
        except AttributeError:
            pass

    if (bytes_in is not None) and (bytes_out is not None):
        # Convert bytes to human-readable units
        bytes_in = hurry.filesize.size(int(bytes_in))
        bytes_out = hurry.filesize.size(int(bytes_out))

        result = "{0}/{1}".format(bytes_in, bytes_out)
    else:
        result = "N/A"

    return result

def parse_ike_proposal(s):
    result = re.search(r'IKE proposal:\s+(.*)\s', s)
    if result:
        return result.groups(0)[0]
    else:
        return "N/A"


# Get a list of all configured connections
with open('/etc/ipsec.conf', 'r') as f:
    config = f.read()
    connections = set(re.findall(r'conn\s([^\s]+)\s*\n', config))
    connections = list(filter(lambda s: s != '%default', connections))

try:
    # DMVPN connections have to be handled separately
    with open('/etc/swanctl/swanctl.conf', 'r') as f:
        dmvpn_config = f.read()
        dmvpn_connections = re.findall(r'\s+(dmvpn-.*)\s+{\n', dmvpn_config)
    connections += dmvpn_connections
except:
    pass

status_data = []

for conn in connections:
    status = subprocess.check_output("ipsec statusall {0}".format(conn), shell=True).decode()
    if re.search(r'no match|CONNECTING', status):
        status_line = [conn, "down", None, None, None, None, None]
    else:
        try:
            time, _, _, ip, id = parse_conn_spec(status)
            if ip == id:
                id = None
            counters = parse_sa_counters(status)
            enc = parse_ike_proposal(status)
            status_line = [conn, "up", time, counters, ip, id, enc]
        except Exception as e:
            print(status)
            raise e
            status_line = [conn, None, None, None, None, None]

    status_line = list(map(lambda x: "N/A" if x is None else x, status_line))
    status_data.append(status_line)

headers = ["Connection", "State", "Up", "Bytes In/Out", "Remote address", "Remote ID", "Proposal"]
output = tabulate.tabulate(status_data, headers)
print(output)
