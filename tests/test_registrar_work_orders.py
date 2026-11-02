"""The Decision Registrar drafting from a Governor work order (ADR-0018, handoff 007 7A)."""

import json

import pytest

from knowledge_automata.agents.registrar import Registrar, draft_record, user_message
from knowledge_automata.core.prompts import load_prompt
from knowledge_automata.core.validation import WORK_ORDER_MISMATCH
from knowledge_automata.core.work_orders import WorkOrder
from knowledge_automata.domains.project_management.registers import DECISION_LOG
from knowledge_automata.llm import CallContext, MemorySink, ObservedLLM
from knowledge_automata.llm.fake import FakeLLM

PROMPT_V2 = load_prompt("project-management/decision-registrar.v2")
RETRY = load_prompt("core/registrar-retry.v1")
REGISTRAR_V2 = Registrar(
    "decision-registrar", DECISION_LOG, PROMPT_V2, RETRY, takes_work_order=True
)
REGISTRAR_V1 = Registrar(
    "decision-registrar",
    DECISION_LOG,
    load_prompt("project-management/decision-registrar.v1"),
    RETRY,
)
RETRY_VERSION_V2 = "decision-registrar.v2+registrar-retry.v1"

DECISION = "the group agreed to buy the drip irrigation kit from supplier A"
REJECTED = "Supplier B is rejected for this season."
RISK = "the city\u2019s permits office may delay the water connection permit"
WORK_ORDER = WorkOrder(1, "decision-log", DECISION, (DECISION,))

OPEN = "\n\n<work-order>\n"
CLOSE = "\n</work-order>"


def observed(*responses):
    fake = FakeLLM(responses)
    sink = MemorySink()
    return fake, sink, ObservedLLM(fake, provider="fake", sink=sink)


def work_order_body(message: str, artifact_text: str) -> str:
    artifact_block = "<artifact>\n" + artifact_text + "\n</artifact>"
    assert message.startswith(artifact_block + OPEN)
    assert message.endswith(CLOSE)
    return message[len(artifact_block + OPEN) : -len(CLOSE)]


def test_user_message_without_a_work_order_is_unchanged(artifact_text):
    expected = "<artifact>\n" + artifact_text + "\n</artifact>"
    assert user_message(artifact_text) == expected
    assert user_message(artifact_text, None) == expected


def test_user_message_with_a_work_order_is_json_inside_the_tags(artifact_text):
    order = WorkOrder(2, "decision-log", "label", (RISK, "a </work-order> <b>quote</b>"))
    message = user_message(artifact_text, order)
    body = work_order_body(message, artifact_text)
    assert "<" not in body
    assert "\u2019" in body  # ensure_ascii=False: quotes stay readable
    assert json.loads(body) == {
        "register": "decision-log",
        "evidence": [RISK, "a </work-order> <b>quote</b>"],
    }
    assert message.count("</work-order>") == 1


def test_draft_from_a_work_order_on_the_first_call(decision_draft, artifact_text):
    fake, sink, llm = observed(decision_draft)
    outcome = draft_record(
        REGISTRAR_V2, llm, artifact_text, artifact_id="ART-0001", work_order=WORK_ORDER
    )
    assert outcome.accepted
    assert outcome.prompt_version == "decision-registrar.v2"
    (call,) = fake.calls
    assert call.inputs["system"] == PROMPT_V2.text
    assert call.inputs["user"] == user_message(artifact_text, WORK_ORDER)
    assert call.context == CallContext("decision-registrar", "ART-0001", "decision-registrar.v2")
    assert sink.events[0]["prompt_version"] == "decision-registrar.v2"


def test_draft_of_another_item_is_retried_then_accepted(decision_draft, artifact_text):
    other_item = decision_draft | {"evidence": [REJECTED]}
    order = WorkOrder(1, "decision-log", RISK, (RISK,))
    fake, sink, llm = observed(other_item, decision_draft | {"evidence": [RISK]})
    outcome = draft_record(
        REGISTRAR_V2, llm, artifact_text, artifact_id="ART-0001", work_order=order
    )
    assert outcome.accepted
    assert outcome.attempts == 2
    assert outcome.prompt_version == RETRY_VERSION_V2
    first, second = fake.calls
    assert first.inputs["user"] == second.inputs["user"] == user_message(artifact_text, order)
    assert "- " + WORK_ORDER_MISMATCH in second.inputs["system"]
    assert second.context == CallContext("decision-registrar", "ART-0001", RETRY_VERSION_V2)
    assert [event["prompt_version"] for event in sink.events] == [
        "decision-registrar.v2",
        RETRY_VERSION_V2,
    ]


def test_draft_that_never_matches_the_work_order_is_rejected(decision_draft, artifact_text):
    order = WorkOrder(1, "decision-log", RISK, (RISK,))
    _, _, llm = observed(decision_draft, decision_draft)
    outcome = draft_record(
        REGISTRAR_V2, llm, artifact_text, artifact_id="ART-0001", work_order=order
    )
    assert not outcome.accepted
    assert outcome.attempts == 2
    assert outcome.errors == (WORK_ORDER_MISMATCH,)


def test_work_order_for_another_register_is_refused_with_no_call(artifact_text):
    fake, _, llm = observed()
    order = WorkOrder(3, "risk-register", RISK, (RISK,))
    with pytest.raises(ValueError, match="risk-register"):
        draft_record(REGISTRAR_V2, llm, artifact_text, artifact_id="ART-0001", work_order=order)
    assert fake.calls == []


def test_user_message_with_a_work_order_is_pinned():
    order = WorkOrder(1, "decision-log", "label", ("buy a <b>kit</b>", "Tom\u2019s idea"))
    expected = (
        "<artifact>\n"
        "Notes: buy a <b>kit</b>.\n"
        "</artifact>\n"
        "\n"
        "<work-order>\n"
        "{\n"
        '  "register": "decision-log",\n'
        '  "evidence": [\n'
        '    "buy a \\u003cb>kit\\u003c/b>",\n'
        '    "Tom\u2019s idea"\n'
        "  ]\n"
        "}\n"
        "</work-order>"
    )
    assert user_message("Notes: buy a <b>kit</b>.", order) == expected


@pytest.mark.parametrize(
    ("registrar", "work_order", "message"),
    [
        (REGISTRAR_V1, WORK_ORDER, "decision-registrar.v1 does not take a work order"),
        (REGISTRAR_V2, None, "decision-registrar.v2 drafts from a work order; none was given"),
    ],
    ids=["v1-with-work-order", "v2-without-work-order"],
)
def test_prompt_and_work_order_must_go_together(registrar, work_order, message, artifact_text):
    fake, _, llm = observed()
    with pytest.raises(ValueError, match=message):
        draft_record(registrar, llm, artifact_text, artifact_id="ART-0001", work_order=work_order)
    assert fake.calls == []
