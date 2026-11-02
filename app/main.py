from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import logging

from aiogram import Bot, Dispatcher

from app.config import Settings
from app.database import Database
from app.handlers.common import router
from app.services.bible_api import BibleApi
from app.services.bible_catalog import BOOKS
from app.services.reading import ReadingService
from app.services.reports import ReportService


async def seed_catalog(db: Database) -> None:
    async with db.cursor() as cur:
        await cur.execute("SET sql_notes = 0")
        for book in BOOKS:
            await cur.execute("""INSERT INTO bible_books (id,name_ru,abbreviation,api_slug,chapters_count,testament)
                VALUES (%s,%s,%s,%s,%s,%s) AS new ON DUPLICATE KEY UPDATE name_ru=new.name_ru,abbreviation=new.abbreviation,api_slug=new.api_slug,chapters_count=new.chapters_count,testament=new.testament""", (book.id,book.name,book.aliases[0],book.slug,book.chapters,book.testament))


async def scheduler(settings: Settings, reading: ReadingService, reports: ReportService) -> None:
    last_cleanup_day = None
    while True:
        try:
            await reading.publish_due()
            await reports.send_due()
            today = datetime.now(timezone.utc).date()
            if today != last_cleanup_day:
                await reading.db.purge_old_metrics()
                last_cleanup_day = today
        except Exception:
            logging.getLogger(__name__).exception("Scheduled task failed")
        await asyncio.sleep(settings.scheduler_interval_seconds)


async def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    db = Database(settings)
    await db.connect()
    await db.migrate()
    await seed_catalog(db)
    bot = Bot(settings.bot_token)
    api = BibleApi(settings.bible_api_url, settings.bible_version)
    await api.start()
    reading = ReadingService(db, api, bot)
    reports = ReportService(db, bot)
    dispatcher = Dispatcher(db=db, reading=reading, reports=reports)
    dispatcher.include_router(router)
    schedule_task = asyncio.create_task(scheduler(settings, reading, reports))
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        schedule_task.cancel()
        with suppress(asyncio.CancelledError):
            await schedule_task
        await api.close()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
