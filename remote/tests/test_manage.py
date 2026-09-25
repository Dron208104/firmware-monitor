import sqlite3
import shutil
import uuid
from pathlib import Path

from app import manage


def local_temp():
    path = Path(__file__).parent / ".tmp-manage" / uuid.uuid4().hex
    path.mkdir(parents=True)
    return path


def test_sqlite_backup_and_restore(monkeypatch):
    directory = local_temp()
    try:
        database = directory / "working.db"
        backup = directory / "backup.db"
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE sample(value TEXT)")
            connection.execute("INSERT INTO sample VALUES ('before')")
        monkeypatch.setattr(manage.settings, "database_url", f"sqlite:///{database}")
        manage.backup_database(str(backup))
        with sqlite3.connect(database) as connection:
            connection.execute("UPDATE sample SET value='after'")
        manage.restore_database(str(backup))
        with sqlite3.connect(database) as connection:
            assert connection.execute("SELECT value FROM sample").fetchone()[0] == "before"
        assert database.with_suffix(".db.before-restore").exists()
    finally:
        shutil.rmtree(directory, ignore_errors=True)


def test_restore_rejects_non_sqlite_file(monkeypatch):
    directory = local_temp()
    try:
        database = directory / "working.db"
        invalid = directory / "invalid.db"
        invalid.write_text("not a database", encoding="utf-8")
        monkeypatch.setattr(manage.settings, "database_url", f"sqlite:///{database}")
        try:
            manage.restore_database(str(invalid))
        except SystemExit as exc:
            assert "корректной базой SQLite" in str(exc)
        else:
            raise AssertionError("Некорректная база должна быть отклонена")
    finally:
        shutil.rmtree(directory, ignore_errors=True)
