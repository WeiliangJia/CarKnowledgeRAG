import pytest

from car_knowledge_rag import index_9x
from car_knowledge_rag.openai_models import EMBEDDING_MODEL, CallMetrics


def test_resumed_index_embeds_only_missing_points(monkeypatch):
    chunks = [
        {"id": "first", "text": "六座版配置", "version": {"group": "六座"}},
        {"id": "second", "text": "五座版配置", "version": {"group": "五座"}},
    ]
    points = {"first": {"id": "first", "payload": chunks[0]}}
    inputs = []
    monkeypatch.setattr(index_9x, "ensure_collection", lambda *args: None)

    def api(method, path, body):
        if path.endswith("/scroll"):
            return {"points": list(points.values()), "next_page_offset": None}
        if path.endswith("/count"):
            return {"count": len(points)}
        assert method == "PUT" and path.endswith("/points?wait=true")
        assert body["update_mode"] == "insert_only"
        for point in body["points"]:
            points[point["id"]] = {"id": point["id"], "payload": point["payload"]}
        return {"status": "completed"}

    def embed_batch(batch):
        inputs.extend(batch)
        return [[0.5]] * len(batch), CallMetrics(EMBEDDING_MODEL, 6, 0, 200, "req_test")

    first = index_9x.index(api, "test", chunks, {}, embed_batch)
    second = index_9x.index(api, "test", chunks, {}, embed_batch)
    assert inputs == ["五座版配置"]
    assert first["points_before"] == 1 and first["points_after"] == 2
    assert first["embedding_requests"] == 1
    assert second["points_before"] == second["points_after"] == 2
    assert second["embedding_requests"] == second["input_tokens"] == 0
    assert points["second"]["payload"]["version"]["group"] == "五座"


def test_mismatched_existing_payload_is_rejected():
    def api(method, path, body):
        return {
            "points": [{"id": "first", "payload": {"text": "changed"}}],
            "next_page_offset": None,
        }

    with pytest.raises(index_9x.QdrantError, match="Unexpected point or payload"):
        index_9x.stored_ids(api, "/collections/test", {"first": {"text": "original"}})
