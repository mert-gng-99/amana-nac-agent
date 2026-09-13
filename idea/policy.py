"""Amana - a cost-aware fraud agent for cross-border transfers.

The problem this policy exists to solve is not detection. Every bank can call a
SIM swap API. The problem is that a cross-border worker looks strange to a rule
engine - new country, new device, odd hours, a receiver in a third country -
and all of that is simply his life. Rules fire, the transfer is held, and an
honest customer walks to a cash agent instead. Meanwhile the real attacker
moves the number to a new SIM and reads the code out of the SMS.

So the agent is built around one question: which check is worth buying for
*this* transfer. Three rules follow from it.

**Spend against the stakes.** Budget scales with the amount. A 90 dollar
remittance gets one call. A 6,000 dollar first-time transfer earns more.

**Buy the signal that could change the answer.** Not every signal - the one
that moves the decision most, which for a takeover is almost always how many
hours sit between a SIM change and the payment.

**Roaming is never a red flag on its own.** A line that has been on a visited
network for two years is a migrant worker. A SIM changed six hours before a
first transfer to a new receiver is something else. Keeping those apart is most
of the value here, and the test suite asserts it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from core.agent import Case
from core.camara import ApiResult
from core.signals import read_signal

# Least severe to most severe. The agent runtime uses this order to hold a
# floor: a planner may never propose something lower than the evidence allows.
LEVELS = ["clear", "review", "hold", "block"]

BIG_USD = 1000.0
VERY_BIG_USD = 4000.0
THIN_TENURE_DAYS = 30

# A SIM change this close to a payment is the shape of a takeover, not an upgrade.
FRESH_SWAP_H = 24.0
NEAR_SWAP_H = 72.0
SWAP_LOOKBACK_H = 240


class AmanaPolicy:
    name = "amana"
    kind = "transfer"
    levels = LEVELS
    budget_units = 14.0

    tool_names = [
        "verify_number",
        "check_sim_swap",
        "sim_swap_date",
        "check_device_swap",
        "check_roaming",
        "check_reachability",
    ]

    # -- prompt --------------------------------------------------------------

    def system_prompt(self, case: Case) -> str:
        return (
            "You are Amana, the decision agent inside a cross-border payments "
            "provider in the Gulf. For each transfer you decide: clear, review, "
            "hold or block.\n\n"
            "You are paid for the checks you do NOT run. Calling every CAMARA "
            "API on every transfer is safe and far too expensive, and it is the "
            "trap most network-API demos fall into. Your job is to buy the one "
            "signal that could change this decision, and then stop.\n\n"
            "How to think:\n"
            "1. Confirm the line on the phone first. It costs almost nothing and "
            "an unverified line ends the case immediately.\n"
            "2. Most transfers are boring. If nothing about this one is odd and "
            "the amount is small, decide clear without buying anything else.\n"
            "3. When something is odd, ask what single answer would move the "
            "decision most. For a suspected takeover that is a SIM change, and "
            "specifically how many hours sit between the change and this "
            "payment. Fewer than 24 hours is a different case from nine days.\n"
            "4. Roaming is NOT evidence of fraud. Most of these customers live "
            "abroad; a line that is roaming in the country the customer declared "
            "is normal life. Use roaming only to check a declared country "
            "against reality, never to escalate on its own.\n"
            "5. A new handset with the same SIM is usually the same person with "
            "a new phone. Weigh it, do not block on it.\n\n"
            "Every answer you give must name the network signals behind it in "
            "one or two sentences a support agent could read out to the customer. "
            "A hold nobody can explain is worse than no hold at all."
        )

    def describe_case(self, case: Case) -> str:
        f = case.facts
        return (
            "Transfer %s\n"
            "  amount: %s %s\n"
            "  corridor: %s\n"
            "  receiver: %s\n"
            "  customer with us: %s days\n"
            "  local time: %02d:00\n"
            "  country the customer says they are in: %s\n"
            "  line: %s"
            % (
                case.case_id,
                f.get("amount"),
                f.get("currency", "USD"),
                f.get("corridor", "unknown"),
                "new to this customer" if f.get("receiver_new") else "used before",
                f.get("customer_tenure_days", "unknown"),
                int(f.get("hour_local", 12)),
                f.get("declared_country", "not stated"),
                case.subject,
            )
        )

    # -- reading answers -----------------------------------------------------

    def interpret(self, tool: str, result: ApiResult, facts: Dict[str, Any]) -> Dict[str, Any]:
        derived = read_signal(tool, result)

        # A declared country that does not match where the line actually is
        # deserves attention. Roaming by itself does not.
        if tool == "check_roaming":
            declared = (facts.get("declared_country") or "").upper()
            actual = (derived.get("roaming_country") or "").upper()
            if declared and actual:
                derived["country_matches_declaration"] = declared == actual
        return derived

    # -- the deterministic ladder -------------------------------------------

    def next_tool(
        self, case: Case, facts: Dict[str, Any], used: List[str]
    ) -> Optional[Tuple[str, Dict[str, Any], str]]:
        risk = self._free_signals(case, facts)

        if "number_verified" not in facts:
            return (
                "verify_number",
                {},
                "One unit to confirm the line on the phone. Cheapest possible "
                "start and it can end the case on its own.",
            )

        if not facts.get("number_verified"):
            return None  # nothing else can rescue this

        # Nothing odd and not much money: this is where the savings come from.
        if risk["oddities"] == 0 and not risk["big"]:
            return None

        if "sim_swapped_in_window" not in facts:
            return (
                "check_sim_swap",
                {"max_age_hours": SWAP_LOOKBACK_H},
                "Something about this transfer is unusual (%s). A SIM change is "
                "the single signal most likely to change the answer, so buy that "
                "one and look back ten days rather than guessing a window."
                % ", ".join(risk["reasons"]),
            )

        if facts.get("sim_swapped_in_window") and "sim_change_hours_ago" not in facts:
            return (
                "sim_swap_date",
                {},
                "The SIM did change inside the window. How many hours ago decides "
                "between a hold and a block, so the timestamp is worth the same "
                "three units again.",
            )

        if (
            not facts.get("sim_swapped_in_window")
            and risk["very_big"]
            and "device_swapped_in_window" not in facts
        ):
            return (
                "check_device_swap",
                {"max_age_hours": SWAP_LOOKBACK_H},
                "The SIM is unchanged but this is a large amount. A handset change "
                "is weaker evidence, worth buying only at this size.",
            )

        if (
            facts.get("declared_country")
            and "roaming" not in facts
            and (risk["oddities"] >= 2 or risk["very_big"])
        ):
            return (
                "check_roaming",
                {},
                "Check the country the customer declared against where the line "
                "actually is. This is a consistency check, not a fraud signal - "
                "roaming on its own means nothing here.",
            )

        # If a hold looks likely, find out how the customer can actually be
        # reached before recommending a step-up they will never receive.
        likely_friction = (
            facts.get("sim_swapped_in_window")
            or facts.get("device_swapped_in_window")
            or risk["oddities"] >= 2
        )
        if likely_friction and "reachability" not in facts:
            return (
                "check_reachability",
                {},
                "A step-up is about to be recommended. One unit tells us whether "
                "this line can take an in-app confirmation or only SMS, so support "
                "does not send a challenge into a dead phone.",
            )

        return None

    # -- the floor -----------------------------------------------------------

    def decide(self, case: Case, facts: Dict[str, Any]) -> Tuple[str, str, str, float]:
        risk = self._free_signals(case, facts)
        checks = sum(
            1
            for key in (
                "number_verified",
                "sim_swapped_in_window",
                "sim_change_hours_ago",
                "device_swapped_in_window",
                "roaming",
                "reachability",
            )
            if key in facts
        )
        confidence = min(0.55 + 0.08 * checks, 0.97)

        if "number_verified" not in facts:
            # The agent got no network evidence at all, which in practice means
            # consent is not in place. Saying so beats inventing a verdict.
            return (
                "review",
                "Send this transfer down the bank's existing manual path",
                "No network evidence was available for this line, so Amana has "
                "nothing to add to this decision and does not pretend otherwise.",
                0.35,
            )

        if not facts.get("number_verified"):
            return (
                "block",
                "Refuse the transfer and send the customer through re-verification",
                "The network could not confirm that the number on the account is "
                "the number on this phone. Nothing else needs checking.",
                0.96,
            )

        hours = facts.get("sim_change_hours_ago")
        if hours is not None:
            when = self._describe_gap(hours)
            if hours <= FRESH_SWAP_H:
                return (
                    "block",
                    "Block this transfer and call the customer on a channel that is not this phone",
                    "The SIM behind this line changed %s. A change that close to a "
                    "payment is the pattern of an account takeover, not an upgrade." % when,
                    0.95,
                )
            if hours <= NEAR_SWAP_H:
                if risk["very_big"]:
                    return (
                        "block",
                        "Block this transfer and verify the customer out of band",
                        "The SIM changed %s and this is the customer's largest "
                        "transfer. Both together are enough to stop it." % when,
                        0.92,
                    )
                return (
                    "hold",
                    "Hold for a step-up confirmation before releasing",
                    "The SIM changed %s. That is recent enough to confirm the "
                    "customer before the money moves, and not so recent that the "
                    "transfer should be refused outright." % when,
                    0.88,
                )
            if hours <= SWAP_LOOKBACK_H and (risk["big"] or risk["new_receiver"]):
                return (
                    "hold",
                    "Hold for a step-up confirmation before releasing",
                    "The SIM changed %s, and this transfer is either large or the "
                    "first to this receiver. One confirmation is proportionate; a "
                    "block would not be." % when,
                    0.82,
                )
            return (
                "review",
                "Release and flag for the next analyst review",
                "The SIM changed %s, which is old enough to be an ordinary "
                "replacement. Worth recording, not worth stopping." % when,
                0.78,
            )

        if facts.get("sim_swapped_in_window"):
            return (
                "hold",
                "Hold for a step-up confirmation before releasing",
                "The network reports a SIM change inside the last ten days but "
                "would not give a timestamp, so the safe reading is the cautious one.",
                0.74,
            )

        if facts.get("device_swapped_in_window") and (risk["very_big"] or risk["new_receiver"]):
            return (
                "review",
                "Release and flag for the next analyst review",
                "The SIM is unchanged, so this is very likely the same person on a "
                "new handset. The amount is large enough to be worth a second pair "
                "of eyes afterwards, not a hold now.",
                0.8,
            )

        if facts.get("country_matches_declaration") is False:
            return (
                "review",
                "Release and flag the country mismatch for review",
                "The line is on a visited network in %s while the customer declared "
                "%s. Living abroad is normal for these customers, so this is a "
                "record-keeping mismatch rather than fraud."
                % (facts.get("roaming_country"), facts.get("declared_country")),
                0.72,
            )

        if risk["oddities"] >= 2:
            return (
                "review",
                "Release and flag for the next analyst review",
                "Nothing in the network contradicts this customer: the line is "
                "verified and the SIM is unchanged. Two things about the transfer "
                "itself are unusual (%s), which is worth a look afterwards."
                % ", ".join(risk["reasons"]),
                confidence,
            )

        if risk["big"] and risk["oddities"] >= 1:
            return (
                "review",
                "Release and flag for the next analyst review",
                "A large transfer with one unusual feature (%s) and a clean network "
                "picture. Releasing it is right; recording it is cheap."
                % ", ".join(risk["reasons"]),
                confidence,
            )

        return (
            "clear",
            "Release the transfer now",
            "The line is verified and nothing about this transfer is unusual for "
            "this customer. No further network checks could have changed that, so "
            "none were bought.",
            confidence,
        )

    # -- helpers -------------------------------------------------------------

    @staticmethod
    def _free_signals(case: Case, facts: Dict[str, Any]) -> Dict[str, Any]:
        """What we know before spending anything.

        Deliberately separate from the network signals: these come out of the
        bank's own records and cost nothing, so they decide whether a paid
        check is worth making at all.
        """
        merged = {**case.facts, **facts}
        amount = float(merged.get("amount") or 0)
        reasons: List[str] = []

        new_receiver = bool(merged.get("receiver_new"))
        if new_receiver:
            reasons.append("first transfer to this receiver")

        tenure = merged.get("customer_tenure_days")
        thin = tenure is not None and float(tenure) < THIN_TENURE_DAYS
        if thin:
            reasons.append("customer only %s days old" % int(float(tenure)))

        hour = merged.get("hour_local")
        odd_hour = hour is not None and int(hour) < 5
        if odd_hour:
            reasons.append("sent at %02d:00 local" % int(hour))

        very_big = amount >= VERY_BIG_USD
        big = amount >= BIG_USD
        if very_big:
            reasons.append("unusually large amount")

        return {
            "amount": amount,
            "big": big,
            "very_big": very_big,
            "new_receiver": new_receiver,
            "thin_tenure": thin,
            "odd_hour": odd_hour,
            "oddities": sum([new_receiver, thin, odd_hour, very_big]),
            "reasons": reasons or ["nothing unusual"],
        }

    @staticmethod
    def _describe_gap(hours: float) -> str:
        if hours < 1:
            return "less than an hour ago"
        if hours < 36:
            return "%d hours before this transfer" % round(hours)
        return "%d days before this transfer" % round(hours / 24)
