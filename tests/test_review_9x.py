import pytest

from car_knowledge_rag.review_9x import classify, review


def test_rejects_unpinned_text():
    with pytest.raises(ValueError, match="pinned"):
        review(b"wrong snapshot", {}, {}, {})


def test_conditions_do_not_turn_ambiguous_values_into_single_numbers():
    assert classify(9, "55/70", True) == ("insufficient_evidence", None)
    assert classify(205, "●1082/○1050", True) == (
        "confirmed_conditions",
        {"H7": 1082, "H9": 1050},
    )
    assert classify(205, "●1082/○1050", False) == ("difference", None)
