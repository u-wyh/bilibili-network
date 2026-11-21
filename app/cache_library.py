import sqlite3
from contextlib import closing
from pathlib import Path


class CacheLibrary:
    def __init__(self, index):
        index.parent.mkdir(parents=True, exist_ok=True)
        self.index = index
        with closing(sqlite3.connect(index)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS cache (
                path TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")

    def add(self, path, title):
        path = Path(path).resolve(strict=True)
        if path.suffix.lower() != ".mp4" or not path.is_file():
            raise OSError("缓存文件不可用。")
        with closing(sqlite3.connect(self.index)) as db, db:
            db.execute(
                "INSERT INTO cache(path, title) VALUES (?, ?) "
                "ON CONFLICT(path) DO UPDATE SET title = excluded.title",
                (str(path), title),
            )
        return path

    def entries(self):
        with closing(sqlite3.connect(self.index)) as db:
            rows = db.execute("SELECT path, title FROM cache ORDER BY added_at DESC, rowid DESC").fetchall()
        return [(Path(path), title) for path, title in rows if Path(path).is_file()]

    def remove(self, path):
        path = Path(path)
        with closing(sqlite3.connect(self.index)) as db, db:
            if not db.execute("SELECT 1 FROM cache WHERE path = ?", (str(path),)).fetchone():
                raise OSError("这不是本应用管理的缓存。")
            if path.is_symlink() or path.resolve() != path:
                raise OSError("缓存路径已变更，请在文件夹中检查。")
            path.unlink(missing_ok=True)
            db.execute("DELETE FROM cache WHERE path = ?", (str(path),))
