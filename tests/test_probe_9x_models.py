from car_knowledge_rag.openai_models import TextChunk
from car_knowledge_rag.probe_9x_models import check_chunk_boundaries, compare_vectors


def test_embedding_probe_reports_distractor_rank():
    documents = [
        {"name": "six_seat", "question": "六座续航？"},
        {"name": "five_seat", "question": "五座续航？"},
    ]
    six, five = compare_vectors(documents, [[2, 0], [0, 3], [1, 0], [2, 1]])
    assert six["expected_rank"] == 1
    assert six["ranked"][0] == {"document": "six_seat", "cosine": 1.0}
    assert five["expected_rank"] == 2


def test_chunking_probe_checks_original_line_numbers_and_split_conditions():
    result = check_chunk_boundaries(
        "seat_and_display",
        [TextChunk(1, 6, ""), TextChunk(7, 7, ""), TextChunk(8, 11, "")],
    )
    assert result["chunk_lines"] == [[176, 181], [182, 182], [183, 186]]
    assert result["checks"] == {
        "seat_functions_and_scope": False,
        "sliding_display_specs": True,
    }
