from revu.application.config import get_settings
from revu.application.base.singleton import Singleton
import aiosqlite


INIT = [
    """
    CREATE TABLE IF NOT EXISTS repositories (
        repo_name TEXT PRIMARY KEY,
        reviews INTEGER DEFAULT 0
    )"""
]


class StatisticsService(Singleton):
    def __init__(self):
        if not get_settings().STATS_ENABLED:
            self.enabled = False
            return None
        else:
            self.enabled = True

        # Initialize async database connection
        self.db_path = str(get_settings().STATS_DB_PATH)
        # We'll initialize the database asynchronously when needed
        self._initialized = False
    
    async def _ensure_initialized(self):
        """Ensure the database is initialized asynchronously."""
        if not self._initialized:
            async with aiosqlite.connect(self.db_path) as db:
                for init in INIT:
                    await db.execute(init)
                await db.commit()
            self._initialized = True

    async def add_review(self, repo_name: str) -> None:
        if not self.enabled:
            return None

        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("INSERT OR IGNORE INTO repositories (repo_name) VALUES (?)", (repo_name,))
            await db.execute("UPDATE repositories SET reviews = reviews + 1 WHERE repo_name = ?", (repo_name,))
            await db.commit()
    
    async def get_all_reviews(self) -> dict[str, int]:
        if not self.enabled:
            return {}

        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT repo_name, reviews FROM repositories ORDER BY repo_name ASC") as cursor:
                result = {}
                async for row in cursor:
                    result[row[0]] = row[1]
                return result
    