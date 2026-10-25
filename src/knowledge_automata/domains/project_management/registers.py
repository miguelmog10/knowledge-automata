"""The decision log and the risk register (ADR-0007, ADR-0011)."""

from collections.abc import Mapping
from typing import Any

from knowledge_automata.core.registers import CLASSIFICATIONS, RegisterSpec

THREAT_ONLY_STRATEGIES = frozenset({"avoid", "transfer", "mitigate"})
OPPORTUNITY_ONLY_STRATEGIES = frozenset({"exploit", "share", "enhance"})


def check_response_strategy_fits_kind(content: Mapping[str, Any]) -> list[str]:
    """A risk's response strategy must fit its kind; escalate and accept fit both."""
    kind = content.get("kind")
    strategy = content.get("response_strategy")
    if kind == "threat" and strategy in OPPORTUNITY_ONLY_STRATEGIES:
        return [
            f"response_strategy {strategy!r} does not fit kind 'threat' "
            "(exploit, share and enhance are for opportunities only)"
        ]
    if kind == "opportunity" and strategy in THREAT_ONLY_STRATEGIES:
        return [
            f"response_strategy {strategy!r} does not fit kind 'opportunity' "
            "(avoid, transfer and mitigate are for threats only)"
        ]
    return []


DECISION_LOG = RegisterSpec(
    name="decision-log",
    id_prefix="DEC",
    content_schema="project-management/decision.v1.json",
    allowed_classifications=CLASSIFICATIONS,
)

RISK_REGISTER = RegisterSpec(
    name="risk-register",
    id_prefix="RSK",
    content_schema="project-management/risk.v1.json",
    # Risks are updated in place; supersession is not allowed in v0.1.
    allowed_classifications=CLASSIFICATIONS - {"supersession"},
    semantic_checks=(check_response_strategy_fits_kind,),
)

REGISTERS: tuple[RegisterSpec, ...] = (DECISION_LOG, RISK_REGISTER)
