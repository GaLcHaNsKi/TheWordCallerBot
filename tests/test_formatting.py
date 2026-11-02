from app.services.formatting import LIMIT, chapter_parts


def test_chapter_is_split_without_losing_verses() -> None:
    verses = ["короткий стих", "другой стих", "x" * 4050]
    parts = chapter_parts("Заголовок", verses, "\nподпись")
    assert len(parts) >= 2
    assert all(len(part) <= LIMIT for part in parts)
    assert sum("короткий стих" in part for part in parts) == 1
    assert sum("другой стих" in part for part in parts) == 1
