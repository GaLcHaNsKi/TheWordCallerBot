from app.services.bible_catalog import BOOKS, find_book


def test_all_books_are_present() -> None:
    assert len(BOOKS) == 66
    assert find_book("ин").slug == "john"
    assert find_book("1Кор").slug == "1corinthians"
    assert find_book("1 Кор").slug == "1corinthians"


def test_rejects_unknown_book() -> None:
    assert find_book("несуществующая") is None
