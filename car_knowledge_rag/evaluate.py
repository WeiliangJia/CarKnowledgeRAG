"""Run and summarize the C7 question-answering evaluation."""

import argparse
import hashlib
import importlib
import json
import sys
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "evaluation"
FAILURE_REASONS = frozenset(
    {
        "incorrect_value",
        "wrong_version",
        "missing_citation",
        "missed_clarification",
        "wrong_scope",
        "unsupported_claim",
        "incomplete_answer",
        "other",
    }
)


def read_jsonl(path):
    data = path.read_bytes()
    records = {}
    for line_number, line in enumerate(data.decode("utf-8-sig").split("\n"), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from error
        if not isinstance(record, dict) or not nonempty(record.get("id")):
            raise ValueError(f"{path}:{line_number}: expected an object with an ID")
        case_id = record["id"]
        if case_id in records:
            raise ValueError(f"{path}:{line_number}: duplicate ID {case_id}")
        records[case_id] = record
    if not records:
        raise ValueError(f"{path}: empty file")
    return records, hashlib.sha256(data).hexdigest()


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def read_dataset(split):
    cases, digest = read_jsonl(DATA / f"9x-{split}.jsonl")
    for case in cases.values():
        required = ("question", "category", "expected", "pass_rule")
        if (
            not all(nonempty(case.get(key)) for key in required)
            or not isinstance(case.get("context", ""), str)
            or not isinstance(case.get("evidence"), list)
            or not case["evidence"]
        ):
            raise ValueError(f"{case['id']}: invalid dataset record")
    return cases, digest


def prompts(case):
    return {key: case[key] for key in ("id", "question", "context") if key in case}


def validate_verdict(verdict):
    if not isinstance(verdict, dict) or type(verdict.get("passed")) is not bool:
        raise ValueError("expected a Boolean passed value")
    reasons = verdict.get("reasons", [])
    if not isinstance(reasons, list) or any(
        not isinstance(reason, str) or reason not in FAILURE_REASONS
        for reason in reasons
    ):
        raise ValueError("invalid failure reason codes")
    if len(reasons) != len(set(reasons)) or verdict["passed"] == bool(reasons):
        raise ValueError(
            "failed verdicts require distinct reasons; passes require none"
        )
    detail = verdict.get("detail", "")
    if not isinstance(detail, str) or (not verdict["passed"] and not detail.strip()):
        raise ValueError("failed verdicts require a written detail")
    return {
        "status": "pass" if verdict["passed"] else "fail",
        "reasons": reasons,
        "detail": detail,
    }


def run_cases(cases, answer, judge):
    for case in cases.values():
        result = {**prompts(case), "category": case["category"], "answer": None}
        stage = "answer"
        try:
            response = answer(case["question"], case.get("context"))
            if not isinstance(response, str):
                raise TypeError("Answerer must return text")
            result["answer"] = response
            if not response.strip():
                yield {
                    **result,
                    "status": "fail",
                    "reasons": ["empty_answer"],
                    "detail": "Answerer returned no text.",
                }
                continue
            stage = "judge"
            verdict = validate_verdict(judge(case, response))
        except Exception as error:
            verdict = {
                "status": "error",
                "reasons": [f"{stage}_error"],
                "detail": type(error).__name__,
            }
        yield {**result, **verdict}


def score_cases(cases, judgments):
    missing = cases.keys() - judgments.keys()
    extra = judgments.keys() - cases.keys()
    if missing or extra:
        raise ValueError(
            f"Judgment IDs differ: missing={sorted(missing)}, extra={sorted(extra)}"
        )
    for case_id, case in cases.items():
        judgment = judgments[case_id]
        answer = judgment.get("answer")
        if not isinstance(answer, str):
            raise ValueError(f"{case_id}: expected a text answer")
        try:
            verdict = validate_verdict(judgment)
            if verdict["status"] == "pass" and not answer.strip():
                raise ValueError("empty answers cannot pass")
        except ValueError as error:
            raise ValueError(f"{case_id}: {error}") from error
        yield {
            **prompts(case),
            "category": case["category"],
            "answer": answer,
            **verdict,
        }


def metrics(results):
    counts = Counter(result["status"] for result in results)
    total = len(results)
    return {
        "total": total,
        "passed": counts["pass"],
        "failed": counts["fail"],
        "errors": counts["error"],
        "pass_rate": counts["pass"] / total,
    }


def summarize(results):
    categories = {}
    for result in results:
        categories.setdefault(result["category"], []).append(result)
    return {
        "overall": metrics(results),
        "by_category": {name: metrics(items) for name, items in categories.items()},
        "failure_reasons": dict(
            Counter(
                reason
                for result in results
                if result["status"] == "fail"
                for reason in result["reasons"]
            )
        ),
        "execution_errors": dict(
            Counter(
                result["reasons"][0]
                for result in results
                if result["status"] == "error"
            )
        ),
    }


def load_adapter(reference):
    module, separator, name = reference.partition(":")
    if not separator or not module or not name:
        raise ValueError("adapter must use module:function")
    try:
        adapter = getattr(importlib.import_module(module), name)
    except Exception as error:
        raise ValueError(
            f"Could not load {reference} ({type(error).__name__})"
        ) from error
    if not callable(adapter):
        raise ValueError(f"{reference} is not callable")
    return adapter


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("dev", "test"), required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prompts", help="Print question inputs as JSONL")
    run = commands.add_parser("run", help="Run the answerer and judge in sequence")
    run.add_argument("--answerer", required=True, metavar="MODULE:FUNCTION")
    run.add_argument("--judge", required=True, metavar="MODULE:FUNCTION")
    score = commands.add_parser("score", help="Summarize reviewed answers from JSONL")
    score.add_argument("judgments", type=Path)
    args = parser.parse_args()
    try:
        cases, digest = read_dataset(args.split)
        if args.command == "prompts":
            for case in cases.values():
                print(json.dumps(prompts(case), ensure_ascii=False))
            return 0
        if args.command == "run":
            with redirect_stdout(sys.stderr):
                answer = load_adapter(args.answerer)
                judge = load_adapter(args.judge)
                results = list(run_cases(cases, answer, judge))
        else:
            judgments, _ = read_jsonl(args.judgments)
            results = list(score_cases(cases, judgments))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    summary = summarize(results)
    report = {
        "split": args.split,
        "dataset_sha256": digest,
        "mode": args.command,
        **summary,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(summary["overall"]["errors"]))


if __name__ == "__main__":
    sys.exit(main())
