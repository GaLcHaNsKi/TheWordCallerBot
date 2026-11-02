from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from app.database import Database
from app.services.bible_api import BibleApi, BibleApiError, Chapter
from app.services.bible_catalog import Book
from app.services.formatting import chapter_parts
from app.utils.russian import plural
from app.utils.timezones import due_at, timezone_from_db

log = logging.getLogger(__name__)


class ReadingService:
    def __init__(self, db: Database, api: BibleApi, bot: Bot) -> None:
        self.db, self.api, self.bot = db, api, bot

    async def set_book(self, chat_id: int, thread_id: int, book: Book, start: int, settings: dict) -> None:
        if not 1 <= start <= book.chapters:
            raise ValueError(f"В книге «{book.name}» только {book.chapters} глав.")
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        tz = timezone_from_db(settings["timezone_type"], settings["timezone_value"])
        next_due = due_at(datetime.now(timezone.utc), settings["daily_time"], tz).replace(tzinfo=None)
        async with self.db.cursor() as cur:
            await cur.execute("UPDATE reading_history SET status='REPLACED', replaced_at=%s WHERE chat_id=%s AND thread_id=%s AND status IN ('ACTIVE','PAUSED')", (now, chat_id, thread_id))
            await cur.execute("INSERT INTO reading_history (chat_id,thread_id,book_id,next_chapter,status,next_due_at,started_at) VALUES (%s,%s,%s,%s,'ACTIVE',%s,%s)", (chat_id, thread_id, book.id, start, next_due, now))

    async def publish_due(self) -> None:
        rows = await self.db.fetchall("""SELECT r.*, s.daily_time,s.timezone_type,s.timezone_value,b.name_ru,b.api_slug,b.chapters_count,b.testament
            FROM reading_history r JOIN chat_settings s USING(chat_id) JOIN bible_books b ON b.id=r.book_id
            WHERE r.status='ACTIVE' AND r.next_due_at<=UTC_TIMESTAMP()""")
        for row in rows:
            await self.publish(row, automatic=True)

    async def reschedule(self, chat_id: int, thread_id: int, settings: dict) -> None:
        """Move the next automatic occurrence after a time-zone or time change."""
        tz = timezone_from_db(settings["timezone_type"], settings["timezone_value"])
        next_due = due_at(datetime.now(timezone.utc), settings["daily_time"], tz).replace(tzinfo=None)
        await self.db.execute("UPDATE reading_history SET next_due_at=%s WHERE chat_id=%s AND thread_id=%s AND status='ACTIVE'", (next_due, chat_id, thread_id))

    async def post_now(self, row: dict) -> str:
        await self.publish(row, automatic=False)
        return "Глава опубликована." 

    async def publish(self, row: dict, automatic: bool) -> None:
        book = Book(row["book_id"], row["name_ru"], row["api_slug"], row["chapters_count"], row["testament"], ())
        chapter_number = row["next_chapter"]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # The unique logical-publication row stops ordinary restart duplicates.
        try:
            await self.db.execute("INSERT INTO publications (chat_id,thread_id,publication_type,book_id,chapter,status,created_at) VALUES (%s,%s,'CHAPTER',%s,%s,'SENDING',%s)", (row["chat_id"], row["thread_id"], book.id, chapter_number, now))
        except Exception:
            existing = await self.db.fetchone("SELECT id,status FROM publications WHERE chat_id=%s AND thread_id=%s AND publication_type='CHAPTER' AND book_id=%s AND chapter=%s", (row["chat_id"], row["thread_id"], book.id, chapter_number))
            if not existing or existing["status"] in {"COMPLETED", "SENDING", "UNCERTAIN"}:
                return
            await self.db.execute("UPDATE publications SET status='SENDING',last_error=NULL WHERE id=%s", (existing["id"],))
        publication = await self.db.fetchone("SELECT id FROM publications WHERE chat_id=%s AND thread_id=%s AND publication_type='CHAPTER' AND book_id=%s AND chapter=%s", (row["chat_id"], row["thread_id"], book.id, chapter_number))
        try:
            chapter = await self._chapter(book, chapter_number)
            title = f"📖 <b>{book.name.upper()}</b>\n<b>Глава {chapter_number} из {book.chapters}</b>"
            footer = ""
            sent = {part["part_index"] for part in await self.db.fetchall("SELECT part_index FROM publication_parts WHERE publication_id=%s AND status='SENT'", (publication["id"],))}
            for index, text in enumerate(chapter_parts(title, chapter.verses, footer), 1):
                if index in sent:
                    continue
                message = await self.bot.send_message(row["chat_id"], text, message_thread_id=row["thread_id"], parse_mode=ParseMode.HTML)
                await self.db.execute("INSERT INTO publication_parts (publication_id,part_index,telegram_message_id,status,sent_at) VALUES (%s,%s,%s,'SENT',%s)", (publication["id"], index, message.message_id, now))
            await self.bot.send_message(
                row["chat_id"],
                "💭 Делитесь своими мыслями по прочитанному с тегом #мысль.",
                message_thread_id=row["thread_id"],
            )
            await self.db.execute("UPDATE publications SET status='COMPLETED',completed_at=%s WHERE id=%s", (now, publication["id"]))
            tz = timezone_from_db(row["timezone_type"], row["timezone_value"])
            if chapter_number >= book.chapters:
                await self.db.execute("UPDATE reading_history SET status='COMPLETED',completed_at=%s,next_due_at=NULL WHERE id=%s", (now, row["id"]))
                await self.bot.send_message(row["chat_id"], f"🎉 <b>Мы закончили {book.name}!</b>\n\nВместе прочитано: {book.chapters} {plural(book.chapters, 'глава', 'главы', 'глав')}.\n\n🙏 Ожидаем выбора следующей книги.", message_thread_id=row["thread_id"], parse_mode=ParseMode.HTML)
            else:
                base = datetime.now(timezone.utc) + (timedelta(days=1) if not automatic else timedelta())
                next_due = due_at(base, row["daily_time"], tz).replace(tzinfo=None)
                await self.db.execute("UPDATE reading_history SET next_chapter=next_chapter+1,next_due_at=%s WHERE id=%s", (next_due, row["id"]))
        except Exception as exc:
            await self.db.execute("UPDATE publications SET status='FAILED',last_error=%s WHERE id=%s", (str(exc)[:4000], publication["id"]))
            log.exception("Chapter publishing failed")

    async def _chapter(self, book: Book, chapter_number: int) -> Chapter:
        cached = await self.db.fetchone("SELECT verses_json,copyright_text,etag FROM bible_cache WHERE book_id=%s AND chapter=%s AND version='synodal'", (book.id, chapter_number))
        try:
            fresh = await self.api.fetch_chapter(book, chapter_number, cached["etag"] if cached else None)
            if fresh:
                await self.db.execute("""INSERT INTO bible_cache (book_id,chapter,version,verses_json,copyright_text,etag,fetched_at) VALUES (%s,%s,'synodal',%s,%s,%s,UTC_TIMESTAMP())
                    ON DUPLICATE KEY UPDATE verses_json=VALUES(verses_json),copyright_text=VALUES(copyright_text),etag=VALUES(etag),fetched_at=VALUES(fetched_at)""", (book.id, chapter_number, json.dumps(fresh.verses, ensure_ascii=False), fresh.copyright, fresh.etag))
                return fresh
        except BibleApiError:
            if not cached:
                raise
        if cached:
            return Chapter(tuple(json.loads(cached["verses_json"])), cached["copyright_text"] or "", cached["etag"])
        raise BibleApiError("Глава недоступна")
