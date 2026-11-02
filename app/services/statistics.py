from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re
from zoneinfo import ZoneInfo

WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
I_RE = re.compile(r"(?<!\w)я(?!\w)", re.IGNORECASE)
THOUGHT_RE = re.compile(r"(?<!\w)#мысль(?!\w)", re.IGNORECASE)
THANKS = frozenset({"спасибо", "благодарю", "благодарим", "благодарен", "благодарна", "благодарны"})


@dataclass(frozen=True, slots=True)
class Metrics:
    words: int
    i_count: int
    thoughts: int
    questions: int
    gratitude: int
    night: int
    morning: int


def calculate_metrics(text: str, sent_at: datetime, tz: ZoneInfo) -> Metrics:
    words = [word.casefold() for word in WORD_RE.findall(text)]
    hour = sent_at.astimezone(tz).hour
    return Metrics(
        words=len(words), i_count=len(I_RE.findall(text)), thoughts=int(bool(THOUGHT_RE.search(text))),
        questions=int("?" in text), gratitude=sum(word in THANKS for word in words),
        night=int(hour >= 22 or hour < 5), morning=int(5 <= hour < 8),
    )


NOMINATIONS = {
    "talkative": ("🗣 БОЛТУНЫ НЕДЕЛИ", "На этой неделе самыми болтливыми оказались:", "message_count", "сообщений"),
    "thinkers": ("💡 МЫСЛИТЕЛИ НЕДЕЛИ", "Больше всех размышляли над Писанием:", "thought_count", "мыслей"),
    "proud": ("👑 «СКРОМНЫЕ» НЕДЕЛИ", "А вот кто чаще всех вспоминал о себе любимом:", "i_count", "раз"),
    "questions": ("❓ ПОЧЕМУЧКИ НЕДЕЛИ", "У кого на этой неделе возникло больше всего вопросов?", "question_count", "вопросов"),
    "night": ("🌙 НОЧНЫЕ СТРАЖИ", "Пока другие спали, эти стражи несли свою службу:", "night_count", "сообщений ночью"),
    "morning": ("🌅 РАННИЕ ПТАШКИ", "Раньше всех просыпались и писали:", "morning_count", "сообщений утром"),
    "gratitude": ("❤️ САМЫЕ БЛАГОДАРНЫЕ", "Больше всех делились благодарностью:", "gratitude_count", "слов благодарности"),
    "authors": ("✍️ АВТОРЫ ПОСЛАНИЙ", "Кажется, эти участники могли бы написать целое послание:", "word_count", "слов"),
    "consistent": ("🌱 ВЕРНЫЕ В МАЛОМ", "А вот кто проявил постоянство с момента запуска чтения:", "active_days", "дней активности"),
}
