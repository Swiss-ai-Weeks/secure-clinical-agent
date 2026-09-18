"""Postgres connection pool (role p360_app).

Autocommit is on: every statement is its own short transaction. The audit hash
chain holds an advisory lock until commit (04-audit.sql), so audit inserts must
never sit inside a longer request transaction.
"""

from __future__ import annotations

from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool


class Database:
    def __init__(self, dsn: str, *, min_size: int = 1, max_size: int = 10) -> None:
        self.pool = AsyncConnectionPool(
            dsn,
            open=False,
            min_size=min_size,
            max_size=max_size,
            kwargs={"row_factory": dict_row, "autocommit": True},
        )

    async def open(self) -> None:
        await self.pool.open()
        await self.pool.wait()

    async def close(self) -> None:
        await self.pool.close()
