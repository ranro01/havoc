from havoc.retrieval import HashingEmbeddings, RunbookRetriever


def test_returns_distinct_documents(retriever):
    hits = retriever.search("connection pool timeout waiting for connection", k=3)
    assert len(hits) == 3 and len({h.doc_id for h in hits}) == 3


def test_finds_right_runbook_for_clear_symptoms(retriever):
    q = "HikariPool Connection is not available, request timed out; pool saturation"
    assert "db_conn_pool_exhausted" in [h.fault_id for h in retriever.search(q, k=3)]
    q = "No space left on device, failed to write WAL segment disk quota exceeded"
    assert "disk_full" in [h.fault_id for h in retriever.search(q, k=3)]


def test_save_and_load_roundtrip(retriever, tmp_path):
    retriever.save(tmp_path / "idx")
    loaded = RunbookRetriever.load(tmp_path / "idx", HashingEmbeddings())
    q = "OOMKilled exit code 137 CrashLoopBackOff"
    assert [h.doc_id for h in loaded.search(q)] == [h.doc_id for h in retriever.search(q)]
