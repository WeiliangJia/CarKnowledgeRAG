import json

import pytest

from car_knowledge_rag import answer_9x
from car_knowledge_rag.openai_models import (
    EMBEDDING_MODEL,
    CallMetrics,
    OpenAIError,
    OpenAISettings,
)

CONFIGURATION = {
    "id": "cell",
    "kind": "configuration",
    "source": "S1",
    "source_url": "https://example.invalid/config",
    "locator": {"row_index": 20, "column_index": 2},
    "version": {"group": "9X六座版", "label": "Ultra版"},
    "text": "六座 Ultra 纯电续航：288/380 km，适用条件待核验。",
}


def draft(text, evidence_id=1, quote="288/380 km"):
    return answer_9x.AnswerDraft.model_validate(
        {
            "status": "answered",
            "claims": [
                {
                    "text": text,
                    "citations": [{"evidence_id": evidence_id, "quote": quote}],
                }
            ],
        }
    )


def test_answer_uses_distinct_responses_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENAI_ANSWER_API_KEY", raising=False)
    (tmp_path / ".env.openai").write_text(
        "OPENAI_ANSWER_API_KEY=sk-test-answer\nOPENAI_CHUNK_API_KEY=sk-test-chunk\n",
        encoding="utf-8",
    )
    question = "六座 Ultra 的纯电续航是多少？"
    expected = draft("六座 Ultra 原值为 288/380 km，适用条件待核验。")

    def post(path, key, payload):
        assert path == "/v1/responses" and key == "sk-test-answer"
        assert payload["store"] is False and payload["text"]["format"]["strict"] is True
        assert json.loads(payload["input"]) == {
            "question": question,
            "context": None,
            "evidence": [
                {"id": 1, "kind": "configuration", "text": CONFIGURATION["text"]}
            ],
        }
        return (
            {
                "status": "completed",
                "model": answer_9x.ANSWER_MODEL,
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": expected.model_dump_json()}
                        ],
                    }
                ],
                "usage": {"input_tokens": 90, "output_tokens": 22},
            },
            30,
            "req_answer",
        )

    monkeypatch.setattr(answer_9x, "post", post)
    result, call = answer_9x.generate_answer(
        question, None, [CONFIGURATION], settings=OpenAISettings()
    )
    assert result == expected
    assert (call.input_tokens, call.output_tokens, call.request_id) == (
        90,
        22,
        "req_answer",
    )


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (draft("续航为 288/380 km", evidence_id=2), "outside the supplied evidence"),
        (draft("续航为 288/380 km", quote="288-380 km"), "quote does not match"),
        (draft("续航为 400 km"), "numbers missing"),
        (
            answer_9x.AnswerDraft(status="answered", claims=[]),
            "does not match its claims",
        ),
    ],
)
def test_answer_rejects_unsupported_citations_and_numbers(result, error):
    with pytest.raises(OpenAIError, match=error):
        answer_9x.checked_claims(result, [CONFIGURATION])


def test_question_preserves_ultra_filter_and_records_usage():
    embed_call = CallMetrics(EMBEDDING_MODEL, 14, 0, 21, "req_question")
    answer_call = CallMetrics(answer_9x.ANSWER_MODEL, 90, 22, 30, "req_answer")

    def search(method, path, body):
        assert (method, path) == ("POST", "/collections/fixture/points/query")
        assert body["limit"] == 10 and body["params"] == {"exact": True}
        assert body["filter"]["should"][1]["must"][2]["match"]["value"] == "9X六座版"
        return {"points": [{"id": "cell"}]}

    def embed(text):
        assert text == "上下文：极氪 9X 六座 Ultra\n问题：纯电续航是多少？"
        return [[0.1]], embed_call

    def generate(question, context, evidence):
        assert question == "纯电续航是多少？"
        assert context == "极氪 9X 六座 Ultra"
        assert evidence == [CONFIGURATION]
        return draft("六座 Ultra 为 288/380 km，适用条件待核验。"), answer_call

    result = answer_9x.answer_question(
        search,
        "fixture",
        [CONFIGURATION],
        "纯电续航是多少？",
        embed,
        generate,
        context="极氪 9X 六座 Ultra",
    )
    assert result["status"] == "answered" and "288/380 km" in result["answer"]
    citation = result["claims"][0]["citations"][0]
    assert citation["locator"] == CONFIGURATION["locator"]
    assert citation["source_url"] == CONFIGURATION["source_url"]
    assert citation["version"] == CONFIGURATION["version"]
    assert result["api_usage"]["question_embedding"]["input_tokens"] == 14
    assert result["api_usage"]["answer_generation"]["output_tokens"] == 22
    assert result["api_usage"]["chunking"] == {"requests": 0}
    assert result["api_usage"]["document_embedding"] == {"requests": 0}
    assert result["timing_ms"]["total"] >= result["timing_ms"]["qdrant_search"]


def test_no_evidence_skips_generation_and_does_not_filter_comparison():
    def search(_method, _path, body):
        assert "filter" not in body
        return {"points": []}

    def embed(_text):
        return [[0.1]], CallMetrics(EMBEDDING_MODEL, 14, 0, 21, "req_question")

    def generate(*_):
        pytest.fail("A question without evidence must not call the answer API")

    result = answer_9x.answer_question(
        search, "fixture", [], "六座 Ultra 和其他版本相比呢？", embed, generate
    )
    assert result["status"] == "insufficient_evidence" and not result["claims"]
    assert result["api_usage"]["answer_generation"] == {"requests": 0}


def test_configuration_symbols_include_the_same_snapshot_legend():
    cell = {**CONFIGURATION, "raw": "○", "text": "前排座椅按摩：○"}
    legend = {
        **CONFIGURATION,
        "id": "legend",
        "kind": "configuration_notice",
        "locator": {"notice_index": 1},
        "text": "“●”为标配，“○”为选装，“−”为无该配置。",
    }

    def generate(_question, _context, evidence):
        assert evidence == [cell, legend]
        return (
            draft("○ 表示选装。", evidence_id=2, quote="“○”为选装"),
            CallMetrics(answer_9x.ANSWER_MODEL, 90, 22, 30, "req_answer"),
        )

    result = answer_9x.answer_question(
        lambda *_: {"points": [{"id": "cell"}]},
        "fixture",
        [cell, legend],
        "座椅按摩的 ○ 是什么意思？",
        lambda _text: (
            [[0.1]],
            CallMetrics(EMBEDDING_MODEL, 14, 0, 21, "req_question"),
        ),
        generate,
    )
    assert result["retrieved_chunk_ids"] == ["cell"]
    assert result["claims"][0]["citations"][0]["chunk_id"] == "legend"
