"""Folder-based visibility for read-only users."""

from fastapi import HTTPException
from sqlalchemy import false, select
from sqlalchemy.orm import Session

from .models import Device, EquipmentFolder, User, UserFolderAccess


def is_system_admin(user: User) -> bool:
    return user.username.casefold() == "admin"


def visible_folder_ids(db: Session, user: User | None) -> set[int] | None:
    """Return None for unrestricted users, otherwise the assigned folder subtrees."""
    if user is None or user.role == "admin":
        return None
    roots = set(db.scalars(select(UserFolderAccess.folder_id).where(UserFolderAccess.user_id == user.id)).all())
    visible = set(roots)
    pending = set(roots)
    while pending:
        children = set(db.scalars(select(EquipmentFolder.id).where(EquipmentFolder.parent_id.in_(pending))).all()) - visible
        visible.update(children)
        pending = children
    return visible


def scope_devices(statement, db: Session, user: User | None):
    folder_ids = visible_folder_ids(db, user)
    if folder_ids is None:
        return statement
    return statement.where(Device.folder_id.in_(folder_ids)) if folder_ids else statement.where(false())


def require_visible_device(db: Session, user: User | None, device_id: int) -> Device:
    device = db.scalar(scope_devices(select(Device).where(Device.id == device_id), db, user))
    if not device:
        raise HTTPException(404, "Устройство не найдено")
    return device


def normalize_folder_ids(db: Session, values) -> set[int]:
    if values is None:
        return set()
    if not isinstance(values, list):
        raise ValueError("Выберите разрешённые каталоги")
    try:
        folder_ids = {int(value) for value in values}
    except (TypeError, ValueError) as exc:
        raise ValueError("Выберите корректные каталоги") from exc
    if folder_ids:
        existing = set(db.scalars(select(EquipmentFolder.id).where(EquipmentFolder.id.in_(folder_ids))).all())
        if existing != folder_ids:
            raise ValueError("Один из выбранных каталогов не найден")
    return folder_ids


def replace_user_folders(db: Session, user: User, folder_ids: set[int]) -> None:
    db.query(UserFolderAccess).filter(UserFolderAccess.user_id == user.id).delete(synchronize_session=False)
    if user.role == "viewer":
        db.add_all(UserFolderAccess(user_id=user.id, folder_id=folder_id) for folder_id in sorted(folder_ids))
