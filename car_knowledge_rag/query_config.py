"""Query configuration facts in a specified PostgreSQL snapshot."""

import argparse
import json
import operator
import os
import sys
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

OPERATORS = {
    "eq": operator.eq,
    "lt": operator.lt,
    "le": operator.le,
    "gt": operator.gt,
    "ge": operator.ge,
}
STATUSES = ("standard", "optional", "unavailable")

FACTS = text("""
    SELECT row_index, column_index, raw, number, status, qualifier,
           footnote_ids, pending_reason, review_status, review_evidence
    FROM config_facts
    WHERE snapshot_id = :snapshot_id
      AND row_index IN :rows AND column_index IN :columns
""").bindparams(bindparam("rows", expanding=True), bindparam("columns", expanding=True))


class SelectionError(ValueError):
    def __init__(self, status, entity, requested, candidates=()):
        super().__init__(f"{entity}: {status}")
        self.result = {
            "status": status,
            "entity": entity,
            "requested": requested,
            "candidates": list(candidates),
        }


def select_one(entity, requested, candidates):
    if len(candidates) != 1:
        status = "ambiguous" if candidates else "not_found"
        raise SelectionError(status, entity, requested, candidates)
    return candidates[0]


@dataclass(frozen=True)
class NumericCondition:
    field: str
    operator: str
    value: str | int | Decimal
    unit: str


@dataclass(frozen=True)
class StatusCondition:
    field: str
    value: str


class ConfigQuery:
    def __init__(self, connection, snapshot_id):
        self.connection = connection
        self.snapshot_id = snapshot_id
        snapshot = (
            connection.execute(
                text("""
                SELECT id AS snapshot_id, model_info_id, model_year_code,
                       source_url, captured_at, source, footnotes
                FROM config_snapshots WHERE id = :snapshot_id
            """),
                {"snapshot_id": snapshot_id},
            )
            .mappings()
            .one_or_none()
        )
        if snapshot is None:
            raise SelectionError("not_found", "snapshot", snapshot_id)
        self.source = dict(snapshot)
        self.footnotes = self.source.pop("footnotes")

    def versions(self):
        return self._rows(
            text("""
            SELECT column_index, group_label, label
            FROM config_versions WHERE snapshot_id = :snapshot_id
            ORDER BY column_index
        """)
        )

    def fields(self):
        return self._rows(
            text("""
            SELECT row_index, field_id, name, unit, test_cycle, range_type,
                   definition ->> 'source_label' AS source_label
            FROM config_fields WHERE snapshot_id = :snapshot_id
            ORDER BY row_index
        """)
        )

    def _rows(self, statement, **params):
        return [
            dict(row)
            for row in self.connection.execute(
                statement, {"snapshot_id": self.snapshot_id, **params}
            ).mappings()
        ]

    def _facts(self, versions, fields):
        facts = self._rows(
            FACTS,
            rows=[field["row_index"] for field in fields],
            columns=[version["column_index"] for version in versions],
        )
        for fact in facts:
            fact["footnotes"] = {
                ref: self.footnotes[ref] for ref in fact["footnote_ids"]
            }
        return {(fact["row_index"], fact["column_index"]): fact for fact in facts}

    def lookup(self, field, version, *, group=None):
        """Read one field by exact ID or label, for a column or exact version label."""
        candidates = [
            item
            for item in self.versions()
            if version in (item["column_index"], item["label"])
            and (group is None or group == item["group_label"])
        ]
        version = select_one(
            "version", {"version": version, "group": group}, candidates
        )
        field = resolve_field(field, self.fields())
        fact = self._facts([version], [field]).get(
            (field["row_index"], version["column_index"])
        )
        return {"source": self.source, "version": version, "field": field, "fact": fact}

    def compare(self, columns, fields):
        """Return each requested field with facts in the requested column order."""
        if len(columns) < 2 or len(set(columns)) != len(columns) or not fields:
            raise ValueError("Provide at least two distinct columns and one field")
        available = {item["column_index"]: item for item in self.versions()}
        versions = [
            select_one(
                "version", column, [available[column]] if column in available else []
            )
            for column in columns
        ]
        catalog = self.fields()
        fields = [resolve_field(field, catalog) for field in fields]
        facts = self._facts(versions, fields)
        return {
            "source": self.source,
            "versions": versions,
            "rows": [
                {
                    "field": field,
                    "facts": [facts.get((field["row_index"], col)) for col in columns],
                }
                for field in fields
            ],
        }

    def filter(self, conditions):
        """Evaluate all conditions for every version in the selected snapshot."""
        if not conditions:
            raise ValueError("Provide at least one condition")
        catalog = self.fields()
        fields = [resolve_field(condition.field, catalog) for condition in conditions]
        checks = [
            prepare_condition(condition, field)
            for condition, field in zip(conditions, fields, strict=True)
        ]
        versions = self.versions()
        facts = self._facts(versions, fields)
        result = {
            "source": self.source,
            "match": [],
            "no_match": [],
            "undetermined": [],
        }
        for version in versions:
            details = []
            for field, (attribute, compare, expected) in zip(
                fields, checks, strict=True
            ):
                fact = facts.get((field["row_index"], version["column_index"]))
                outcome = evaluate(fact, attribute, compare, expected)
                details.append({"field": field, "fact": fact, "outcome": outcome})
            outcomes = {item["outcome"] for item in details}
            if "no_match" in outcomes:
                outcome = "no_match"
            elif "undetermined" in outcomes:
                outcome = "undetermined"
            else:
                outcome = "match"
            result[outcome].append({"version": version, "conditions": details})
        return result


def resolve_field(requested, fields):
    exact_id = [field for field in fields if requested == field["field_id"]]
    candidates = exact_id or [
        field for field in fields if requested in (field["name"], field["source_label"])
    ]
    return select_one("field", requested, candidates)


def prepare_condition(condition, field):
    if isinstance(condition, StatusCondition):
        if condition.value not in STATUSES:
            raise ValueError(f"Expected a status in {', '.join(STATUSES)}")
        return "status", operator.eq, condition.value
    if not isinstance(condition, NumericCondition):
        raise ValueError("Expected a numeric or status condition")
    if field["unit"] is None or condition.unit != field["unit"]:
        raise ValueError(
            f"{field['field_id']} requires unit {field['unit']!r} for numeric filtering"
        )
    if condition.operator not in OPERATORS:
        raise ValueError(f"Expected an operator in {', '.join(OPERATORS)}")
    try:
        value = Decimal(condition.value)
    except (InvalidOperation, TypeError) as error:
        raise ValueError("Expected a finite decimal threshold") from error
    if not value.is_finite():
        raise ValueError("Expected a finite decimal threshold")
    return "number", OPERATORS[condition.operator], value


def evaluate(fact, attribute, compare, expected):
    if (
        fact is None
        or fact["pending_reason"]
        or fact["qualifier"]
        or fact["review_status"] == "insufficient_evidence"
    ):
        return "undetermined"
    actual = fact[attribute]
    if actual is None or actual == "unknown":
        return "undetermined"
    return "match" if compare(actual, expected) else "no_match"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--snapshot", required=True, help="Snapshot ID printed by import_config"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("catalog", help="List exact version and field selectors")
    lookup = commands.add_parser("lookup", help="Read one configuration fact")
    version = lookup.add_mutually_exclusive_group(required=True)
    version.add_argument("--column", type=int)
    version.add_argument("--version")
    lookup.add_argument("--group")
    lookup.add_argument("--field", required=True)
    compare = commands.add_parser("compare", help="Compare columns side by side")
    compare.add_argument("--column", type=int, action="append", required=True)
    compare.add_argument("--field", action="append", required=True)
    filters = commands.add_parser(
        "filter", help="Evaluate AND conditions on all columns"
    )
    filters.add_argument(
        "--number",
        nargs=4,
        metavar=("FIELD", "OP", "VALUE", "UNIT"),
        action="append",
        default=[],
    )
    filters.add_argument(
        "--status", nargs=2, metavar=("FIELD", "STATUS"), action="append", default=[]
    )
    args = parser.parse_args()
    try:
        engine = create_engine(os.environ["DATABASE_URL"])
    except (KeyError, ValueError, SQLAlchemyError):
        parser.exit(1, "Query failed; check DATABASE_URL.\n")
    try:
        with engine.connect() as connection:
            query = ConfigQuery(connection, args.snapshot)
            if args.command == "lookup":
                version = args.column if args.column is not None else args.version
                result = query.lookup(args.field, version, group=args.group)
            elif args.command == "compare":
                result = query.compare(args.column, args.field)
            elif args.command == "filter":
                result = query.filter(
                    [NumericCondition(*values) for values in args.number]
                    + [StatusCondition(*values) for values in args.status]
                )
            else:
                result = {
                    "source": query.source,
                    "versions": query.versions(),
                    "fields": query.fields(),
                }
    except SelectionError as error:
        print(json.dumps(error.result, ensure_ascii=False))
        return 2
    except ValueError as error:
        parser.exit(2, f"Invalid query: {error}\n")
    except SQLAlchemyError as error:
        parser.exit(
            1,
            f"Query failed ({type(error).__name__}); check DATABASE_URL and migration.\n",
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
