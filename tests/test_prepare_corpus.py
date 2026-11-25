import pytest

from car_knowledge_rag.prepare_corpus import extract_product

PRODUCT = """
<div class="zeekr-001 top">
  <div><h1>极氪9X</h1><button>预约试驾</button></div>
  <div class="anchor" id="chassis">
    <div class="chapter-9x"><div class="title">底盘</div></div>
  </div>
  <div><div>空气悬架</div><div>110 mm</div><div>* 按官方条件测试</div></div>
  <div><div class="consult-wrapper">
    <label>预约车型</label><p class="extra-content">* 以实际交付为准</p>
  </div></div>
  <div><div class="footer-wrapper">网站页脚</div></div>
</div>
"""
VISIBLE = (
    "导航\n极氪9X\n预约试驾\n底盘\n空气悬架\n110 mm\n* 按官方条件测试"
    "\n预约车型\n\n* 以实际交付为准\n网站页脚"
)


def test_product_preserves_line_numbers_and_notices_when_cleaning():
    result = extract_product(PRODUCT, VISIBLE)
    hero, chapter, suspension = result["blocks"]
    assert hero["lines"] == [{"line": 2, "text": "极氪9X"}]
    assert chapter["anchor"] == "chassis"
    assert suspension["section"] == ["底盘"]
    assert suspension["lines"] == [
        {"line": 5, "text": "空气悬架"},
        {"line": 6, "text": "110 mm"},
        {"line": 7, "text": "* 按官方条件测试"},
    ]
    assert result["notices"] == [
        {"source": "S2", "line": 10, "text": "* 以实际交付为准"}
    ]


def test_product_rejects_drift_instead_of_assigning_wrong_line_numbers():
    with pytest.raises(ValueError, match="differ at line 5"):
        extract_product(PRODUCT, VISIBLE.replace("110 mm", "100 mm"))
