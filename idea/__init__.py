"""Amana product spec: theme 4, secure fintech, payments and anti-fraud."""

from __future__ import annotations

from core.agent import Case
from core.idea import ConsentPlan, IdeaSpec, LevelStyle, Scenario, UiSpec
from core.simulator import LineProfile

from .policy import AmanaPolicy

POLICY = AmanaPolicy()

# --- demo lines --------------------------------------------------------------
# Each line is a story the simulator will tell consistently across every API.

LINE_PAYDAY = LineProfile(
    msisdn="+966500000101",
    label="Long-standing customer, living and working in Riyadh",
    roaming=True,
    country_code=966,
    country_name="SAU",
    notes="Roaming for two years. The case the old rule engine keeps getting wrong.",
)

LINE_NEW_RECEIVER = LineProfile(
    msisdn="+966500000102",
    label="Three weeks with the bank, first transfer to a new receiver",
    roaming=True,
    country_code=966,
    country_name="SAU",
    notes="Nothing wrong with the line. Everything unusual is in the transfer itself.",
)

LINE_FRESH_SWAP = LineProfile(
    msisdn="+966500000103",
    label="SIM changed six hours ago",
    sim_swap_hours_ago=6,
    roaming=True,
    country_code=966,
    country_name="SAU",
    notes="The takeover shape: fresh SIM, large amount, receiver never used before.",
)

LINE_OLD_SWAP = LineProfile(
    msisdn="+966500000104",
    label="SIM changed nine days ago",
    sim_swap_hours_ago=216,
    roaming=True,
    country_code=966,
    country_name="SAU",
    notes="Same signal as the takeover, nine days out. Should not get the same answer.",
)

LINE_NEW_HANDSET = LineProfile(
    msisdn="+966500000105",
    label="Same SIM, new phone since yesterday",
    device_swap_hours_ago=20,
    roaming=True,
    country_code=966,
    country_name="SAU",
    notes="A person who bought a phone, not a person who stole an account.",
)

LINE_UNVERIFIED = LineProfile(
    msisdn="+966500000106",
    label="Network will not confirm this line belongs to this handset",
    number_verified=False,
    roaming=True,
    country_code=966,
    country_name="SAU",
    notes="One unit of spend ends the case.",
)


def _transfer(subject: str, label: str, **facts) -> Case:
    base = {
        "currency": "USD",
        "corridor": "SAU -> PAK",
        "declared_country": "SAU",
        "hour_local": 14,
        "customer_tenure_days": 1400,
        "receiver_new": False,
    }
    base.update(facts)
    return Case(subject=subject, kind="transfer", facts=base, label=label)


SCENARIOS = [
    Scenario(
        id="payday-remittance",
        title="Friday payday remittance",
        subtitle="320 USD to a receiver he has used for years, line roaming in Saudi Arabia",
        expect_level="clear",
        lines=[LINE_PAYDAY],
        narrative="The transfer that a classic rule engine holds and should not.",
        teaches=(
            "The agent buys one call, confirms the line, and stops. Roaming, an "
            "overseas corridor and a third-country receiver are this customer's "
            "ordinary life, so none of them buy a single extra check."
        ),
        build_case=lambda: _transfer(
            LINE_PAYDAY.msisdn,
            "Friday payday remittance",
            amount=320,
            customer_tenure_days=1460,
        ),
    ),
    Scenario(
        id="new-receiver-large",
        title="First transfer to a new receiver",
        subtitle="2,400 USD, customer three weeks old, receiver never used before",
        expect_level="review",
        lines=[LINE_NEW_RECEIVER],
        narrative="Two unusual things about the transfer, nothing wrong with the line.",
        teaches=(
            "Here the agent does spend: a SIM swap check, then a roaming "
            "consistency check. Both come back clean, so the transfer is released "
            "and flagged rather than held. Friction is a cost too."
        ),
        build_case=lambda: _transfer(
            LINE_NEW_RECEIVER.msisdn,
            "First transfer to a new receiver",
            amount=2400,
            receiver_new=True,
            customer_tenure_days=21,
        ),
    ),
    Scenario(
        id="sim-swap-fresh",
        title="SIM changed six hours ago",
        subtitle="4,800 USD to a receiver never used before, at 03:00 local",
        expect_level="block",
        lines=[LINE_FRESH_SWAP],
        narrative="The account takeover this product exists to stop.",
        teaches=(
            "The agent finds the swap, then spends again on the timestamp, because "
            "the gap between the change and the payment is what separates a block "
            "from a hold. Six hours is a block."
        ),
        build_case=lambda: _transfer(
            LINE_FRESH_SWAP.msisdn,
            "Large transfer hours after a SIM change",
            amount=4800,
            receiver_new=True,
            hour_local=3,
            customer_tenure_days=610,
        ),
    ),
    Scenario(
        id="sim-swap-nine-days",
        title="Same signal, nine days older",
        subtitle="5,000 USD to a new receiver, SIM changed nine days ago",
        expect_level="hold",
        lines=[LINE_OLD_SWAP],
        narrative="Identical CAMARA answer, different decision.",
        teaches=(
            "A yes/no SIM swap check would have blocked this too. Because the agent "
            "pays for the timestamp it can tell nine days from six hours, and holds "
            "for one confirmation instead of refusing a real customer."
        ),
        build_case=lambda: _transfer(
            LINE_OLD_SWAP.msisdn,
            "Large transfer nine days after a SIM change",
            amount=5000,
            receiver_new=True,
            customer_tenure_days=980,
        ),
    ),
    Scenario(
        id="new-handset",
        title="New phone, same person",
        subtitle="6,000 USD to a receiver used for years, handset changed yesterday",
        expect_level="review",
        lines=[LINE_NEW_HANDSET],
        narrative="A device change that most systems treat as a takeover.",
        teaches=(
            "The SIM is untouched, so the agent reads the handset change as a person "
            "who bought a phone. The amount earns a review afterwards; it does not "
            "earn a hold now."
        ),
        build_case=lambda: _transfer(
            LINE_NEW_HANDSET.msisdn,
            "Large transfer from a new handset",
            amount=6000,
            customer_tenure_days=1850,
        ),
    ),
    Scenario(
        id="unverified-line",
        title="The network will not confirm the line",
        subtitle="900 USD from a handset that does not hold this number",
        expect_level="block",
        lines=[LINE_UNVERIFIED],
        narrative="The cheapest call in the catalogue, doing the most work.",
        teaches=(
            "One unit of number verification ends the case. The agent buys nothing "
            "else, because nothing else could change the answer."
        ),
        build_case=lambda: _transfer(
            LINE_UNVERIFIED.msisdn,
            "Transfer from an unverified line",
            amount=900,
            receiver_new=True,
            customer_tenure_days=95,
        ),
    ),
]

SPEC = IdeaSpec(
    slug="amana",
    name="Amana",
    tagline="A cost-aware fraud agent for cross-border transfers",
    theme_number=4,
    theme_name="Secure Fintech, Payments & Anti-Fraud Innovation",
    submission_title="Amana - a cost-aware fraud agent for cross-border transfers",
    submission_description=(
        "Amana is an AI agent that decides which network check a transfer is "
        "worth, instead of calling every CAMARA API on every payment. It "
        "separates a migrant worker's ordinary life abroad from the shape of an "
        "account takeover, and it explains every hold in one sentence."
    ),
    policy=POLICY,
    scenarios=SCENARIOS,
    lines=[
        LINE_PAYDAY,
        LINE_NEW_RECEIVER,
        LINE_FRESH_SWAP,
        LINE_OLD_SWAP,
        LINE_NEW_HANDSET,
        LINE_UNVERIFIED,
    ],
    consent=ConsentPlan(
        moment="at the moment of the transfer, in the app, before the agent runs",
        scopes=[
            "identity:verify",
            "fraud:sim-swap",
            "fraud:device-swap",
            "device:status",
        ],
        who_consents="the account holder, who is the line owner and the person asking for the transfer",
        duration_note="The grant covers this transfer decision only and expires with it.",
        revocation=(
            "A customer who declines consent can still transfer; the agent simply "
            "has no network evidence and the transfer falls back to the bank's "
            "existing manual path."
        ),
    ),
    ui=UiSpec(
        accent="#2f9e6b",
        accent_soft="#e6f5ee",
        hero_kicker=(
            "Every bank can call a SIM swap API. Knowing when it is worth calling "
            "is the product. Amana is paid for the checks it does not run."
        ),
        subject_label="Customer line (MSISDN)",
        case_label="Transfer",
        run_all_label="Run all six transfers",
        ad_hoc_placeholder="+966500000103",
        ad_hoc_help=(
            "Any number works. Unregistered lines get a stable profile derived "
            "from the number itself, so the same number always behaves the same way."
        ),
        levels=[
            LevelStyle("clear", "Clear - release now", "calm",
                       "Nothing in the network contradicts the customer."),
            LevelStyle("review", "Review - release and flag", "watch",
                       "Released, recorded, looked at afterwards."),
            LevelStyle("hold", "Hold - step up first", "warn",
                       "One confirmation before the money moves."),
            LevelStyle("block", "Block - refuse and verify out of band", "alarm",
                       "The network evidence says stop."),
        ],
    ),
    honest_limits=[
        "Amana cannot see a customer who was talked into sending money willingly. "
        "Social engineering leaves no trace in the network, and no CAMARA API will "
        "ever find it.",
        "A SIM swap check answers for the line, not for the person. A family member "
        "using the same phone with permission looks identical to the rightful owner.",
        "Consent is required. A customer who declines leaves the agent blind, which "
        "is the correct trade and does mean coverage is never total.",
        "The simulator here is not a fraud model. Real deployment needs the bank's "
        "own history to set thresholds; the numbers in this prototype are ours.",
    ],
    buyers=[
        "Banks and exchange houses paying per decision, priced below what they "
        "already spend on SMS one-time codes",
        "Digital wallets and remittance apps in the Gulf corridors",
        "Mobile operators, who earn from every CAMARA call the agent does buy",
    ],
    repo_name="amana-nac-agent",
    demo_notes=(
        "Run the two SIM swap scenarios back to back. Both return the same CAMARA "
        "answer; only the timestamp differs, and the decisions differ with it."
    ),
)
