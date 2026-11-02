from __future__ import annotations

from dataclasses import dataclass
import logging

import aiohttp

from app.services.bible_catalog import Book

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Chapter:
    verses: tuple[str, ...]
    copyright: str
    etag: str | None


class BibleApiError(RuntimeError):
    pass


class BibleApi:
    def __init__(self, base_url: str, version: str = "synodal") -> None:
        self.base_url, self.version = base_url.rstrip("/"), version
        self.session: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))

    async def close(self) -> None:
        if self.session:
            await self.session.close()

    async def fetch_chapter(self, book: Book, chapter: int, etag: str | None = None) -> Chapter | None:
        if not self.session:
            raise RuntimeError("Bible API session is not started")
        headers = {"If-None-Match": etag} if etag else {}
        url = f"{self.base_url}/v1/{self.version}/{book.slug}/{chapter}"
        try:
            async with self.session.get(url, headers=headers) as response:
                if response.status == 304:
                    return None
                payload = await response.json(content_type=None)
                if response.status != 200:
                    raise BibleApiError(str(payload.get("error", {}).get("message", response.status)))
        except (aiohttp.ClientError, ValueError) as exc:
            raise BibleApiError("Не удалось получить главу из Bible API") from exc
        data, meta = payload.get("data"), payload.get("meta", {})
        if not isinstance(data, dict) or data.get("version") != self.version:
            raise BibleApiError("API вернул неожиданный перевод")
        verses = data.get("verses")
        if not isinstance(verses, list) or not verses or not all(isinstance(v, str) and v.strip() for v in verses):
            raise BibleApiError("API вернул пустой или некорректный текст главы")
        return Chapter(tuple(verses), str(meta.get("copyright", "")), response.headers.get("ETag"))
