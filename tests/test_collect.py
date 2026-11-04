import json
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import TimeoutError as BrowserTimeout

from car_knowledge_rag.collect import (
    ModelSource,
    capture,
    main,
    validate_columns,
    validate_url,
    write_json,
)


@pytest.fixture
def model() -> ModelSource:
    return ModelSource(
        name="极氪 9X",
        model_info_id="10",
        model_year_code="GMY_9X_01",
        product_url="https://www.zeekrlife.com/zh-cn/zeekr9x?modelInfoId=10&modelYearCode=GMY_9X_01",
        config_url="https://www.zeekrlife.com/zh-cn/config?modelInfoId=10&modelYearCode=GMY_9X_01",
        columns=[{"label": "Max版"}, {"label": "Ultra版"}],
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/zh-cn/config?modelInfoId=10&modelYearCode=GMY_9X_01",
        "https://www.zeekrlife.com/zh-cn/config?modelInfoId=11&modelYearCode=GMY_9X_01",
        "https://www.zeekrlife.com/zh-cn/config?modelInfoId=10&modelYearCode=OLD",
        "http://www.zeekrlife.com/zh-cn/config?modelInfoId=10&modelYearCode=GMY_9X_01",
    ],
)
def test_reject_unexpected_url(model, url):
    with pytest.raises(ValueError):
        validate_url(url, model, "config")


def test_columns_preserve_duplicate_counts(model):
    validate_columns(["Max 版", "Ultra版"], model)
    with pytest.raises(ValueError):
        validate_columns(["Max版", "Max版", "Ultra版"], model)
    with pytest.raises(ValueError):
        validate_columns(["Max版"], model)


def make_page(model):
    page = MagicMock()
    page.url = model.config_url
    page.goto.return_value.status = 200
    page.goto.return_value.ok = True
    page.goto.return_value.text.return_value = "<html>initial source</html>"
    page.content.return_value = "<html>rendered configuration</html>"
    page.locator.return_value.all_text_contents.return_value = ["Max版", "Ultra版"]
    page.locator.return_value.inner_text.return_value = "极氪9X 配置与脚注"
    return page


def test_capture_keeps_initial_and_rendered_content(model, tmp_path):
    directory = tmp_path / "capture"
    receipt = capture(make_page(model), model, "config", directory, 100)
    assert receipt["status"] == "success"
    assert receipt["requested_url"] == model.config_url
    assert (directory / "response.html").read_text(
        encoding="utf-8"
    ) == "<html>initial source</html>"
    assert (directory / "rendered.html").read_text(
        encoding="utf-8"
    ) == "<html>rendered configuration</html>"
    assert (
        json.loads((directory / "receipt.json").read_text(encoding="utf-8")) == receipt
    )


def test_timeout_is_failure_not_empty_success(model, tmp_path):
    page = make_page(model)
    page.wait_for_function.side_effect = BrowserTimeout("sample timeout")
    directory = tmp_path / "capture"
    receipt = capture(page, model, "config", directory, 100)
    assert receipt["status"] == "failed"
    assert receipt["failure_category"] == "loading_timeout"
    assert (directory / "response.html").exists()
    assert not (directory / "rendered.html").exists()
    assert (directory / "receipt.json").exists()


def test_changed_columns_are_not_accepted(model, tmp_path):
    page = make_page(model)
    page.locator.return_value.all_text_contents.return_value = ["New版"]
    receipt = capture(page, model, "config", tmp_path / "capture", 100)
    assert receipt["status"] == "failed"


def test_product_landing_is_labelled_not_full_description(model, tmp_path):
    page = make_page(model)
    page.url = model.product_url
    page.locator.return_value.count.return_value = 2
    receipt = capture(page, model, "product", tmp_path / "landing", 100)
    assert receipt["status"] == "success"
    assert receipt["content_role"] == "landing"


def test_browser_start_failure_has_run_receipt(model, tmp_path, monkeypatch):
    from playwright.sync_api import Error as BrowserError

    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"models": [model.model_dump()]}), encoding="utf-8")
    output = tmp_path / "raw"
    monkeypatch.setattr(
        "sys.argv", ["collect", "--source", str(catalog), "--output-root", str(output)]
    )
    playwright = MagicMock()
    playwright.return_value.__enter__.return_value.chromium.launch.side_effect = (
        BrowserError("cannot start")
    )
    monkeypatch.setattr("car_knowledge_rag.collect.sync_playwright", playwright)
    monkeypatch.setattr("car_knowledge_rag.collect.configure_logging", lambda: None)
    with pytest.raises(SystemExit) as raised:
        main()
    assert raised.value.code == 1
    receipts = list(output.glob("*/run.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
    assert receipt["not_attempted"] == 2
    assert receipt["fatal_error_type"] == "Error"


def test_existing_capture_is_not_overwritten(model, tmp_path):
    directory = tmp_path / "capture"
    directory.mkdir()
    marker = directory / "keep.txt"
    marker.write_text("old snapshot", encoding="utf-8")
    with pytest.raises(FileExistsError):
        capture(make_page(model), model, "config", directory, 100)
    assert marker.read_text(encoding="utf-8") == "old snapshot"


def test_receipt_cannot_overwrite_existing_file(tmp_path):
    path = tmp_path / "receipt.json"
    write_json(path, {"status": "original"})
    with pytest.raises(FileExistsError):
        write_json(path, {"status": "changed"})
    assert json.loads(path.read_text()) == {"status": "original"}
