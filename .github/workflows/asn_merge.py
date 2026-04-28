import ipaddress

ipv4_nets, ipv6_nets = [], []

with open("raw_ips.txt") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            net = ipaddress.ip_network(line)
            (ipv4_nets if net.version == 4 else ipv6_nets).append(net)
        except ValueError:
            continue

merged_v4 = ipaddress.collapse_addresses(ipv4_nets)
merged_v6 = ipaddress.collapse_addresses(ipv6_nets)

with open("ru-bundle/rknasnblock.list", "w") as out:
    for net in merged_v4:
        out.write(str(net) + "\n")
    for net in merged_v6:
        out.write(str(net) + "\n")

print("ASN merge done.")
