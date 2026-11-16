import json
import sys
from types import ModuleType

import pytest

from car_knowledge_rag.evaluate import main, read_dataset


@pytest.mark.parametrize(("split", "total"), [("dev", 96), ("test", 24)])
def test_run_batches_real_cases_without_passing_answers_to_answerer(
    monkeypatch, capsys, split, total
):
    cases, _ = read_dataset(split)
    inputs = [(case["question"], case.get("context")) for case in cases.values()]
    calls = []
    adapter = ModuleType("evaluation_fixture")

    def answer(question, context):
        print("answerer diagnostic")
        calls.append((question, context))
        if len(calls) == 3:
            raise RuntimeError("internal connection details")
        return "70 kWh" if len(calls) == 1 else "fixture response"

    def judge(case, response):
        assert case["expected"] and case["pass_rule"] and case["evidence"]
        assert (case["question"], case.get("context")) == calls[-1]
        if len(calls) == 2:
            return {"passed": "true"}
        if response == "70 kWh":
            return {
                "passed": False,
                "reasons": ["incorrect_value", "missing_citation"],
                "detail": "Wrong amount and missing source.",
            }
        return {"passed": True}

    adapter.answer = answer
    adapter.judge = judge
    monkeypatch.setitem(sys.modules, adapter.__name__, adapter)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate",
            "--split",
            split,
            "run",
            "--answerer",
            "evaluation_fixture:answer",
            "--judge",
            "evaluation_fixture:judge",
        ],
    )
    assert main() == 1
    captured = capsys.readouterr()
    assert "answerer diagnostic" in captured.err
    report = json.loads(captured.out)
    assert calls == inputs
    assert [row["id"] for row in report["results"]] == list(cases)
    assert report["overall"] == {
        "total": total,
        "passed": total - 3,
        "failed": 1,
        "errors": 2,
        "pass_rate": (total - 3) / total,
    }
    assert len(report["by_category"]) == 8
    assert report["failure_reasons"] == {"incorrect_value": 1, "missing_citation": 1}
    assert report["execution_errors"] == {"judge_error": 1, "answer_error": 1}
    assert report["results"][2]["detail"] == "RuntimeError"


def test_prompts_and_offline_scoring_validate_complete_review(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(sys, "argv", ["evaluate", "--split", "test", "prompts"])
    assert main() == 0
    prompts = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(prompts) == 24
    assert all(set(case) <= {"id", "question", "context"} for case in prompts)
    path = tmp_path / "judgments.jsonl"
    judgments = [
        {"id": prompt["id"], "answer": "reviewed fixture", "passed": True}
        for prompt in prompts
    ]
    judgments[0].update(passed=False, reasons=["wrong_version"], detail="Wrong trim.")
    path.write_text("\n".join(map(json.dumps, reversed(judgments))), encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", ["evaluate", "--split", "test", "score", str(path)]
    )
    assert main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["by_category"]["lookup"]["pass_rate"] == 0.75
    assert report["results"][0]["detail"] == "Wrong trim."
    path.write_text(json.dumps(judgments[0]), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert not output.out
    assert "Judgment IDs differ" in output.err
