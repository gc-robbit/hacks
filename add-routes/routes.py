#!/usr/bin/env python3

# Given list of addresses, grab their ip's and add them to the routing table
import argparse
import socket
import subprocess


def get_ips_to_route(file_with_host_names):
    ips = []
    with open(file_with_host_names, "rb") as f:
        for dirty_host in f:
            host = dirty_host.strip().decode("utf-8")
            ip = socket.gethostbyname(host)
            ips.append(ip)
    return ips


def add_route_for_ips(ips, gateway):
    for ip in ips:
        result = subprocess.run(["sudo", "route", "-n", "add", "-net", "{ip}/32".format(ip=ip), gateway])
        result.check_returncode()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--gateway', required=True)
    parser.add_argument('--hosts', default="hosts")
    args = parser.parse_args()

    ips = get_ips_to_route(args.hosts)

    print("About to invoke sudo, please provide your password if prompted")

    add_route_for_ips(ips, args.gateway)

