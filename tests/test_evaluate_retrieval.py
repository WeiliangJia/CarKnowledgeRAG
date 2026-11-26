import pytest

from car_knowledge_rag.evaluate_retrieval import (
    evaluate,
    query_text,
    score_top_k,
    ultra_group,
    version_filter,
)
from car_knowledge_rag.openai_models import EMBEDDING_MODEL, CallMetrics


def config_point(point_id, group):
    return {
        "id": point_id,
        "score": 0.7,
        "payload": {
            "kind": "configuration",
            "version": {"group": group, "label": "Ultra版"},
        },
    }


def test_evaluate_reuses_query_for_version_filter_and_scores_all_evidence():
    calls = []
    cases = {
        "Q01": {
            "id": "Q01",
            "question": "六座 Ultra 的续航？",
            "category": "lookup",
            "expected": "scoring information",
        }
    }
    labels = {
        "dataset_sha256": "dataset",
        "chunks_sha256": "chunks",
        "cases": [
            {
                "id": "Q01",
                "evidence_units": [
                    {
                        "source": "S1",
                        "row_index": 20,
                        "column_index": 2,
                        "chunk_ids": ["six"],
                    },
                    {
                        "source": "S1",
                        "note": 1,
                        "chunk_ids": ["note", "note-alternate"],
                    },
                ],
            }
        ],
    }
    vector = [1.0]
    six = config_point("six", "9X六座版")
    wrong = config_point("five", "9X五座版")
    note = {"id": "note-alternate", "payload": {"kind": "configuration_notice"}}

    def embed_queries(texts):
        assert texts == ["六座 Ultra 的续航？"]
        return [vector], CallMetrics(EMBEDDING_MODEL, 6, 0, 120, "req_test")

    def api(method, path, body):
        assert method == "POST" and path == "/collections/test/points/query"
        assert (
            body["query"] is vector
            and body["limit"] == 10
            and body["params"] == {"exact": True}
        )
        calls.append(body)
        if "filter" in body:
            assert body["filter"] == version_filter("9X六座版")
            return {"points": [six, note]}
        return {"points": [wrong, six]}

    report = evaluate(api, "test", cases, labels, embed_queries)
    assert len(calls) == 2
    for k in ("5", "10"):
        comparison = report["version_comparison"]["all"][k]
        assert comparison["unfiltered"]["mixing_rate"] == 1
        assert comparison["filtered"]["mixing_rate"] == 0
        assert comparison["gained_complete"] == ["Q01"]


@pytest.mark.parametrize(
    ("question", "context", "category", "expected"),
    [
        ("六座 Ultra 的曜黑外观套件有车色限制吗？", None, "lookup", "9X六座版"),
        ("它有座椅通风吗？", "上一轮提到五座 Ultra。", "conversation", "9X五座版"),
        ("Ultra 的续航？", None, "clarification", None),
        ("五座 Ultra 和六座 Ultra 有什么区别？", None, "comparison", None),
        ("换成五座 Hyper 后还标配吗？", "上一轮提到五座 Ultra。", "conversation", None),
        ("换成六座 Ultra 有什么变化？", "上一轮提到五座 Ultra。", "conversation", None),
    ],
)
def test_ultra_pair_requires_one_explicit_version(
    question, context, category, expected
):
    case = {"question": question, "context": context, "category": category}
    assert ultra_group(case, query_text(case)) == expected


def test_top5_is_prefix_of_top10_and_duplicate_candidates_count_once():
    points = [{"id": str(i)} for i in range(10)]
    evidence = [
        {"source": "S2", "line": 20, "chunk_ids": ["0", "1"]},
        {"source": "S2", "line": 21, "chunk_ids": ["5"]},
    ]
    top5 = score_top_k(points, evidence, 5)
    top10 = score_top_k(points, evidence, 10)
    assert top5["hit_units"] == 1 and top5["complete"] is False
    assert top10["hit_units"] == 2 and top10["complete"] is True
