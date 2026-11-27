# Athena on DigitalOcean: PriceLabs demo

A LangChain **Deep Agents** revenue agent, deployed unchanged on **Harness
Runtime**. It uses **Serverless Inference** (Kimi K3.1 Pro) for the model,
**Action Gateway** for tools, and **private Postgres in NYC1** reached through
an MCP server. One prompt, 96–125 s in rehearsal (3 runs, same top 10 each time).

> "Coastal Stays manages 2,000 listings. Review the next 30 days, find
> underpriced listings, and push new prices for the top 10."

## What runs where

| Piece | Where | Stands in for |
|---|---|---|
| `agent/`: Deep Agent (`create_deep_agent`), `langgraph.json` | Harness Runtime session, RIC1 (`agent: langgraph`) | Athena |
| Model | Serverless Inference, `kimi-k3.1-pro`, internal VPC endpoint | OpenRouter → OpenAI |
| `agent/pricing_agent/tools.py`: local tools | Inside the session's sandbox | Athena's Python tools |
| `pricing-api/`: pricing service, HTTPS | NYC1 Droplet behind Caddy, `https://pricing.134-209-209-90.sslip.io` | Their Rails app |
| `mcp-server/`: listings-db MCP | NYC1 Droplet, **private** `10.150.0.4:8080` | Steve's "simple MCP" |
| Postgres 17, about 800k listing-nights | NYC1 Managed DB in VPC `pricelabs-nyc1`, trusted source = Droplet only | Their Postgres |
| Action Gateway | Named endpoint `athena-demo` (actor `dcabrejas`, VPC `pricelabs-ric1`, RIC1); reaches the MCP over the VPC peering `pricelabs-ric1 ↔ pricelabs-nyc1` | |
| `action_code` | Action Gateway's ephemeral Python sandbox; scores and ranks the aggregated candidates | "a sandbox that writes code" |

Team: **Solutions Demos**. Secrets live in `.env.local` (gitignored). The
GitHub repo is public: https://github.com/dcabrejas/pricelabs-athena-demo

## Run it

```bash
cd ~/Code/do-claude-scratchpad/pricelabs-demo
set -a; . ./.env.local; set +a
export FRAMEWORK_REPO_SHA=$(git rev-parse HEAD)   # push first: the session clones this commit
export AG_MCP_HOST=ric1.actions.do-ai.run           # host of AG_MCP_URL, for the egress allowlist
curl -s -X POST -H "Authorization: Bearer $PRICING_API_TOKEN" $PRICING_API_URL/audit/reset
doctl --context "solutions demos" harness-runtime create --spec env/athena-endpoint.yaml --name athena-live
```

The prompt for the call:

```bash
doctl --context "solutions demos" harness-runtime prompt athena-live "Coastal Stays (customer 'Coastal Stays') manages 2,000 listings. Review pricing for the next 30 days: find listings that are underpriced versus their comp set while filling at or above comp occupancy, check whether upcoming market events explain the demand, then get recommendations and push new prices for the top 10. Keep raw nightly data out of the conversation."
```

Show the pushes: open `https://pricing.134-209-209-90.sslip.io/?token=$PRICING_API_TOKEN`.
Reset between rehearsals: `curl -X POST -H "Authorization: Bearer $PRICING_API_TOKEN" https://pricing.134-209-209-90.sslip.io/audit/reset`

Replay the run's events: `doctl --context "solutions demos" harness-runtime logs athena-live`

## Talk track (about 8 beats)

1. **Their stack, unchanged.** Open `agent/pricing_agent/agent.py`. It's plain
   `create_deep_agent(...)`, with no DO SDK. `langgraph.json` points at it.
   Harness Runtime clones the repo at a pinned commit and runs it.
2. **Model swap is one line.** `ChatOpenAI(base_url=…)` points at Serverless
   Inference. The model here is open-weights Kimi K3.1 Pro, and the same code
   works with OpenAI or Anthropic models on SI. Inference stays on DO's internal
   network.
3. **Send the prompt.** The plan appears (`write_todos`).
4. **Heavy data pull, done right.** The agent calls the private
   `listings-db_run_readonly_sql` tool with GROUP BY queries, so Postgres
   aggregates 60,000 listing-nights (from about 800k in the DB) and only about
   55 rows come back. It then writes Python that runs in `action_code` to score
   and rank them. Its final line reports "listing-nights analysed vs rows that
   entered the conversation". This is the answer to "customers with many
   listings": the model never sees
   the raw data.
5. **Private connectivity.** Postgres is in a private NYC1 VPC, with no public
   path in (show the DB trusted sources: Droplet only). Action Gateway reaches
   the MCP server over a NYC1↔RIC1 VPC peering. The server log shows the
   calls arriving from `10.151.0.2`, inside the RIC1 VPC. That is Steve's MCP
   idea, working. The MCP is plain HTTP with no auth: for private HTTP URLs the
   gateway requires that, so the VPC, firewall, the connection's allowed
   host:port and a read-only DB role are the boundary.
6. **Web search through Action Gateway** confirms the market events
   (Winterfest, ski opening).
7. **Their Rails pattern.** `get_price_recommendation` / `apply_price_change`
   are ordinary Python tools in the repo. They call a separate pricing service
   (Rails, in their world), which owns the guardrails (max +35%). Show the
   audit page with 10 pushes.
8. **Long-running work.** `doctl harness-runtime pause` / `resume` on the
   session keeps its state; checkpoints and forks exist too. Coming soon:
   Harness Runtime as a native Deep Agents *sandbox backend* (internal package
   today), so the agent's own shell and files can live in a session.

## Pooja's other questions (short answers)

- **One session per customer.** Each customer's work runs in its own session
  (`--name athena-<customer>`). The actor caveat: Action Gateway connections
  are tied to the actor of the DO user who creates the session, so per-customer
  *connected accounts* need one endpoint per customer, attached as an inline
  MCP server. We raised this with the Action Gateway team (Diego's thread).
- **Serverless Inference** works as a drop-in for OpenRouter: an
  OpenAI-compatible `/v1`, one key, many models (`router:` model routing too).
- **Deep Agents compatibility.** The `langgraph` harness runs it today, as
  shown. The internal `langchain-digitalocean-harness-runtime` package (sandbox
  backend) isn't customer-shareable yet; ask Calin Lupa.

## Fallbacks

- **Private Action Gateway path not working on the day:** make the MCP server
  public behind Action Gateway's 5 fixed IPs (`129.212.241.165`,
  `209.38.2.205`, `165.245.149.125`, `165.245.156.118`, `24.144.69.169`) and
  explain the private path verbally.
- **The named endpoint or its token fails:** check the token hasn't expired
  (read + execute on action_gateway) and `AG_MCP_URL` is the endpoint's head URL.
- **Live run misbehaves:** play the recorded run (`logs`) or the backup video.

## Gotchas found while building

- doctl wants `agent: langgraph` in the spec; the docs page shows `harness:`.
- In a langgraph session the gateway exposes only the meta tools
  (`action_search` / `action_invoke` / `action_code`) unless you set
  `preload_tools`.
- `HARNESS_MCP_URL_DO_ACTIONS` and `HARNESS_INFERENCE_BASE_URL` are injected
  (internal VPC endpoints). Don't override the base URL.
- The catalog web search is `brightdata_web_search` (not Exa) on this team.
- Model access keys can no longer be created through the API; use the Console.
- MCP Python SDK 2.x renamed FastMCP; the server pins `mcp==1.30.0`.

## Why a named endpoint, not `tools: [do.actions]`

- With `do.actions`, the per-session endpoint calls with an empty actor, so it
  only sees providers **shared with the team**. A custom provider registered by
  a non-owner can't be shared ("provider_not_shared"). `env/athena.yaml` is the
  `do.actions` variant, for once a team owner shares `listings-db`.
- Code inside `action_code` calling `invoke_digitalocean_tool('listings-db_…')`
  hits the same error even through the named endpoint: the code sandbox calls
  tools as the team. Direct tool calls from the agent work. Direct HTTP from
  `action_code` into the VPC also works, but it bypasses tool policy, so the demo
  doesn't use it.
- Both are worth raising with the Action Gateway team. PriceLabs would hit them
  too (see the actor-per-session question).

## Teardown

`infra/teardown.sh`, then delete the Action Gateway endpoint `athena-demo`, provider and connection in the Console, and revoke the endpoint token.
