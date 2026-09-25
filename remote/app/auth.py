import hashlib
import secrets
from collections import OrderedDict, deque
from datetime import datetime, timedelta, timezone
from threading import Lock

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import AdminAuditLog, User, UserSession

SESSION_COOKIE = "firmware_session"
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
_dummy_password_hash = _hasher.hash(secrets.token_urlsafe(32))
_attempts: OrderedDict[str, deque[datetime]] = OrderedDict()
_attempts_lock = Lock()
_max_attempt_keys = 10_000

def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def normalize_username(value: str) -> str:
    return value.strip().lower()

def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("Пароль должен содержать не менее 8 символов")
    return _hasher.hash(password)

def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False

def verify_user_credentials(user: User | None, password: str) -> bool:
    """Perform one Argon2 verification even when the account is absent or blocked."""
    password_hash = user.password_hash if user and user.active else _dummy_password_hash
    valid = verify_password(password_hash, password)
    return bool(user and user.active and valid)

def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def create_session(db: Session, user: User) -> str:
    raw = secrets.token_urlsafe(48)
    current=utcnow()
    db.add(UserSession(user_id=user.id, token_hash=token_hash(raw), last_seen_at=current, expires_at=current+timedelta(hours=settings.session_lifetime_hours)))
    user.last_login_at = utcnow()
    db.commit()
    return raw

def session_user(db: Session, raw: str | None) -> User | None:
    if not raw:
        return None
    session = db.scalar(select(UserSession).where(UserSession.token_hash==token_hash(raw), UserSession.revoked_at.is_(None)))
    if not session:
        return None
    current=utcnow()
    expires=session.expires_at.replace(tzinfo=session.expires_at.tzinfo or timezone.utc)
    last_seen=(session.last_seen_at or session.created_at).replace(tzinfo=(session.last_seen_at or session.created_at).tzinfo or timezone.utc)
    if expires<=current or last_seen+timedelta(minutes=settings.session_inactivity_minutes)<=current:
        session.revoked_at=current;db.commit();return None
    user = db.get(User, session.user_id)
    if not user or not user.active:
        return None
    session.last_seen_at=current;db.commit();return user

def revoke_session(db: Session, raw: str | None) -> None:
    if raw:
        session = db.scalar(select(UserSession).where(UserSession.token_hash==token_hash(raw), UserSession.revoked_at.is_(None)))
        if session:
            session.revoked_at = utcnow()
            db.commit()

def rate_key(ip: str, username: str) -> str:
    return f"{ip}:{normalize_username(username)}"

def login_allowed(key: str) -> bool:
    cutoff = utcnow()-timedelta(minutes=15)
    with _attempts_lock:
        attempts = _attempts.get(key)
        if attempts is None:
            return True
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if not attempts:
            _attempts.pop(key, None)
            return True
        _attempts.move_to_end(key)
        return len(attempts) < 5

def record_login_failure(key: str) -> None:
    with _attempts_lock:
        attempts = _attempts.get(key)
        if attempts is None:
            if len(_attempts) >= _max_attempt_keys:
                _attempts.popitem(last=False)
            attempts = deque()
            _attempts[key] = attempts
        attempts.append(utcnow())
        _attempts.move_to_end(key)

def clear_login_failures(key: str) -> None:
    with _attempts_lock:
        _attempts.pop(key, None)

def active_admin_count(db: Session) -> int:
    return db.scalar(select(func.count(User.id)).where(User.role=="admin", User.active.is_(True))) or 0

def audit(db: Session, actor: User | None, action: str, target: str, details: str | None = None) -> None:
    db.add(AdminAuditLog(actor_user_id=actor.id if actor else None, action=action, target=target, details=details))

def create_initial_admin(db: Session) -> bool:
    if not settings.initial_admin_username or not settings.initial_admin_password or db.scalar(select(func.count(User.id))):
        return False
    db.add(User(username=normalize_username(settings.initial_admin_username), display_name=settings.initial_admin_username.strip(), password_hash=hash_password(settings.initial_admin_password), role="admin", active=True))
    db.commit()
    return True
