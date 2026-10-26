import pytest

from knowledge_automata.core import prompts

REPO_PROMPTS = prompts.prompts_root()


def test_both_registrar_prompts_are_listed():
    assert set(prompts.list_prompts()) >= {
        "core/registrar-retry.v1",
        "project-management/decision-registrar.v1",
    }


@pytest.mark.parametrize(
    ("name", "version"),
    [
        ("project-management/decision-registrar.v1", "decision-registrar.v1"),
        ("core/registrar-retry.v1", "registrar-retry.v1"),
    ],
)
def test_prompt_loads_with_its_version(name, version):
    prompt = prompts.load_prompt(name)
    assert prompt.version == version
    expected = (REPO_PROMPTS / f"{name}.md").read_text(encoding="utf-8")
    assert prompt.text == expected
    assert "\r" not in prompt.text


def test_retry_prompt_has_the_errors_placeholder():
    assert "{errors}" in prompts.load_prompt("core/registrar-retry.v1").text


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
