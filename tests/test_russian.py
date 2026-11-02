from app.utils.russian import plural


def test_russian_plural_forms() -> None:
    forms = ("слово благодарности", "слова благодарности", "слов благодарности")
    assert plural(1, *forms) == "слово благодарности"
    assert plural(2, *forms) == "слова благодарности"
    assert plural(5, *forms) == "слов благодарности"
    assert plural(11, *forms) == "слов благодарности"
    assert plural(22, *forms) == "слова благодарности"
