import pytest
from jsonschema import Draft202012Validator

from knowledge_automata.core.schemas import GOVERNOR_REPLY_SCHEMA, governor_schema, load_schema
from knowledge_automata.core.validation import validate_work_orders
from knowledge_automata.core.work_orders import WorkOrder, build_work_orders, placeholder_label
from knowledge_automata.domains.project_management.registers import REGISTERS
from knowledge_automata.llm.provider_schema import to_cohere_schema

DECISION = "the group agreed to buy the drip irrigation kit from supplier A"
REJECTED = "Supplier B is rejected for this season."
RISK = "the city\u2019s permits office may delay the water connection permit"
OPPORTUNITY = "the local school might lend volunteers for the build day"


def item(register, *evidence):
    return {"register": register, "evidence": list(evidence)}


def assert_fails(result, *fragments):
    assert not result.ok
    for fragment in fragments:
        assert any(fragment in error for error in result.errors), (fragment, result.errors)


# The schema


def test_governor_schema_sets_the_register_names():
    schema = governor_schema(REGISTERS)
    register = schema["properties"]["items"]["items"]["properties"]["register"]
    assert register["type"] == "string"
    assert register["enum"] == ["decision-log", "risk-register"]
    Draft202012Validator.check_schema(schema)


def test_governor_schema_is_accepted_by_the_cohere_reduction():
    reduced = to_cohere_schema(governor_schema(REGISTERS))
    item_schema = reduced["properties"]["items"]["items"]
    assert item_schema["properties"]["register"]["enum"] == ["decision-log", "risk-register"]
    assert "maxItems" not in reduced["properties"]["items"]
    assert "minItems" not in item_schema["properties"]["evidence"]


def test_governor_schema_returns_an_independent_copy():
    governor_schema(REGISTERS)["properties"]["items"]["items"]["required"].append("tampered")
    assert "enum" not in str(load_schema(GOVERNOR_REPLY_SCHEMA))
    assert "tampered" not in str(governor_schema(REGISTERS))


# validate_work_orders


def test_valid_reply_passes(artifact_text):
    reply = {
        "items": [
            item("decision-log", DECISION, REJECTED),
            item("risk-register", RISK),
            item("risk-register", OPPORTUNITY),
        ]
    }
    result = validate_work_orders(reply, REGISTERS, artifact_text)
    assert result.ok, result.errors


def test_empty_list_is_accepted(artifact_text):
    assert validate_work_orders({"items": []}, REGISTERS, artifact_text).ok


def test_the_count_is_not_a_validation_error():
    artifact = "\n".join(f"Decision {n}: the group chose option number {n}." for n in range(1, 13))
    reply = {
        "items": [
            item("decision-log", f"Decision {n}: the group chose option number {n}.")
            for n in range(1, 13)
        ]
    }
    result = validate_work_orders(reply, REGISTERS, artifact)
    assert result.ok, result.errors


def test_too_many_items_is_one_short_error():
    lines = [f"Decision {n}: the group chose option number {n}." for n in range(1, 102)]
    reply = {"items": [item("decision-log", line) for line in lines]}
    result = validate_work_orders(reply, REGISTERS, "\n".join(lines))
    assert result.errors == ("$.items: 101 items, at most 100",)


def test_too_many_quotes_in_an_item_is_one_short_error(artifact_text):
    reply = {
        "items": [item("decision-log", DECISION, REJECTED, DECISION, REJECTED, RISK, DECISION)]
    }
    errors = validate_work_orders(reply, REGISTERS, artifact_text).errors
    assert errors[0] == "$.items[0].evidence: 6 items, at most 5"


def test_quote_not_found_fails(artifact_text):
    reply = {"items": [item("decision-log", DECISION), item("risk-register", "the sky may fall")]}
    assert_fails(
        validate_work_orders(reply, REGISTERS, artifact_text),
        "$.items[1].evidence[0]: not found in the artifact: 'the sky may fall'",
    )


def test_quote_too_short_fails(artifact_text):
    reply = {"items": [item("decision-log", DECISION, "supplier A")]}
    assert_fails(
        validate_work_orders(reply, REGISTERS, artifact_text),
        "$.items[0].evidence[1]: too short",
    )


def test_unknown_register_fails(artifact_text):
    reply = {"items": [item("action-items", DECISION)]}
    assert_fails(validate_work_orders(reply, REGISTERS, artifact_text), "$.items[0].register:")


@pytest.mark.parametrize(
    "reply",
    [None, [], {"items": "none"}, {"items": [{"register": "decision-log"}]}, {"extra": 1}],
    ids=["null", "list", "items-not-a-list", "no-evidence", "no-items"],
)
def test_malformed_reply_fails_without_raising(reply, artifact_text):
    assert not validate_work_orders(reply, REGISTERS, artifact_text).ok


def test_same_quote_in_two_items_of_one_register_fails(artifact_text):
    reply = {"items": [item("decision-log", DECISION), item("decision-log", REJECTED, DECISION)]}
    result = validate_work_orders(reply, REGISTERS, artifact_text)
    assert result.errors == (
        "$.items[1].evidence[1]: also quoted by item 0 in the same register; "
        "return one item for one thing",
    )


def test_quote_contained_in_another_items_quote_fails():
    artifact = (
        "Aisha explained the reasons. The QR code labels for every bench stay the plan.\n\n"
        "## Decisions\n\n- QR code labels for every bench stay the plan.\n"
    )
    section = "The QR code labels for every bench stay the plan."
    summary = "QR code labels for every bench stay the plan."
    reply = {"items": [item("decision-log", summary), item("decision-log", section)]}
    assert_fails(
        validate_work_orders(reply, REGISTERS, artifact),
        "$.items[1].evidence[0]: also quoted by item 0 in the same register",
    )
    reply = {"items": [item("decision-log", section), item("decision-log", summary)]}
    assert_fails(
        validate_work_orders(reply, REGISTERS, artifact),
        "$.items[1].evidence[0]: also quoted by item 0 in the same register",
    )


def test_shared_quote_is_compared_after_normalization(artifact_text):
    reply = {
        "items": [
            item("risk-register", RISK),
            item("risk-register", "THE CITY'S PERMITS   OFFICE may delay"),
        ]
    }
    assert_fails(
        validate_work_orders(reply, REGISTERS, artifact_text),
        "$.items[1].evidence[0]: also quoted by item 0",
    )


def test_shared_quote_in_different_registers_passes(artifact_text):
    reply = {"items": [item("decision-log", DECISION), item("risk-register", DECISION)]}
    assert validate_work_orders(reply, REGISTERS, artifact_text).ok


def test_overlapping_quotes_within_one_item_pass(artifact_text):
    reply = {"items": [item("decision-log", DECISION, "buy the drip irrigation kit")]}
    assert validate_work_orders(reply, REGISTERS, artifact_text).ok


def test_failed_quotes_are_not_compared(artifact_text):
    reply = {"items": [item("decision-log", DECISION), item("decision-log", "...", REJECTED)]}
    result = validate_work_orders(reply, REGISTERS, artifact_text)
    assert len(result.errors) == 1
    assert result.errors[0].startswith("$.items[1].evidence[0]: too short")


# Building the work orders

SORT_ARTIFACT = (
    "# Tech sync\n\n"
    "Marc agreed to launch with English and French for those two screens only.\n\n"
    "The app now keeps the most recent count and shows both counts.\n\n"
    "## Decisions\n\n"
    "- Launch the count screen and the status picker in English and French.\n"
)


def test_work_orders_are_sorted_by_their_earliest_quote():
    items = [
        item("decision-log", "The app now keeps the most recent count"),
        # The first-listed quote is from the summary at the end; the second comes first.
        item(
            "decision-log",
            "Launch the count screen and the status picker in English and French.",
            "Marc agreed to launch with English and French",
        ),
    ]
    orders = build_work_orders(items, SORT_ARTIFACT)
    assert orders == (
        WorkOrder(
            number=1,
            register="decision-log",
            label="Launch the count screen and the status picker in English and...",
            evidence=(
                "Launch the count screen and the status picker in English and French.",
                "Marc agreed to launch with English and French",
            ),
        ),
        WorkOrder(
            number=2,
            register="decision-log",
            label="The app now keeps the most recent count",
            evidence=("The app now keeps the most recent count",),
        ),
    )


def test_ties_keep_the_models_order():
    quote = "The app now keeps the most recent count"
    items = [item("risk-register", quote), item("decision-log", quote)]
    orders = build_work_orders(items, SORT_ARTIFACT)
    assert [(order.number, order.register) for order in orders] == [
        (1, "risk-register"),
        (2, "decision-log"),
    ]


def test_no_items_give_no_work_orders():
    assert build_work_orders([], SORT_ARTIFACT) == ()


def test_unchecked_quote_raises():
    with pytest.raises(ValueError):
        build_work_orders([item("decision-log", "not in the artifact at all")], SORT_ARTIFACT)


def test_placeholder_label_keeps_a_short_quote():
    assert placeholder_label("Decision: QR labels.") == "Decision: QR labels."


def test_placeholder_label_cuts_a_long_quote_at_a_word_boundary():
    quote = (
        "Julie confirmed that the status paths per crop type stay as the board decided in April."
    )
    assert placeholder_label(quote) == (
        "Julie confirmed that the status paths per crop type stay as..."
    )


def test_placeholder_label_collapses_line_breaks():
    quote = "Julie confirmed that the\nstatus paths per crop type stay\n  as the board decided."
    assert placeholder_label(quote) == (
        "Julie confirmed that the status paths per crop type stay as..."
    )
    assert placeholder_label("  two\nlines \t here ") == "two lines here"


def test_placeholder_label_keeps_a_word_that_ends_at_the_limit():
    quote = "a" * 55 + " bcde fgh"
    assert placeholder_label(quote) == "a" * 55 + " bcde..."


def test_placeholder_label_cuts_a_single_long_word():
    assert placeholder_label("x" * 80) == "x" * 60 + "..."


@pytest.mark.parametrize(
    "quote",
    [
        '"Decision: QR labels."',
        "'Decision: QR labels.'",
        "\u201cDecision: QR labels.\u201d",
        "\u2018 \u201cDecision: QR labels.\u201d\u2019 ",
    ],
    ids=["straight-double", "straight-single", "typographic", "nested"],
)
def test_placeholder_label_strips_surrounding_quote_marks(quote):
    assert placeholder_label(quote) == "Decision: QR labels."


def test_placeholder_label_keeps_inner_quote_marks():
    assert placeholder_label("the city\u2019s permits office") == "the city\u2019s permits office"
    assert placeholder_label('Tom said "yes" to it') == 'Tom said "yes" to it'
