#!/usr/bin/env bash
# NYC1 side: the "customer's" private network. Postgres + listings MCP server.
# Team: Solutions Demos. Everything is tagged pricelabs-demo (see teardown.sh).
set -euo pipefail
C=(--context "solutions demos")
TAG=pricelabs-demo
MY_IP=${MY_IP:-$(curl -s4 https://ifconfig.me)}
cd "$(dirname "$0")"

VPC=$(doctl "${C[@]}" vpcs list --format ID,Name --no-header | awk '$2=="pricelabs-nyc1"{print $1}')
[ -n "$VPC" ] || VPC=$(doctl "${C[@]}" vpcs create --name pricelabs-nyc1 --region nyc1 --ip-range 10.150.0.0/20 \
      --description "PriceLabs demo: private data network" -o json | python3 -c 'import json,sys; d=json.load(sys.stdin); print((d[0] if isinstance(d,list) else d)["id"])')
echo "VPC $VPC"

doctl "${C[@]}" databases create pricelabs-pg --engine pg --version 17 --region nyc1 \
  --size db-s-1vcpu-1gb --num-nodes 1 --private-network-uuid "$VPC" --tag "$TAG"

cat > /tmp/pricelabs-cloudinit.yaml <<EOF
#cloud-config
users:
  - name: demo
    sudo: ALL=(ALL) NOPASSWD:ALL
    shell: /bin/bash
    ssh_authorized_keys:
      - $(cat ~/.ssh/id_ed25519.pub)
package_update: true
packages: [python3-venv, postgresql-client]
EOF
doctl "${C[@]}" compute droplet create pricelabs-mcp --region nyc1 --size s-1vcpu-2gb \
  --image ubuntu-24-04-x64 --vpc-uuid "$VPC" --tag-name "$TAG" \
  --user-data-file /tmp/pricelabs-cloudinit.yaml --wait --format ID,PublicIPv4,PrivateIPv4

# Public side: SSH from the presenter's IP only. MCP port only from private ranges
# (this VPC and the peered RIC1 VPC that Action Gateway uses).
doctl "${C[@]}" compute firewall create --name pricelabs-mcp-fw --tag-names "$TAG" \
  --inbound-rules "protocol:tcp,ports:22,address:${MY_IP}/32 protocol:tcp,ports:8080,address:10.150.0.0/20 protocol:tcp,ports:8080,address:10.151.0.0/20" \
  --outbound-rules "protocol:tcp,ports:all,address:0.0.0.0/0 protocol:udp,ports:all,address:0.0.0.0/0 protocol:icmp,address:0.0.0.0/0"
