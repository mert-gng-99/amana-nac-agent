## Amana - A cost-aware fraud agent for cross-border transfers

Amana is an AI agent that decides which network check a transfer is worth, instead of calling every CAMARA API on every payment. It separates a migrant worker's ordinary life abroad from the shape of an account takeover, and it explains every hold in one sentence.

### The problem

Every bank can call a SIM swap API. Knowing when it is worth calling is the product. Amana is paid for the checks it does not run.

### What the prototype actually does

Amana is a working web application with an operator console, a REST API, and
a live WebSocket feed of the agent's reasoning. Open it, click a scenario, and
you watch the agent choose CAMARA calls one at a time and then justify its
decision with the network answers behind it.

It runs in three modes. `simulator` needs no credentials and answers every
CAMARA call in the real CAMARA response shape, which is how the organisers
recommend demonstrating and how the test suite stays deterministic. `live`
calls the Nokia Network-as-Code gateway with your own key. `hybrid` uses live
where credentials allow and falls back per call. Every answer is tagged with
its source in the UI, so a simulated result can never pass itself off as a real
network answer.

### The AI agent layer

The agent is a planner over a CAMARA tool registry, not a script with an LLM
bolted on. Each tool in the registry carries its price, its typical latency and
how much it reveals about a person, and the planner is judged on choosing well:

1. The planner proposes one call, with a stated reason.
2. The runtime, never the model, checks it against the tool allowlist, the
   consent ledger and the remaining budget.
3. The CAMARA answer is recorded with full provenance and turned into a fact.
4. Repeat until the planner submits a decision, or the budget runs out.

The planner is Google AI Studio (Gemini) through **Pydantic AI**'s typed,
structured-output path. It is enabled by setting `AGENT_PROVIDER=gemini`
alongside a `GEMINI_API_KEY`. A model turn may only propose a next CAMARA check
or a decision; it cannot execute a network call itself. The runtime remains the
only executor of consent, the tool allowlist, argument filtering and budget.

Gemini is opt-in on both counts deliberately: a key sitting in the environment
should not be enough to start spending on a model. Otherwise a deterministic
policy planner implementing the same escalation ladder takes over, so the
prototype is demonstrable offline and CI has something stable to assert. If a
configured model cannot complete a turn, the finished case is explicitly
labelled `policy-fallback` with a bounded error reason. It is never presented
as a successful Gemini-planned decision.

**The guardrail is the part worth looking at.** The policy computes a floor for
every case from the facts alone. If the model proposes something less cautious
than the floor, the floor wins and the disagreement is written into the
decision record. A language model should choose which checks to buy; it should
not be able to clear a case the evidence says to escalate. There is a test for
exactly this.

### Results from the shipped scenarios

6 scenarios ship with the prototype, and all 6 reach the
outcome they claim. The demo and the test suite assert the same thing, so a
scenario drifting from the pitch is a build failure.

- Outcome levels reached: `clear`, `review`, `hold`, `block`
- CAMARA calls per case: 1 to 5 (average 3.5)
- Total spend across all scenarios: 35 units, against 72 if
  every available check were called on every case, a saving of 51.4%

| Scenario | Outcome | CAMARA calls | Spend |
| --- | --- | --- | --- |
| Friday payday remittance | `clear` | 1 | 1 |
| First transfer to a new receiver | `review` | 4 | 6 |
| SIM changed six hours ago | `block` | 5 | 9 |
| Same signal, nine days older | `hold` | 5 | 9 |
| New phone, same person | `review` | 5 | 9 |
| The network will not confirm the line | `block` | 1 | 1 |

The cheapest case, *Friday payday remittance*, resolves in 1 call(s). The
most expensive, *SIM changed six hours ago*, earns 5. That gap is the product:
an agent that calls everything on everyone is safe, useless and unaffordable.

### CAMARA APIs on Nokia Network as Code

`number-verification`, `sim-swap`, `device-swap`, `device-status`

| CAMARA API | What the agent asks it | Cost | Reveals |
| --- | --- | --- | --- |
| `number-verification` | Confirm the line on the phone | 1 | boolean |
| `sim-swap` | Has the SIM changed recently | 3 | boolean |
| `sim-swap` | When did the SIM last change | 3 | enum |
| `device-swap` | Has the handset changed recently | 3 | boolean |
| `device-status` | Is the line roaming, and where | 1 | enum |
| `device-status` | Can the line be reached | 1 | enum |

### Consent

CAMARA identity, location and geofencing APIs are only lawful with the consent
of the line owner, so consent is enforced in the transport path rather than
described in a policy document. An ungranted call raises before a request is
built.

Consent is taken at the moment of the transfer, in the app, before the agent
runs, from the account holder, who is the line owner and the person asking for
the transfer. The grant covers this transfer decision only and expires with
it. A customer who declines consent can still transfer; the agent simply has
no network evidence and the transfer falls back to the bank's existing manual
path.

You can prove this in the running app: press **Withdraw consent**, run the same
case again, and watch the agent get refused at the transport layer with zero
CAMARA calls made.

### What this does not do

- Amana cannot see a customer who was talked into sending money willingly. Social engineering leaves no trace in the network, and no CAMARA API will ever find it.
- A SIM swap check answers for the line, not for the person. A family member using the same phone with permission looks identical to the rightful owner.
- Consent is required. A customer who declines leaves the agent blind, which is the correct trade and does mean coverage is never total.
- The simulator here is not a fraud model. Real deployment needs the bank's own history to set thresholds; the numbers in this prototype are ours.

### Who pays

- Banks and exchange houses paying per decision, priced below what they already spend on SMS one-time codes
- Digital wallets and remittance apps in the Gulf corridors
- Mobile operators, who earn from every CAMARA call the agent does buy

### Verification

Run `pytest -q` in the repository. The suite covers the CAMARA transport and
its provenance, the consent gate, budget enforcement, the tool allowlist, the
guardrail floor overruling an over-confident model, the LLM planner loop
against a scripted model, the full HTTP surface, and every shipped scenario.
