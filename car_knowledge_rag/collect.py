"""Save public source pages without parsing vehicle configuration facts."""

import argparse
import json
import logging
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from playwright.sync_api import Error as BrowserError
from playwright.sync_api import TimeoutError as BrowserTimeout
from playwright.sync_api import sync_playwright
from pydantic import BaseModel, Field

from car_knowledge_rag.logging_config import configure_logging

ROOT = Path(__file__).resolve().parents[1]
logger = logging.getLogger("car_knowledge_rag.collect")


class Column(BaseModel):
    group: str | None = None
    label: str


class ModelSource(BaseModel):
    name: str
    model_info_id: str = Field(pattern=r"^\d+$")
    model_year_code: str
    product_url: str
    config_url: str
    columns: list[Column] = Field(min_length=1)


class Catalog(BaseModel):
    models: list[ModelSource] = Field(min_length=1)


def validate_url(url: str, model: ModelSource, kind: str) -> None:
    parsed = urlsplit(url)
    query = parse_qs(parsed.query)
    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.zeekrlife.com"
        or not parsed.path.startswith("/zh-cn/")
        or (kind == "config" and parsed.path != "/zh-cn/config")
        or query.get("modelInfoId") != [model.model_info_id]
        or query.get("modelYearCode") != [model.model_year_code]
    ):
        raise ValueError("Source URL does not match the official catalog identity")


def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text)


def validate_columns(observed: list[str], model: ModelSource) -> None:
    if Counter(map(normalize, observed)) != Counter(
        normalize(column.label) for column in model.columns
    ):
        raise ValueError("Configuration columns differ from B1; review the catalog")


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def capture(
    page,
    model: ModelSource,
    kind: str,
    directory: Path,
    timeout: int,
    discovered_from: str | None = None,
) -> dict:
    url = model.config_url if kind == "config" else model.product_url
    receipt = {
        "model_info_id": model.model_info_id,
        "model_year_code": model.model_year_code,
        "name": model.name,
        "kind": kind,
        "requested_url": url,
        "discovered_from_url": discovered_from,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "failed",
        "files": [],
    }
    directory.mkdir(parents=True, exist_ok=False)
    try:
        response = page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        receipt["final_url"] = page.url
        validate_url(page.url, model, kind)
        receipt["http_status"] = response.status if response else None
        if response is None or not response.ok:
            raise ValueError("The official page did not return a successful response")
        source = directory / "response.html"
        source.write_text(response.text(), encoding="utf-8")
        receipt["files"].append(source.name)
        if kind == "config":
            page.wait_for_function(
                """count => document.querySelectorAll('.model-item .title').length
                    >= count && document.querySelectorAll('.name .el-tooltip').length
                    > 0 && document.querySelectorAll('.config-tips .tip-content').length > 0""",
                arg=len(model.columns),
                timeout=timeout,
            )
            observed = page.locator(".model-item .title").all_text_contents()
            validate_columns(observed, model)
            for group in {column.group for column in model.columns if column.group}:
                if normalize(group) not in normalize(page.locator("body").inner_text()):
                    raise ValueError("Expected configuration group is missing")
            receipt["observed_columns"] = observed
        else:
            page.wait_for_function(
                """() => Array.from(document.querySelectorAll('#app > div'))
                    .filter(e => !e.classList.contains('navigation')
                        && !e.classList.contains('footertoast'))
                    .some(e => e.innerText.length > 1000)
                    || (document.querySelectorAll('.car-item .button').length > 0
                        && Array.from(document.querySelectorAll('.car-item .button'))
                            .every(e => e.innerText.trim() === '了解更多'))""",
                timeout=timeout,
            )
            receipt["content_role"] = (
                "landing"
                if page.locator(".car-item .button").count()
                else "description"
            )
        rendered = page.content()
        text = page.locator("body").inner_text()
        if normalize(model.name.removeprefix("焕新")) not in normalize(text):
            raise ValueError("Expected model name is missing from the loaded page")
        (directory / "rendered.html").write_text(rendered, encoding="utf-8")
        (directory / "text.txt").write_text(text, encoding="utf-8")
        receipt["files"].extend(["rendered.html", "text.txt"])
        receipt["status"] = "success"
    except (BrowserError, ValueError) as error:
        receipt["error_type"] = type(error).__name__
        if isinstance(error, ValueError):
            receipt["reason"] = str(error)
        receipt["failure_category"] = (
            "loading_timeout" if isinstance(error, BrowserTimeout) else "capture_error"
        )
        logger.error(
            "Capture failed model=%s kind=%s type=%s",
            model.model_info_id,
            kind,
            type(error).__name__,
        )
    receipt["finished_at"] = datetime.now(timezone.utc).isoformat()
    write_json(directory / "receipt.json", receipt)
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / "data/sources/zeekr-2026-11-04.json"
    )
    parser.add_argument("--output-root", type=Path, default=ROOT / "data/raw/zeekr")
    parser.add_argument(
        "--model-id", action="append", help="Limit to catalog modelInfoId"
    )
    parser.add_argument(
        "--channel", choices=["chromium", "msedge", "chrome"], default="chromium"
    )
    parser.add_argument("--timeout-ms", type=int, default=60000)
    args = parser.parse_args()
    if args.timeout_ms <= 0:
        parser.error("--timeout-ms must be positive")
    catalog_text = args.source.read_text(encoding="utf-8")
    models = Catalog.model_validate_json(catalog_text).models
    if len({model.model_info_id for model in models}) != len(models):
        parser.error("Duplicate modelInfoId in catalog")
    selected = set(args.model_id or [model.model_info_id for model in models])
    if selected - {model.model_info_id for model in models}:
        parser.error("Unknown --model-id")
    models = [model for model in models if model.model_info_id in selected]
    for model in models:
        validate_url(model.product_url, model, "product")
        validate_url(model.config_url, model, "config")
    configure_logging()
    run_id = (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex[:8]
    )
    run_dir = args.output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "source-catalog.json").write_text(catalog_text, encoding="utf-8")
    receipts = []
    fatal_error = None
    extra_pages = 0
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel=None if args.channel == "chromium" else args.channel,
                headless=True,
            )
            try:
                context = browser.new_context(locale="zh-CN")
                page = context.new_page()
                for model in models:
                    for kind in ("product", "config"):
                        receipt = capture(
                            page,
                            model,
                            kind,
                            run_dir / model.model_info_id / kind,
                            args.timeout_ms,
                        )
                        receipts.append(receipt)
                        logger.info(
                            "Capture model=%s kind=%s status=%s",
                            model.model_info_id,
                            kind,
                            receipt["status"],
                        )
                        time.sleep(0.5)
                        if receipt.get("content_role") == "landing":
                            detail_count = page.locator(".car-item .button").count()
                            extra_pages += detail_count
                            for index in range(detail_count):
                                page.goto(
                                    model.product_url,
                                    wait_until="domcontentloaded",
                                    timeout=args.timeout_ms,
                                )
                                page.locator(".car-item .button").nth(index).wait_for(
                                    timeout=args.timeout_ms
                                )
                                page.locator(".car-item .button").nth(index).click()
                                page.wait_for_url(
                                    lambda current: current != model.product_url,
                                    timeout=args.timeout_ms,
                                )
                                detail = model.model_copy(
                                    update={"product_url": page.url}
                                )
                                validate_url(detail.product_url, detail, "product")
                                detail_kind = f"detail-{index + 1}"
                                detail_receipt = capture(
                                    page,
                                    detail,
                                    detail_kind,
                                    run_dir / model.model_info_id / detail_kind,
                                    args.timeout_ms,
                                    discovered_from=model.product_url,
                                )
                                receipts.append(detail_receipt)
                                logger.info(
                                    "Capture model=%s kind=%s status=%s",
                                    model.model_info_id,
                                    detail_kind,
                                    detail_receipt["status"],
                                )
                                time.sleep(0.5)
            finally:
                browser.close()
    except (BrowserError, ValueError) as error:
        fatal_error = type(error).__name__
        logger.error("Browser aborted type=%s", fatal_error)
    failed = sum(receipt["status"] != "success" for receipt in receipts)
    not_attempted = len(models) * 2 + extra_pages - len(receipts)
    write_json(
        run_dir / "run.json",
        {
            "run_id": run_id,
            "channel": args.channel,
            "total": len(receipts),
            "failed": failed,
            "not_attempted": not_attempted,
            "fatal_error_type": fatal_error,
            "pages": receipts,
        },
    )
    logger.info(
        "Capture finished pages=%s failed=%s output=%s", len(receipts), failed, run_dir
    )
    raise SystemExit(1 if failed or not_attempted or fatal_error else 0)


if __name__ == "__main__":
    main()
