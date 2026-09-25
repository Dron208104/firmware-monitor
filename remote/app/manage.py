import argparse
import getpass
import os
import shutil
import sqlite3
from pathlib import Path
from sqlalchemy import select

from .auth import hash_password, normalize_username
from .config import settings
from .db import Base, SessionLocal, engine
from .migrations import migrate_sqlite
from .models import User

def _sqlite_path() -> Path:
    prefix = "sqlite:///"
    if not settings.database_url.startswith(prefix):
        raise SystemExit("Команда поддерживается только для SQLite")
    return Path(settings.database_url[len(prefix):]).resolve()

def backup_database(output: str) -> None:
    source = _sqlite_path()
    target = Path(output).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        raise SystemExit("База данных ещё не создана")
    with sqlite3.connect(source) as current, sqlite3.connect(target) as backup:
        current.backup(backup)
    print(f"Резервная копия создана: {target}")

def restore_database(input_path: str) -> None:
    source = Path(input_path).resolve()
    target = _sqlite_path()
    if not source.is_file() or source.read_bytes()[:16] != b"SQLite format 3\x00":
        raise SystemExit("Указанный файл не является корректной базой SQLite")
    target.parent.mkdir(parents=True, exist_ok=True)
    safety_copy = target.with_suffix(target.suffix + ".before-restore")
    if target.exists():
        shutil.copy2(target, safety_copy)
    shutil.copy2(source, target)
    print(f"База восстановлена: {target}")
    if safety_copy.exists():
        print(f"Предыдущая база сохранена: {safety_copy}")

def create_admin(username: str, display_name: str | None = None) -> None:
    password = os.getenv("FIRMWARE_ADMIN_PASSWORD") or getpass.getpass("Пароль администратора: ")
    confirmation = password if os.getenv("FIRMWARE_ADMIN_PASSWORD") else getpass.getpass("Повторите пароль: ")
    if password != confirmation:
        raise SystemExit("Пароли не совпадают")
    Base.metadata.create_all(engine)
    migrate_sqlite(engine)
    with SessionLocal() as db:
        normalized = normalize_username(username)
        if db.scalar(select(User).where(User.username==normalized)):
            raise SystemExit("Пользователь уже существует")
        db.add(User(username=normalized, display_name=(display_name or username).strip(), password_hash=hash_password(password), role="admin", active=True))
        db.commit()
    print(f"Администратор {normalized} создан")

def reset_password(username: str) -> None:
    password = os.getenv("FIRMWARE_ADMIN_PASSWORD") or getpass.getpass("Новый пароль: ")
    confirmation = password if os.getenv("FIRMWARE_ADMIN_PASSWORD") else getpass.getpass("Повторите пароль: ")
    if password != confirmation:
        raise SystemExit("Пароли не совпадают")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username==normalize_username(username)))
        if not user:
            raise SystemExit("Пользователь не найден")
        user.password_hash = hash_password(password)
        for session in user.sessions:
            db.delete(session)
        db.commit()
    print(f"Пароль пользователя {user.username} сброшен")

def main() -> None:
    parser = argparse.ArgumentParser(description="Управление Firmware Monitor")
    sub = parser.add_subparsers(dest="command", required=True)
    command = sub.add_parser("create-admin", help="Создать администратора")
    command.add_argument("--username", required=True)
    command.add_argument("--display-name")
    reset = sub.add_parser("reset-password", help="Сбросить пароль пользователя")
    reset.add_argument("--username", required=True)
    backup = sub.add_parser("backup", help="Создать согласованную резервную копию SQLite")
    backup.add_argument("--output", required=True)
    restore = sub.add_parser("restore", help="Восстановить SQLite из резервной копии (приложение должно быть остановлено)")
    restore.add_argument("--input", required=True)
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.username, args.display_name)
    elif args.command == "reset-password":
        reset_password(args.username)
    elif args.command == "backup":
        backup_database(args.output)
    elif args.command == "restore":
        restore_database(args.input)

if __name__ == "__main__":
    main()
