from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.services.statistics import calculate_metrics


def test_metrics_rules() -> None:
    metrics = calculate_metrics("Я думаю, что я понял #мысль, #мысль #мысли спасибо, благодарю?", datetime(2026, 1, 1, 23, tzinfo=timezone.utc), ZoneInfo("UTC"))
    assert metrics.i_count == 2
    assert metrics.thoughts == 1
    assert metrics.questions == 1
    assert metrics.gratitude == 2
    assert metrics.night == 1


def test_morning() -> None:
    assert calculate_metrics("Текст", datetime(2026, 1, 1, 6, tzinfo=timezone.utc), ZoneInfo("UTC")).morning == 1
