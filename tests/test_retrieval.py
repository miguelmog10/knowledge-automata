import pytest

from knowledge_automata.core.retrieval import comparison_text, cosine, top_k


def test_comparison_text_keeps_what_was_decided():
    content = {
        "title": "One status ladder",
        "statement": "Every batch moves through one ladder.",
        "context": "Growers asked for it.",
        "rationale": "Learn the screen once.",
        "alternatives": ["Per crop statuses"],
    }
    assert comparison_text(content) == (
        "One status ladder\nEvery batch moves through one ladder.\nGrowers asked for it."
    )


def test_comparison_text_without_context():
    content = {"statement": "S", "title": "T", "impacts": "I"}
    assert comparison_text(content) == "T\nS"


def test_cosine_of_equal_opposite_orthogonal_and_zero_vectors():
    assert cosine([1.0, 2.0], [2.0, 4.0]) == pytest.approx(1.0)
    assert cosine([1.0, 2.0], [-1.0, -2.0]) == pytest.approx(-1.0)
    assert cosine([1.0, 0.0], [0.0, 3.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0
    assert cosine([0.0, 0.0], [0.0, 0.0]) == 0.0


def test_cosine_refuses_vectors_of_different_lengths():
    with pytest.raises(ValueError, match="differ in length"):
        cosine([1.0], [1.0, 0.0])


def test_top_k_orders_by_similarity_best_first():
    vectors = {"DEC-0001": [0.0, 1.0], "DEC-0002": [1.0, 0.1], "DEC-0003": [1.0, 1.0]}
    assert top_k([1.0, 0.0], vectors, 2) == ["DEC-0002", "DEC-0003"]


def test_top_k_breaks_ties_by_id_ascending_by_sequence():
    vectors = {"DEC-10000": [1.0, 0.0], "DEC-0002": [2.0, 0.0], "DEC-9999": [3.0, 0.0]}
    assert top_k([1.0, 0.0], vectors, 3) == ["DEC-0002", "DEC-9999", "DEC-10000"]


def test_top_k_larger_than_the_register_returns_every_record():
    vectors = {"DEC-0002": [1.0, 0.0], "DEC-0001": [0.0, 1.0]}
    assert top_k([0.0, 1.0], vectors, 10) == ["DEC-0001", "DEC-0002"]
    assert top_k([0.0, 1.0], {}, 10) == []


def test_top_k_needs_at_least_one():
    with pytest.raises(ValueError):
        top_k([1.0], {"DEC-0001": [1.0]}, 0)
