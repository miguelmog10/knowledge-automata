"""Architecture checks: the provider SDK stays inside the adapter (ADR-0003, ADR-0012)."""

import ast
from pathlib import Path

import cohere
import httpx
import pytest

import knowledge_automata
from knowledge_automata.llm import (
    ChatModel,
    EmbeddingModel,
    LLMSettings,
    MemorySink,
    ObservedLLM,
    RerankModel,
)
from knowledge_automata.llm.cohere_adapter import CohereAdapter
from knowledge_automata.llm.fake import FakeLLM

PACKAGE_ROOT = Path(knowledge_automata.__file__).parent
ADAPTER = Path("llm", "cohere_adapter.py")
PROVIDER_MODULES = {"cohere", "httpx"}


def imported_top_level_modules(path: Path) -> set[str]:
    modules = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_only_the_cohere_adapter_imports_the_provider_sdk():
    offenders = {
        str(path.relative_to(PACKAGE_ROOT)): sorted(imports & PROVIDER_MODULES)
        for path in PACKAGE_ROOT.rglob("*.py")
        if path.relative_to(PACKAGE_ROOT) != ADAPTER
        and (imports := imported_top_level_modules(path)) & PROVIDER_MODULES
    }
    assert offenders == {}


def test_the_adapter_is_where_the_sdk_is_imported():
    assert {"cohere", "httpx"} <= imported_top_level_modules(PACKAGE_ROOT / ADAPTER)


def adapters():
    client = cohere.ClientV2(
        api_key="test", httpx_client=httpx.Client(transport=httpx.MockTransport(lambda r: None))
    )
    cohere_adapter = CohereAdapter(LLMSettings(api_key="test"), client=client)
    return [
        FakeLLM(),
        cohere_adapter,
        ObservedLLM(cohere_adapter, provider="cohere", sink=MemorySink()),
    ]


@pytest.mark.parametrize("protocol", [ChatModel, EmbeddingModel, RerankModel])
def test_adapters_implement_every_interface(protocol):
    for adapter in adapters():
        assert isinstance(adapter, protocol)
