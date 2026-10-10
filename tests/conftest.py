import json

import pytest
from langchain_core.messages import AIMessage

from havoc.datagen import generate
from havoc.retrieval import HashingEmbeddings, RunbookRetriever
from havoc.telemetry import TelemetryStore


@pytest.fixture(scope="session")
def data_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    generate(d, n=30, seed=42)
    return d


@pytest.fixture(scope="session")
def store(data_dir):
    return TelemetryStore(data_dir)


@pytest.fixture(scope="session")
def labels(data_dir):
    return json.loads((data_dir / "labels.json").read_text())


@pytest.fixture(scope="session")
def retriever(data_dir):
    return RunbookRetriever.build(data_dir, HashingEmbeddings())


class ScriptedLLM:
    """Stands in for ChatGroq: returns pre-written replies in order."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def bind_tools(self, tools):
        return self

    def invoke(self, messages):
        self.calls += 1
        r = self.replies.pop(0)
        return r if isinstance(r, AIMessage) else AIMessage(content=r)
