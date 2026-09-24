import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy import select
from app.core.database import Base, engine, SessionLocal
from app.models.entities import User
from app.models import canonical  # noqa: F401 - ensure canonical models are registered
from app.core.security import hash_password
from app.services.engine import uid


def read_password_windows(prompt: str) -> str:
    """Read a password on Windows while displaying * for each character."""
    try:
        import msvcrt
    except ImportError:
        import getpass
        return getpass.getpass(prompt)

    sys.stdout.write(prompt)
    sys.stdout.flush()
    chars = []
    while True:
        ch = msvcrt.getwch()
        if ch in ('\r', '\n'):
            sys.stdout.write('\n')
            sys.stdout.flush()
            return ''.join(chars)
        if ch == '\003':  # Ctrl+C
            raise KeyboardInterrupt
        if ch == '\b':
            if chars:
                chars.pop()
                sys.stdout.write('\b \b')
                sys.stdout.flush()
            continue
        if ch in ('\x00', '\xe0'):
            msvcrt.getwch()  # consume special-key suffix
            continue
        chars.append(ch)
        sys.stdout.write('*')
        sys.stdout.flush()


def main() -> None:
    Base.metadata.create_all(engine)

    username = input('Admin username [admin]: ').strip() or 'admin'
    password = read_password_windows('Admin password: ')
    confirm = read_password_windows('Confirm password: ')

    if password != confirm:
        raise SystemExit('Passwords do not match. Please run the script again.')
    if len(password) < 12:
        raise SystemExit(
            f'Password must contain at least 12 characters. '
            f'The script received {len(password)} character(s).'
        )

    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username == username))
        if existing:
            raise SystemExit(
                f'User "{username}" already exists. Choose a different username '
                'or use the existing account.'
            )
        db.add(
            User(
                id=uid('USR'),
                username=username,
                password_hash=hash_password(password),
                role='ADMIN',
            )
        )
        db.commit()

    print(f'Admin created successfully: {username}')


if __name__ == '__main__':
    main()
