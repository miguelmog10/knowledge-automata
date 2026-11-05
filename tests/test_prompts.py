import pytest

from knowledge_automata import pipeline
from knowledge_automata.agents.governor import Governor
from knowledge_automata.core import prompts

REPO_PROMPTS = prompts.prompts_root()

# The instruction Cohere's structured outputs page asks of a json_object request (handoff 008).
JSON_INSTRUCTION = "Reply with one JSON object that matches the response schema, and nothing else."
SAMPLE_ERRORS = (
    "$.evidence[0]: quote not found in the artifact",
    "$.target_id: not one of the candidates shown",
)

# Every agent the pipeline builds, so a new Registrar is covered without a test change.
PIPELINE_AGENTS = [
    pipeline.governor(),
    *(factory() for factory in pipeline.REGISTRARS.values()),
    pipeline.decision_comparator(),
]


def test_registrar_and_comparator_prompts_are_listed():
    assert set(prompts.list_prompts()) >= {
        "core/registrar-retry.v1",
        "project-management/decision-registrar.v1",
        "core/comparator-retry.v1",
        "project-management/decision-comparator.v1",
    }


def test_governor_prompts_and_definitions_are_listed():
    assert set(prompts.list_prompts()) >= {
        "core/governor.v1",
        "core/governor-retry.v1",
        "project-management/decision-registrar.v2",
        "project-management/definitions/decision-log.v1",
        "project-management/definitions/risk-register.v1",
    }


def test_prompts_that_ask_for_json_are_listed():
    assert set(prompts.list_prompts()) >= {
        "core/governor.v2",
        "core/governor-retry.v2",
        "project-management/decision-registrar.v3",
        "core/registrar-retry.v2",
        "project-management/decision-comparator.v2",
        "core/comparator-retry.v2",
    }


@pytest.mark.parametrize(
    ("name", "version"),
    [
        ("project-management/decision-registrar.v1", "decision-registrar.v1"),
        ("core/registrar-retry.v1", "registrar-retry.v1"),
        ("project-management/decision-comparator.v1", "decision-comparator.v1"),
        ("core/comparator-retry.v1", "comparator-retry.v1"),
        ("core/governor.v1", "governor.v1"),
        ("core/governor-retry.v1", "governor-retry.v1"),
        ("project-management/decision-registrar.v2", "decision-registrar.v2"),
        ("core/governor.v2", "governor.v2"),
        ("core/governor-retry.v2", "governor-retry.v2"),
        ("project-management/decision-registrar.v3", "decision-registrar.v3"),
        ("core/registrar-retry.v2", "registrar-retry.v2"),
        ("project-management/decision-comparator.v2", "decision-comparator.v2"),
        ("core/comparator-retry.v2", "comparator-retry.v2"),
        ("project-management/definitions/decision-log.v1", "decision-log.v1"),
        ("project-management/definitions/risk-register.v1", "risk-register.v1"),
    ],
)
def test_prompt_loads_with_its_version(name, version):
    prompt = prompts.load_prompt(name)
    assert prompt.version == version
    expected = (REPO_PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    assert prompt.text == expected
    assert "\r" not in prompt.text


@pytest.mark.parametrize(
    "name",
    [
        "core/registrar-retry.v1",
        "core/comparator-retry.v1",
        "core/governor-retry.v1",
        "core/registrar-retry.v2",
        "core/comparator-retry.v2",
        "core/governor-retry.v2",
    ],
)
def test_retry_prompt_has_the_errors_placeholder(name):
    assert "{errors}" in prompts.load_prompt(name).text


@pytest.mark.parametrize("name", ["core/governor.v1", "core/governor.v2"])
def test_governor_prompt_has_the_registers_placeholder(name):
    assert prompts.load_prompt(name).text.count("{registers}") == 1


def last_line(text):
    return text.rstrip().splitlines()[-1]


def first_attempt_prompt(agent):
    """The main prompt as the agent sends it: the Governor's with its registers filled in."""
    if isinstance(agent, Governor):
        return prompts.Prompt(agent.prompt.version, agent.system_text())
    return agent.prompt


@pytest.mark.parametrize("agent", PIPELINE_AGENTS, ids=[a.agent for a in PIPELINE_AGENTS])
def test_every_pipeline_prompt_ends_with_the_json_instruction(agent):
    assert last_line(agent.prompt.text) == JSON_INSTRUCTION
    assert last_line(agent.retry_prompt.text) == JSON_INSTRUCTION
    assert first_attempt_prompt(agent).text.rstrip().endswith(JSON_INSTRUCTION)


@pytest.mark.parametrize("agent", PIPELINE_AGENTS, ids=[a.agent for a in PIPELINE_AGENTS])
def test_every_retry_message_ends_with_the_json_instruction(agent):
    system = prompts.retry_system_text(
        first_attempt_prompt(agent), agent.retry_prompt, SAMPLE_ERRORS
    )
    assert system.rstrip().endswith(JSON_INSTRUCTION)
    last = system.rindex(JSON_INSTRUCTION)
    for error in SAMPLE_ERRORS:
        assert -1 < system.find(error) < last


def test_the_frozen_registrar_v1_prompt_does_not_ask_for_json():
    # The public reproduction (cohere-feedback) uses this file as it is: never "fix" it.
    text = prompts.load_prompt("project-management/decision-registrar.v1").text
    assert JSON_INSTRUCTION not in text


def test_missing_prompt_names_the_prompt():
    with pytest.raises(FileNotFoundError, match="core/missing.v1"):
        prompts.load_prompt("core/missing.v1")


@pytest.mark.parametrize(
    "bad_name",
    ["../pyproject", "core/../../pyproject", "/etc/passwd", "", "core\\registrar-retry.v1"],
)
def test_load_prompt_rejects_paths_outside_prompts(bad_name):
    with pytest.raises(ValueError):
        prompts.load_prompt(bad_name)
