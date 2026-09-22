import argparse
import getpass
import os
from sqlalchemy import select

from .auth import hash_password, normalize_username
from .db import Base, SessionLocal, engine
from .migrations import migrate_sqlite
from .models import User

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
    args = parser.parse_args()
    if args.command == "create-admin":
        create_admin(args.username, args.display_name)
    elif args.command == "reset-password":
        reset_password(args.username)

if __name__ == "__main__":
    main()
