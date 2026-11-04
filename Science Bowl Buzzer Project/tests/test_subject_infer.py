from __future__ import annotations

from science_bowl_buzzer.subject_infer import infer_subjects_from_text


def test_infer_subjects_from_science_bowl_headers():
    text = """
    TOSS-UP
    1) BIOLOGY Short Answer
    This is a question.

    BONUS
    1) BIOLOGY Multiple Choice
    Bonus text.

    TOSS-UP
    2) EARTH AND SPACE SCIENCE Multiple Choice
    More text.
    """

    subjects = infer_subjects_from_text(text)

    assert subjects[1] == "Biology"
    assert subjects[2] == "Earth And Space Science"
    assert len(subjects) == 2

