#!/usr/bin/env bash
# Remove everything the PriceLabs demo created in Solutions Demos.
# Action Gateway provider/connection: delete by hand in the Console (see ag-setup.md).
set -uo pipefail
C=(--context "solutions demos")

for s in $(doctl "${C[@]}" harness-runtime list --format Name --no-header | grep '^athena-'); do
  doctl "${C[@]}" harness-runtime remove "$s"
done
doctl "${C[@]}" compute droplet delete pricelabs-mcp --force
doctl "${C[@]}" databases delete "$(doctl "${C[@]}" databases list --format ID,Name --no-header | awk '$2=="pricelabs-pg"{print $1}')" --force
doctl "${C[@]}" compute firewall delete "$(doctl "${C[@]}" compute firewall list --format ID,Name --no-header | awk '$2=="pricelabs-mcp-fw"{print $1}')" --force
doctl "${C[@]}" vpcs peerings delete "$(doctl "${C[@]}" vpcs peerings list --format ID,Name --no-header | awk '$2=="pricelabs-nyc1-ric1"{print $1}')" --force
echo "Wait for the droplet and DB to finish deleting, then:"
echo "  doctl --context 'solutions demos' vpcs delete <pricelabs-nyc1 id> --force"
echo "  pricelabs-ric1 is the team's default RIC1 VPC; it can stay (no cost) or be deleted once another default exists."
