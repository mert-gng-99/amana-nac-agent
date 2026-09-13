# Amana

> A cost-aware fraud agent for cross-border transfers

**MENA Ignite Hackathon - GSMA Open Gateway - Theme 4: Secure Fintech, Payments & Anti-Fraud Innovation**

Every bank can call a SIM swap API. Knowing when it is worth calling is the product. Amana is paid for the checks it does not run.

Amana is an AI agent that decides which network check a transfer is worth, instead of calling every CAMARA API on every payment. It separates a migrant worker's ordinary life abroad from the shape of an account takeover, and it explains every hold in one sentence.

---

## Quick start

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open http://localhost:8000. You need no credentials, because the app starts in
`simulator` mode and every answer is tagged with its source.

Full instructions, including the Gemini planner and the live Nokia gateway, are
in **INSTRUCTIONS.md**. The design is in **ARCHITECTURE.md**.

## What it is

An AI agent that decides *which* CAMARA network check is worth making for a
given case, spends against a budget, refuses calls it has no consent for, and
explains every decision with the network answers behind it.

- **6 scenarios** ship with it, all reaching the outcome they claim
- **4 CAMARA APIs** on the Nokia Network-as-Code platform
- **51.4% cheaper** than calling every available check on every case
- **1 to 5 calls** per case, depending on what the case deserves

## Scenarios

- Friday payday remittance. 320 USD to a receiver he has used for years, line roaming in Saudi Arabia (expects `clear`)
- First transfer to a new receiver. 2,400 USD, customer three weeks old, receiver never used before (expects `review`)
- SIM changed six hours ago. 4,800 USD to a receiver never used before, at 03:00 local (expects `block`)
- Same signal, nine days older. 5,000 USD to a new receiver, SIM changed nine days ago (expects `hold`)
- New phone, same person. 6,000 USD to a receiver used for years, handset changed yesterday (expects `review`)
- The network will not confirm the line. 900 USD from a handset that does not hold this number (expects `block`)

## CAMARA APIs used

| CAMARA API | What the agent asks it | Cost | Reveals |
| --- | --- | --- | --- |
| `number-verification` | Confirm the line on the phone | 1 | boolean |
| `sim-swap` | Has the SIM changed recently | 3 | boolean |
| `sim-swap` | When did the SIM last change | 3 | enum |
| `device-swap` | Has the handset changed recently | 3 | boolean |
| `device-status` | Is the line roaming, and where | 1 | enum |
| `device-status` | Can the line be reached | 1 | enum |

## The agent

```
planner proposes one call  ->  runtime checks allowlist, consent, budget
      ^                                        |
      |                                        v
  answer becomes a fact   <-   CAMARA call recorded with provenance
      |
      +--> planner submits a decision  ->  policy floor applied  ->  ledger
```

The planner is Google AI Studio (Gemini) through Pydantic AI when
`AGENT_PROVIDER=gemini` and a `GEMINI_API_KEY` are both set, and a deterministic
policy ladder otherwise. Pydantic AI returns a typed proposal only; the runtime
still holds the budget, allowlist and consent gate, and the policy holds a floor
the model cannot talk its way under.

## Tests

```bash
pytest -q
```

## What this does not do

- Amana cannot see a customer who was talked into sending money willingly. Social engineering leaves no trace in the network, and no CAMARA API will ever find it.
- A SIM swap check answers for the line, not for the person. A family member using the same phone with permission looks identical to the rightful owner.
- Consent is required. A customer who declines leaves the agent blind, which is the correct trade and does mean coverage is never total.
- The simulator here is not a fraud model. Real deployment needs the bank's own history to set thresholds; the numbers in this prototype are ours.

## Layout

```
main.py            uvicorn entry point
app_spec.py        re-exports this product's spec
core/              shared platform: CAMARA client, agent, consent, ledger, UI
  camara.py        the eleven CAMARA API families, live + simulator
  simulator.py     deterministic network simulator
  agent.py         the agent loop, budget, guardrail
  tools.py         CAMARA tool registry with cost and reveal metadata
  consent.py       consent ledger enforced in the transport path
  ledger.py        SQLite decision ledger
  signals.py       CAMARA answers -> named facts
  server.py        FastAPI app
  webui.py         the operator console
idea/              this product: policy, scenarios, demo lines, copy
tests/             pytest suite
```

## Licence

MIT. See LICENSE.
