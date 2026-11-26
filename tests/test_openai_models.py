import json

import pytest

from car_knowledge_rag import openai_models


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_EMBED_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_CHUNK_API_KEY", raising=False)
    (tmp_path / ".env.openai").write_text(
        'OPENAI_EMBED_API_KEY="sk-test-embed"\nOPENAI_CHUNK_API_KEY=sk-test-chunk\n',
        encoding="utf-8-sig",
    )
    monkeypatch.setenv("OPENAI_EMBED_API_KEY", "sk-test-override")
    return openai_models.OpenAISettings()


def test_embed_uses_correct_key_and_preserves_batch_order(settings, monkeypatch):
    size = openai_models.EMBEDDING_DIMENSIONS

    def post(path, secret, payload):
        assert path == "/v1/embeddings" and secret == "sk-test-override"
        assert payload["model"] == "text-embedding-3-small"
        assert payload["input"] == ["文档", "问题"]
        assert payload["dimensions"] == size
        return (
            {
                "data": [
                    {"index": 1, "embedding": [0.2] * size},
                    {"index": 0, "embedding": [0.1] * size},
                ],
                "model": payload["model"],
                "usage": {"prompt_tokens": 12},
            },
            10.24,
            "req_embed",
        )

    monkeypatch.setattr(openai_models, "post", post)
    vectors, call = openai_models.embed(["文档", "问题"], settings=settings)
    assert [vector[0] for vector in vectors] == [0.1, 0.2]
    assert call.input_tokens == 12 and call.output_tokens == 0
    assert call.elapsed_ms == 10.2 and call.request_id == "req_embed"


@pytest.mark.parametrize("start", [3, 2, 4])
def test_chunking_uses_original_lines_and_rejects_overlap_or_gap(
    settings, monkeypatch, start
):
    lines = ["座椅按摩：22 个点位", "  仅适用前排及二排两侧。", "全景天窗"]

    def post(path, secret, payload):
        assert path == "/v1/responses" and secret == "sk-test-chunk"
        assert payload["model"] == "gpt-6-luna" and payload["store"] is False
        assert payload["text"]["format"]["strict"] is True
        assert [item["text"] for item in json.loads(payload["input"])["lines"]] == lines
        output = json.dumps(
            {
                "chunks": [
                    {"start_line": 1, "end_line": 2},
                    {"start_line": start, "end_line": 3},
                ]
            }
        )
        return (
            {
                "status": "completed",
                "model": payload["model"],
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": output}],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 8},
            },
            15,
            "req_chunk",
        )

    monkeypatch.setattr(openai_models, "post", post)
    if start != 3:
        with pytest.raises(openai_models.OpenAIError, match="Invalid chunk boundaries"):
            openai_models.chunk_lines(lines, settings=settings)
        return
    chunks, call = openai_models.chunk_lines(lines, settings=settings)
    assert [(c.start_line, c.end_line, c.text) for c in chunks] == [
        (1, 2, "\n".join(lines[:2])),
        (3, 3, lines[2]),
    ]
    assert call.output_tokens == 8 and call.request_id == "req_chunk"


def test_http_error_does_not_echo_the_provider_error_body(monkeypatch):
    class Connection:
        def __init__(self, host, timeout):
            assert host == "api.openai.com" and timeout == 40

        def request(self, method, path, body, headers):
            assert method == "POST" and path == "/v1/embeddings"
            assert headers["Authorization"] == "Bearer sk-example"

        def getresponse(self):
            return self

        def getheader(self, name):
            assert name == "x-request-id"
            return "req_failure"

        status = 401

        def read(self):
            return (
                b'{"error":{"code":"invalid_api_key","message":"Rejected sk-example"}}'
            )

        def close(self):
            pass

    monkeypatch.setattr(openai_models, "HTTPSConnection", Connection)
    with pytest.raises(openai_models.OpenAIError) as error:
        openai_models.post("/v1/embeddings", "sk-example", {})
    assert (
        str(error.value) == "OpenAI HTTP 401 (invalid_api_key), request_id=req_failure"
    )
