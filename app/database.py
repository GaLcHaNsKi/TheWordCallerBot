from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator, Sequence

import aiomysql

from app.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self.pool: aiomysql.Pool | None = None

    async def connect(self) -> None:
        self.pool = await aiomysql.create_pool(
            host=self._settings.mysql_host, port=self._settings.mysql_port,
            user=self._settings.mysql_user, password=self._settings.mysql_password,
            db=self._settings.mysql_database, minsize=1, maxsize=3,
            autocommit=False, charset="utf8mb4",
        )

    async def close(self) -> None:
        if self.pool:
            self.pool.close()
            await self.pool.wait_closed()

    @asynccontextmanager
    async def cursor(self) -> AsyncIterator[aiomysql.DictCursor]:
        if not self.pool:
            raise RuntimeError("Database is not connected")
        async with self.pool.acquire() as connection:
            async with connection.cursor(aiomysql.DictCursor) as cursor:
                try:
                    yield cursor
                    await connection.commit()
                except BaseException:
                    await connection.rollback()
                    raise

    async def execute(self, sql: str, args: Sequence[object] = ()) -> int:
        async with self.cursor() as cur:
            return await cur.execute(sql, args)

    async def fetchone(self, sql: str, args: Sequence[object] = ()) -> dict | None:
        async with self.cursor() as cur:
            await cur.execute(sql, args)
            return await cur.fetchone()

    async def fetchall(self, sql: str, args: Sequence[object] = ()) -> list[dict]:
        async with self.cursor() as cur:
            await cur.execute(sql, args)
            return list(await cur.fetchall())

    async def migrate(self) -> None:
        if not self.pool:
            raise RuntimeError("Database is not connected")
        async with self.pool.acquire() as connection:
            async with connection.cursor() as cur:
                # CREATE TABLE IF NOT EXISTS is intentionally repeatable at startup.
                await cur.execute("SET sql_notes = 0")
                for migration in sorted((Path(__file__).parent.parent / "migrations").glob("*.sql")):
                    sql = migration.read_text(encoding="utf-8")
                    for statement in sql.split(";\n"):
                        if statement.strip() and not statement.lstrip().startswith("--"):
                            await cur.execute(statement)
            await connection.commit()

    async def purge_old_metrics(self, days: int = 90) -> int:
        return await self.execute("DELETE FROM message_metrics WHERE sent_at < DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s DAY)", (days,))
