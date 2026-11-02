from __future__ import annotations

from datetime import datetime, timezone
from html import escape
import json
from typing import Any

from aiogram import Bot
from aiogram.enums import ParseMode

from app.database import Database
from app.services.statistics import NOMINATIONS
from app.utils.russian import plural
from app.utils.timezones import as_time, timezone_from_db


class ReportService:
    def __init__(self, db: Database, bot: Bot) -> None:
        self.db, self.bot = db, bot

    async def send_due(self) -> None:
        now = datetime.now(timezone.utc)
        for setting in await self.db.fetchall("SELECT * FROM chat_settings"):
            local = now.astimezone(timezone_from_db(setting["timezone_type"], setting["timezone_value"]))
            time_ = as_time(setting["weekly_time"])
            if local.weekday() != 6 or (local.hour, local.minute) < (time_.hour, time_.minute):
                continue
            end = local.replace(hour=time_.hour, minute=time_.minute, second=0, microsecond=0).astimezone(timezone.utc).replace(tzinfo=None)
            if await self.db.fetchone("SELECT id FROM report_history WHERE chat_id=%s AND thread_id=%s AND period_end=%s", (setting["chat_id"], setting["thread_id"], end)):
                continue
            await self.send_period(setting, setting["last_report_end_at"] or setting["bound_at"], end, automatic=True)

    async def _enabled(self, setting: dict) -> set[str]:
        rows = await self.db.fetchall("SELECT nomination FROM nomination_settings WHERE chat_id=%s AND thread_id=%s AND enabled=1", (setting["chat_id"], setting["thread_id"]))
        return {row["nomination"] for row in rows}

    async def calculate(self, setting: dict, start: datetime, end: datetime) -> dict[str, list[dict[str, Any]]]:
        """Compute all ratings in Python: fixed offsets and IANA DST get the same local-day behavior."""
        global_start = setting["bound_at"]
        rows = await self.db.fetchall("""SELECT m.*,u.first_name,u.last_name FROM message_metrics m
            LEFT JOIN users u ON u.user_id=m.user_id
            WHERE m.chat_id=%s AND m.thread_id=%s AND m.sent_at >= %s AND m.sent_at < %s
            ORDER BY m.sent_at,m.user_id""", (setting["chat_id"], setting["thread_id"], start, end))
        tz = timezone_from_db(setting["timezone_type"], setting["timezone_value"])
        fields = {key: value[2] for key, value in NOMINATIONS.items()}
        totals: dict[str, dict[int, dict[str, Any]]] = {key: {} for key in NOMINATIONS}
        # The consistency nomination is intentionally global per bound topic;
        # all other nominations remain limited to the requested report period.
        global_rows = await self.db.fetchall("""SELECT m.*,u.first_name,u.last_name FROM message_metrics m
            LEFT JOIN users u ON u.user_id=m.user_id
            WHERE m.chat_id=%s AND m.thread_id=%s AND m.sent_at >= %s AND m.sent_at < %s
            ORDER BY m.sent_at,m.user_id""", (setting["chat_id"], setting["thread_id"], global_start, end))
        for row in rows:
            for key, field in fields.items():
                if key == "consistent":
                    continue
                user_id = row["user_id"]
                item = totals[key].setdefault(user_id, {"user_id": user_id, "value": 0, "first_at": row["sent_at"], "first_name": row["first_name"], "last_name": row["last_name"], "days": set()})
                if key == "talkative":
                    # One stored metric row represents one qualifying message.
                    item["value"] += 1
                else:
                    item["value"] += int(row[field])
        for row in global_rows:
            user_id = row["user_id"]
            item = totals["consistent"].setdefault(user_id, {"user_id": user_id, "value": 0, "first_at": row["sent_at"], "first_name": row["first_name"], "last_name": row["last_name"], "days": set()})
            item["days"].add(row["sent_at"].replace(tzinfo=timezone.utc).astimezone(tz).date().isoformat())
        result: dict[str, list[dict[str, Any]]] = {}
        for key, values in totals.items():
            ranking = []
            for item in values.values():
                if key == "consistent": item["value"] = len(item.pop("days"))
                else: item.pop("days", None)
                if item["value"]: ranking.append(item)
            result[key] = sorted(ranking, key=lambda x: (-x["value"], x["first_at"], x["user_id"]))[:3]
        return result

    async def _send_results(self, setting: dict, results: dict[str, list[dict[str, Any]]], enabled: set[str]) -> None:
        forms = {
            "talkative": ("сообщение", "сообщения", "сообщений"),
            "thinkers": ("мысль", "мысли", "мыслей"),
            "proud": ("раз", "раза", "раз"),
            "questions": ("вопрос", "вопроса", "вопросов"),
            "night": ("ночное сообщение", "ночных сообщения", "ночных сообщений"),
            "morning": ("утреннее сообщение", "утренних сообщения", "утренних сообщений"),
            "gratitude": ("слово благодарности", "слова благодарности", "слов благодарности"),
            "authors": ("слово", "слова", "слов"),
            "consistent": ("день активности", "дня активности", "дней активности"),
        }
        for key, (title, heading, _field, unit) in NOMINATIONS.items():
            rows = results.get(key, [])
            if key not in enabled or not rows: continue
            lines = []
            for index, row in enumerate(rows):
                name = escape(" ".join(filter(None, [row.get("first_name"), row.get("last_name")])) or "Участник")
                value = f"{row['value']} {plural(int(row['value']), *forms[key])}"
                lines.append(f"{['🥇', '🥈', '🥉'][index]} <a href=\"tg://user?id={row['user_id']}\">{name}</a> — {value}")
            text = f"<b>{title}</b>\n\n{heading}\n\n" + "\n".join(lines)
            if key == "proud": text += "\n\n<i>Это всего лишь статистика, а не оценка характера! 😁</i>"
            await self.bot.send_message(setting["chat_id"], text, message_thread_id=setting["thread_id"], parse_mode=ParseMode.HTML)

    async def send_period(self, setting: dict, start: datetime, end: datetime, automatic: bool) -> None:
        enabled, results = await self._enabled(setting), await self.calculate(setting, start, end)
        if automatic:
            tz = timezone_from_db(setting["timezone_type"], setting["timezone_value"])
            a, b = start.replace(tzinfo=timezone.utc).astimezone(tz), end.replace(tzinfo=timezone.utc).astimezone(tz)
            await self.bot.send_message(setting["chat_id"], f"🏆 <b>ИТОГИ НЕДЕЛИ</b>\n<i>Период: {a:%d.%m %H:%M} — {b:%d.%m %H:%M}</i>", message_thread_id=setting["thread_id"], parse_mode=ParseMode.HTML)
        await self._send_results(setting, results, enabled)
        if automatic:
            packed = {key: [{**item, "first_at": item["first_at"].isoformat()} for item in values] for key, values in results.items()}
            await self.db.execute("INSERT INTO report_history (chat_id,thread_id,period_start,period_end,results_json,created_at) VALUES (%s,%s,%s,%s,%s,UTC_TIMESTAMP())", (setting["chat_id"], setting["thread_id"], start, end, json.dumps(packed, ensure_ascii=False)))
            await self.db.execute("UPDATE chat_settings SET last_report_end_at=%s WHERE chat_id=%s", (end, setting["chat_id"]))

    async def send_last(self, setting: dict) -> bool:
        row = await self.db.fetchone("SELECT results_json FROM report_history WHERE chat_id=%s AND thread_id=%s ORDER BY period_end DESC LIMIT 1", (setting["chat_id"], setting["thread_id"]))
        if not row: return False
        saved = json.loads(row["results_json"])
        for values in saved.values():
            for item in values: item["first_at"] = datetime.fromisoformat(item["first_at"])
        # Historical output must not change merely because an admin later toggled a nomination.
        await self._send_results(setting, saved, set(saved))
        return True
