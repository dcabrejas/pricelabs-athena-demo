# Action Gateway setup (Console, Solutions Demos team)

Action Gateway runs in **RIC1** only. The listings MCP server lives in the
private **NYC1** VPC. The two VPCs are peered, so Action Gateway reaches the
server over private addresses. Nothing about it is public.

| Thing | Value |
|---|---|
| RIC1 VPC (Action Gateway side) | `pricelabs-ric1` · `0089c75c-d005-4add-b9d7-b890aed6ccbe` · 10.151.0.0/20 |
| NYC1 VPC (data side) | `pricelabs-nyc1` · `ae605fca-ab9a-4ff3-8872-56c1b413d903` · 10.150.0.0/20 |
| Peering | `pricelabs-nyc1-ric1` (ACTIVE) |
| MCP server URL | `http://10.150.0.4:8080/mcp` (Streamable HTTP) |
| MCP auth | API key, header `X-API-Key`, value = `MCP_API_KEY` in `.env.local` |
| Tools it exposes | `describe_schema`, `run_readonly_sql` (read-only role, 15 s timeout, 500-row cap) |

## 0. Check the team has VPC access

Go to Managed Agents → Action Gateway → Tool Providers → **Add custom provider**.
If the **Reach this server in a VPC** option is missing or greyed out, VPC
access isn't enabled for Solutions Demos. Ask in #mars-internal-testing or
Support to enable "Action Gateway VPC access + private discovery in ric1".
Fallback: README "Fallbacks".

## 1. Register the custom provider

- Name: `listings-db`
- Transport: Streamable HTTP · URL: `http://10.150.0.4:8080/mcp`
- Check **Reach this server in a VPC** → Server VPC: `pricelabs-ric1`
- Auth: **None**. Action Gateway only accepts a plain-HTTP private URL with
  no authentication. The firewall (8080 open only to the two VPC ranges) and
  the read-only DB role are the boundary. With HTTPS you could add an API key.

Discovery should list both tools. If it fails, see "Troubleshooting" below.

## 2. Create the provider connection

- Provider: `listings-db` · VPC: `pricelabs-ric1` (the same VPC as step 1)
- Allowed destination: `10.150.0.4`, port `8080`
- Actor: leave the default (your actor, `dcabrejas`). Harness Runtime
  sessions created by you use the same actor.

## 3. Nothing to build: check the actor and the enabled tools

Harness Runtime creates an Action Gateway endpoint for each session by itself
(`tools: [do.actions]` in `env/athena.yaml`), so you don't create an endpoint.
Two things must line up:

- **Tools enabled on the provider.** On the provider's *Server tools* page,
  `describe_schema` and `run_readonly_sql` must be enabled. Disabled tools
  still show up in search but can't be invoked.
- **A connection for the session's actor.** Connections are per actor ID.
  Sessions you create use your default actor: the part of your email before
  the @ (`dcabrejas`). The connection's **Actor ID** must be exactly that,
  with VPC `pricelabs-ric1`, destination `10.150.0.4`, port `8080`.

Verified 27 Nov: the session finds `listings-db_run_readonly_sql` and
`listings-db_describe_schema`. Discovery traffic reaches the server from
`10.151.0.2`, inside `pricelabs-ric1`, over the peering.

## 4. Smoke test (before Harness Runtime)

In the endpoint's playground, or with any MCP client against the endpoint URL:
`run_readonly_sql` with `select count(*) from listings` should return 2190.

## Troubleshooting

- **Discovery or calls time out.** The Droplet's cloud firewall
  (`pricelabs-mcp-fw`) allows 8080 only from 10.150.0.0/20 and 10.151.0.0/20.
  If Action Gateway's private traffic comes from another range, check
  `journalctl -u listings-mcp` on the Droplet. If no request arrives, ask
  Support for Action Gateway's private source range and add it to the firewall.
- **401 in the MCP logs.** Wrong header name or key in the connection.
- **HTTP vs HTTPS.** If the provider form insists on `https://`, tell me. I'll
  put Caddy with an internal certificate in front of 8080.
