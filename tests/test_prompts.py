import pytest

from knowledge_automata.core import prompts

REPO_PROMPTS = prompts.prompts_root()


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
    "name", ["core/registrar-retry.v1", "core/comparator-retry.v1", "core/governor-retry.v1"]
)
def test_retry_prompt_has_the_errors_placeholder(name):
    assert "{errors}" in prompts.load_prompt(name).text


def test_governor_prompt_has_the_registers_placeholder():
    assert prompts.load_prompt("core/governor.v1").text.count("{registers}") == 1


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
