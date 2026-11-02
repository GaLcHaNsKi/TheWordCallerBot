from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.database import Database
from app.services.bible_catalog import BOOKS, books_by_testament, find_book
from app.services.reading import ReadingService
from app.services.reports import ReportService
from app.services.statistics import NOMINATIONS, calculate_metrics
from app.utils.timezones import as_time, parse_timezone, timezone_from_db
from app.utils.russian import plural

router = Router()


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📖 Выбрать книгу", callback_data="admin:books")],
        [InlineKeyboardButton(text="⏸ Приостановить / ▶️ Возобновить", callback_data="admin:toggle")],
        [InlineKeyboardButton(text="📄 Опубликовать сейчас", callback_data="admin:postnow")],
        [InlineKeyboardButton(text="🏆 Номинации", callback_data="admin:nominations")],
    ])


async def nominations_keyboard(db: Database, chat_id: int, thread_id: int) -> InlineKeyboardMarkup:
    rows = await db.fetchall("SELECT nomination,enabled FROM nomination_settings WHERE chat_id=%s AND thread_id=%s", (chat_id, thread_id))
    active = {row["nomination"]: row["enabled"] for row in rows}
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{'✅' if active.get(key, 1) else '❌'} {title}", callback_data=f"nom:{key}")]
        for key, (title, *_rest) in NOMINATIONS.items()
    ])


async def settings_for(db: Database, message: Message) -> dict | None:
    if not message.chat or message.message_thread_id is None:
        return None
    row = await db.fetchone("SELECT * FROM chat_settings WHERE chat_id=%s", (message.chat.id,))
    return row if row and row["thread_id"] == message.message_thread_id else None


async def admin(bot: Bot, message: Message) -> bool:
    if not message.from_user:
        return False
    member = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return member.status in {"creator", "administrator"}


@router.message(Command("bind"))
async def bind(message: Message, command: CommandObject, db: Database, bot: Bot) -> None:
    if message.chat.type not in {"group", "supergroup"} or message.message_thread_id is None:
        await message.answer("Выполните /bind внутри темы супергруппы.")
        return
    if not await admin(bot, message):
        await message.answer("Только администратор может привязать тему.")
        return
    existing = await db.fetchone("SELECT * FROM chat_settings WHERE chat_id=%s", (message.chat.id,))
    if existing and existing["thread_id"] != message.message_thread_id and (command.args or "").strip().casefold() != "confirm":
        await message.answer("Группа уже привязана к другой теме. Повторите /bind confirm для переноса.")
        return
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.execute("""INSERT INTO chat_settings (chat_id,thread_id,timezone_type,timezone_value,daily_time,weekly_time,bound_at,created_at,updated_at)
        VALUES (%s,%s,'IANA','UTC','08:00','21:00',%s,%s,%s) ON DUPLICATE KEY UPDATE thread_id=VALUES(thread_id),bound_at=VALUES(bound_at),last_report_end_at=NULL,updated_at=VALUES(updated_at)""", (message.chat.id, message.message_thread_id, now, now, now))
    for nomination in NOMINATIONS:
        await db.execute("INSERT IGNORE INTO nomination_settings (chat_id,thread_id,nomination,enabled) VALUES (%s,%s,%s,1)", (message.chat.id, message.message_thread_id, nomination))
    await message.answer("✅ Тема привязана. Часовой пояс: UTC; главы будут выходить в 08:00.")


@router.message(Command("setbook"))
async def setbook(message: Message, command: CommandObject, db: Database, reading: ReadingService, bot: Bot) -> None:
    setting = await settings_for(db, message)
    if not setting or not await admin(bot, message): return
    args = (command.args or "").rsplit(maxsplit=1)
    if not args:
        await message.answer("Пример: /setbook ин 1")
        return
    start = int(args[-1]) if args[-1].isdigit() else 1
    query = args[0] if args[-1].isdigit() else command.args
    book = find_book(query or "")
    if not book:
        await message.answer("Не удалось однозначно определить книгу. Используйте /books.")
        return
    try:
        await reading.set_book(message.chat.id, message.message_thread_id, book, start, setting)
        await message.answer(f"✅ Выбрана книга «{book.name}». Следующая глава: {start}.")
    except ValueError as exc:
        await message.answer(str(exc))


@router.message(Command("timezone"))
async def set_timezone(message: Message, command: CommandObject, db: Database, bot: Bot, reading: ReadingService) -> None:
    setting = await settings_for(db, message)
    if not setting:
        return
    if not command.args:
        await message.answer(f"Текущий пояс: {setting['timezone_value']}. Пример: /timezone Asia/Dushanbe или /timezone +5")
        return
    if not await admin(bot, message): return
    try:
        kind, value, _ = parse_timezone(command.args)
    except ValueError as exc:
        await message.answer(str(exc)); return
    await db.execute("UPDATE chat_settings SET timezone_type=%s,timezone_value=%s,updated_at=UTC_TIMESTAMP() WHERE chat_id=%s", (kind, value, message.chat.id))
    changed = await settings_for(db, message)
    await reading.reschedule(message.chat.id, message.message_thread_id, changed)
    await message.answer(f"✅ Часовой пояс изменён: {value}")


@router.message(Command("time", "weektime"))
async def set_time(message: Message, command: CommandObject, db: Database, bot: Bot, reading: ReadingService) -> None:
    setting = await settings_for(db, message)
    if not setting or not await admin(bot, message): return
    try:
        value = datetime.strptime(command.args or "", "%H:%M").time()
    except ValueError:
        await message.answer("Используйте формат HH:MM."); return
    column = "daily_time" if command.command == "time" else "weekly_time"
    await db.execute(f"UPDATE chat_settings SET {column}=%s,updated_at=UTC_TIMESTAMP() WHERE chat_id=%s", (value, message.chat.id))
    if column == "daily_time":
        changed = await settings_for(db, message)
        await reading.reschedule(message.chat.id, message.message_thread_id, changed)
    await message.answer(f"✅ Время изменено: {value:%H:%M}")


@router.message(Command("pause", "resume"))
async def pause(message: Message, command: CommandObject, db: Database, bot: Bot) -> None:
    setting = await settings_for(db, message)
    if not setting or not await admin(bot, message): return
    status = "PAUSED" if command.command == "pause" else "ACTIVE"
    await db.execute("UPDATE reading_history SET status=%s WHERE chat_id=%s AND thread_id=%s AND status IN ('ACTIVE','PAUSED')", (status,message.chat.id,message.message_thread_id))
    await message.answer("⏸ Чтение приостановлено." if status == "PAUSED" else "▶️ Чтение возобновлено.")


@router.message(Command("books"))
async def books(message: Message) -> None:
    for testament, label in (("ВЗ", "ВЕТХИЙ ЗАВЕТ"), ("НЗ", "НОВЫЙ ЗАВЕТ")):
        lines = [f"<b>{label}</b>"] + [f"{book.name} — {book.aliases[0]}" for book in books_by_testament(testament)]
        await message.answer("\n".join(lines), parse_mode="HTML")


@router.message(Command("help"))
async def help_(message: Message) -> None:
    await message.answer("<b>📖 Бот совместного чтения Библии</b>\n\nКаждый день публикуется одна глава. Делитесь размышлениями с #мысль; по воскресеньям выходят итоги активности.\n\n<b>Команды:</b> /books, /status, /today, /progress, /stats, /report, /report last\n\nАдминистраторам: /bind, /setbook, /time, /weektime, /timezone, /pause, /resume, /postnow.\n\n📚 Полный список книг Библии и их сокращений: /books", parse_mode="HTML")


@router.message(Command("admin"))
async def admin_menu(message: Message, db: Database, bot: Bot) -> None:
    setting = await settings_for(db, message)
    if not setting or not await admin(bot, message):
        await message.answer("Эта команда доступна администраторам в привязанной теме.")
        return
    reading = await db.fetchone("""SELECT r.next_chapter,r.status,b.name_ru,b.chapters_count FROM reading_history r JOIN bible_books b ON b.id=r.book_id
        WHERE r.chat_id=%s AND r.thread_id=%s AND r.status IN ('ACTIVE','PAUSED') ORDER BY r.id DESC LIMIT 1""", (message.chat.id,message.message_thread_id))
    book = f"{reading['name_ru']}, следующая {reading['next_chapter']}/{reading['chapters_count']}" if reading else "не выбрана"
    await message.answer(f"<b>⚙️ Управление чтением</b>\n\n📖 Книга: {book}\n⏰ Публикация: {as_time(setting['daily_time']):%H:%M}, {setting['timezone_value']}\n🏆 Отчёт: воскресенье, {as_time(setting['weekly_time']):%H:%M}", parse_mode="HTML", reply_markup=admin_keyboard())


@router.message(Command("nominations"))
async def nominations_menu(message: Message, db: Database, bot: Bot) -> None:
    setting = await settings_for(db, message)
    if not setting or not await admin(bot, message):
        await message.answer("Команда доступна администраторам в привязанной теме.")
        return
    keyboard = await nominations_keyboard(db, message.chat.id, message.message_thread_id)
    await message.answer("🏆 <b>Номинации</b>\n\nНажмите кнопку, чтобы включить или отключить номинацию.", parse_mode="HTML", reply_markup=keyboard)


@router.callback_query(F.data.startswith("admin:"))
async def admin_callback(callback: CallbackQuery, db: Database, bot: Bot, reading: ReadingService) -> None:
    if not callback.message or not callback.from_user or not await admin(bot, callback.message):
        await callback.answer("Недостаточно прав.", show_alert=True); return
    setting = await settings_for(db, callback.message)
    if not setting:
        await callback.answer("Эта тема больше не привязана.", show_alert=True); return
    action = callback.data.split(":", 1)[1]
    if action == "toggle":
        row = await db.fetchone("SELECT id,status FROM reading_history WHERE chat_id=%s AND thread_id=%s AND status IN ('ACTIVE','PAUSED') ORDER BY id DESC LIMIT 1", (callback.message.chat.id,callback.message.message_thread_id))
        if not row: await callback.answer("Нет активного чтения.", show_alert=True); return
        status = "PAUSED" if row['status'] == "ACTIVE" else "ACTIVE"
        await db.execute("UPDATE reading_history SET status=%s WHERE id=%s", (status,row['id']))
        await callback.answer("Настройка сохранена.")
    elif action == "postnow":
        row = await db.fetchone("""SELECT r.*,s.daily_time,s.timezone_type,s.timezone_value,b.name_ru,b.api_slug,b.chapters_count,b.testament FROM reading_history r JOIN chat_settings s USING(chat_id) JOIN bible_books b ON b.id=r.book_id WHERE r.chat_id=%s AND r.thread_id=%s AND r.status='ACTIVE'""", (callback.message.chat.id,callback.message.message_thread_id))
        if not row: await callback.answer("Нет активного чтения.", show_alert=True); return
        await callback.answer("Начинаю публикацию.")
        await reading.post_now(row)
    elif action == "nominations":
        keyboard = await nominations_keyboard(db, callback.message.chat.id, callback.message.message_thread_id)
        await callback.message.answer("Выберите номинацию для включения или выключения:", reply_markup=keyboard)
        await callback.answer()
    elif action == "books":
        await callback.message.answer("Выберите Завет:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="Ветхий Завет", callback_data="books:ВЗ:0"), InlineKeyboardButton(text="Новый Завет", callback_data="books:НЗ:0")]]))
        await callback.answer()


@router.callback_query(F.data.startswith("books:"))
async def books_callback(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    if not callback.message or not await admin(bot, callback.message):
        await callback.answer("Недостаточно прав.", show_alert=True); return
    _, testament, page_raw = callback.data.split(":")
    page, entries = int(page_raw), list(books_by_testament(testament))
    chunk = entries[page * 8:(page + 1) * 8]
    buttons = [[InlineKeyboardButton(text=book.name, callback_data=f"pick:{book.id}")] for book in chunk]
    nav = []
    if page: nav.append(InlineKeyboardButton(text="◀️", callback_data=f"books:{testament}:{page - 1}"))
    if (page + 1) * 8 < len(entries): nav.append(InlineKeyboardButton(text="▶️", callback_data=f"books:{testament}:{page + 1}"))
    if nav: buttons.append(nav)
    await callback.message.edit_text("Выберите книгу:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("pick:"))
async def pick_book(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.message or not await admin(bot, callback.message):
        await callback.answer("Недостаточно прав.", show_alert=True); return
    book = next((item for item in BOOKS if item.id == int(callback.data.split(":")[1])), None)
    if not book: await callback.answer("Книга не найдена.", show_alert=True); return
    starts = [1, 2, 3, 5, 10, book.chapters]
    starts = list(dict.fromkeys(chapter for chapter in starts if chapter <= book.chapters))
    buttons = [[InlineKeyboardButton(text=str(chapter), callback_data=f"confirmbook:{book.id}:{chapter}") for chapter in starts]]
    await callback.message.edit_text(f"{book.name}. Выберите начальную главу:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("confirmbook:"))
async def confirm_book(callback: CallbackQuery, db: Database, bot: Bot, reading: ReadingService) -> None:
    if not callback.message or not await admin(bot, callback.message):
        await callback.answer("Недостаточно прав.", show_alert=True); return
    _, book_id, chapter = callback.data.split(":")
    book = next(item for item in BOOKS if item.id == int(book_id))
    setting = await settings_for(db, callback.message)
    if not setting: await callback.answer("Тема не привязана.", show_alert=True); return
    await reading.set_book(callback.message.chat.id, callback.message.message_thread_id, book, int(chapter), setting)
    await callback.message.edit_text(f"✅ Выбрана книга «{book.name}», глава {chapter}.")
    await callback.answer()


@router.callback_query(F.data.startswith("nom:"))
async def nomination_callback(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    if not callback.message or not await admin(bot, callback.message):
        await callback.answer("Недостаточно прав.", show_alert=True); return
    setting = await settings_for(db, callback.message)
    if not setting: await callback.answer("Тема не привязана.", show_alert=True); return
    nomination = callback.data.split(":", 1)[1]
    if nomination not in NOMINATIONS: await callback.answer("Некорректная номинация.", show_alert=True); return
    await db.execute("""INSERT INTO nomination_settings (chat_id,thread_id,nomination,enabled) VALUES (%s,%s,%s,0)
       ON DUPLICATE KEY UPDATE enabled=NOT enabled""", (callback.message.chat.id,callback.message.message_thread_id,nomination))
    keyboard = await nominations_keyboard(db, callback.message.chat.id, callback.message.message_thread_id)
    await callback.message.edit_reply_markup(reply_markup=keyboard)
    await callback.answer("Настройка изменена.")


@router.message(Command("status", "progress", "today", "stats", "mystats"))
async def info(message: Message, command: CommandObject, db: Database) -> None:
    setting = await settings_for(db, message)
    if not setting: return
    reading = await db.fetchone("""SELECT r.*,b.name_ru,b.chapters_count FROM reading_history r JOIN bible_books b ON b.id=r.book_id
        WHERE r.chat_id=%s AND r.thread_id=%s ORDER BY r.id DESC LIMIT 1""", (message.chat.id,message.message_thread_id))
    if command.command == "stats":
        row = await db.fetchone("SELECT COUNT(*) messages,COALESCE(SUM(thought_count),0) thoughts,COUNT(DISTINCT user_id) users FROM message_metrics WHERE chat_id=%s AND thread_id=%s", (message.chat.id,message.message_thread_id))
        await message.answer(f"Учтено сообщений: {row['messages']}\nМыслей: {row['thoughts']}\nУчастников: {row['users']}"); return
    if command.command == "mystats":
        if not message.from_user: return
        row = await db.fetchone("SELECT * FROM user_totals WHERE chat_id=%s AND thread_id=%s AND user_id=%s", (message.chat.id,message.message_thread_id,message.from_user.id))
        if not row:
            await message.answer("Вашей учтённой активности пока нет."); return
        await message.answer(f"Ваши сообщения: {row['message_count']}\nСлова: {row['word_count']}\nМысли: {row['thought_count']}\nБлагодарности: {row['gratitude_count']}"); return
    if command.command == "today":
        publication = await db.fetchone("""SELECT p.chapter,p.completed_at,b.name_ru,MIN(pp.telegram_message_id) message_id FROM publications p
            JOIN bible_books b ON b.id=p.book_id LEFT JOIN publication_parts pp ON pp.publication_id=p.id
            WHERE p.chat_id=%s AND p.thread_id=%s AND p.publication_type='CHAPTER' AND p.status='COMPLETED'
            GROUP BY p.id ORDER BY p.completed_at DESC LIMIT 1""", (message.chat.id,message.message_thread_id))
        if not publication:
            await message.answer("Глава ещё не публиковалась."); return
        link = f"https://t.me/c/{str(message.chat.id)[4:]}/{publication['message_id']}" if publication['message_id'] else ""
        await message.answer(f"📖 {publication['name_ru']}, глава {publication['chapter']}\nОпубликована: {publication['completed_at']:%d.%m.%Y}\n{link}"); return
    if command.command == "progress":
        completed = await db.fetchone("SELECT COUNT(*) books FROM reading_history WHERE chat_id=%s AND thread_id=%s AND status='COMPLETED'", (message.chat.id,message.message_thread_id))
        published = await db.fetchone("SELECT COUNT(*) chapters FROM publications WHERE chat_id=%s AND thread_id=%s AND publication_type='CHAPTER' AND status='COMPLETED'", (message.chat.id,message.message_thread_id))
        current = ""
        if reading:
            current_count = max(0, reading['next_chapter'] - 1)
            current = f"\nТекущая книга: {reading['name_ru']} — {current_count}/{reading['chapters_count']} глав"
        await message.answer(f"Завершено книг: {completed['books']}\nПрочитано всего: {published['chapters']} {plural(int(published['chapters']), 'глава', 'главы', 'глав')}{current}"); return
    if not reading:
        await message.answer("Книга ещё не выбрана."); return
    await message.answer(f"📖 {reading['name_ru']}\nСтатус: {reading['status']}\nСледующая глава: {reading['next_chapter']}/{reading['chapters_count']}\nПубликация: {as_time(setting['daily_time']):%H:%M}, {setting['timezone_value']}")


@router.message(Command("report"))
async def report(message: Message, command: CommandObject, db: Database, reports: ReportService) -> None:
    setting = await settings_for(db, message)
    if not setting: return
    if (command.args or "").strip() == "last":
        if not await reports.send_last(setting):
            await message.answer("Завершённых отчётов пока нет.")
        return
    await reports.send_period(setting, setting['last_report_end_at'] or setting['bound_at'], datetime.now(timezone.utc).replace(tzinfo=None), automatic=False)


@router.message(Command("postnow"))
async def post_now(message: Message, db: Database, reading: ReadingService, bot: Bot) -> None:
    setting = await settings_for(db,message)
    if not setting or not await admin(bot,message): return
    row = await db.fetchone("""SELECT r.*,s.daily_time,s.timezone_type,s.timezone_value,b.name_ru,b.api_slug,b.chapters_count,b.testament FROM reading_history r
        JOIN chat_settings s USING(chat_id) JOIN bible_books b ON b.id=r.book_id WHERE r.chat_id=%s AND r.thread_id=%s AND r.status='ACTIVE'""", (message.chat.id,message.message_thread_id))
    if not row: await message.answer("Нет активного чтения."); return
    await reading.post_now(row)


@router.message(F.text | F.caption)
@router.edited_message(F.text | F.caption)
async def metrics(message: Message, db: Database) -> None:
    if not message.from_user or message.from_user.is_bot or (message.text or message.caption or "").startswith("/"): return
    setting = await settings_for(db,message)
    if not setting: return
    text = message.text or message.caption or ""
    tz = timezone_from_db(setting['timezone_type'],setting['timezone_value'])
    m = calculate_metrics(text, message.date, tz)
    await db.execute("INSERT INTO users (user_id,first_name,last_name,username,last_seen_at) VALUES (%s,%s,%s,%s,UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE first_name=VALUES(first_name),last_name=VALUES(last_name),username=VALUES(username),last_seen_at=VALUES(last_seen_at)", (message.from_user.id,message.from_user.first_name,message.from_user.last_name,message.from_user.username))
    await db.execute("""INSERT INTO message_metrics (chat_id,thread_id,message_id,user_id,sent_at,word_count,i_count,thought_count,question_count,gratitude_count,night_count,morning_count)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE edited_at=UTC_TIMESTAMP(),word_count=VALUES(word_count),i_count=VALUES(i_count),thought_count=VALUES(thought_count),question_count=VALUES(question_count),gratitude_count=VALUES(gratitude_count),night_count=VALUES(night_count),morning_count=VALUES(morning_count)""", (message.chat.id,message.message_thread_id,message.message_id,message.from_user.id,message.date.replace(tzinfo=None),m.words,m.i_count,m.thoughts,m.questions,m.gratitude,m.night,m.morning))
    # Rebuild one small aggregate from numeric metrics. This makes edits idempotent.
    totals = await db.fetchone("""SELECT COUNT(*) message_count,COALESCE(SUM(word_count),0) word_count,COALESCE(SUM(thought_count),0) thought_count,
        COALESCE(SUM(i_count),0) i_count,COALESCE(SUM(question_count),0) question_count,COALESCE(SUM(gratitude_count),0) gratitude_count,
        COALESCE(SUM(night_count),0) night_count,COALESCE(SUM(morning_count),0) morning_count FROM message_metrics WHERE chat_id=%s AND thread_id=%s AND user_id=%s""", (message.chat.id,message.message_thread_id,message.from_user.id))
    await db.execute("""INSERT INTO user_totals (chat_id,thread_id,user_id,message_count,word_count,thought_count,i_count,question_count,gratitude_count,night_count,morning_count)
       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE message_count=VALUES(message_count),word_count=VALUES(word_count),thought_count=VALUES(thought_count),i_count=VALUES(i_count),question_count=VALUES(question_count),gratitude_count=VALUES(gratitude_count),night_count=VALUES(night_count),morning_count=VALUES(morning_count)""", (message.chat.id,message.message_thread_id,message.from_user.id,totals["message_count"],totals["word_count"],totals["thought_count"],totals["i_count"],totals["question_count"],totals["gratitude_count"],totals["night_count"],totals["morning_count"]))
