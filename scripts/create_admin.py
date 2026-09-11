import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy import select
from app.core.database import Base, engine, SessionLocal
from app.models.entities import User
from app.models import canonical
from app.core.security import hash_password
from app.services.engine import uid

def main():
    Base.metadata.create_all(engine)
    username = 'admin'
    password = 'AdminPassword123!'
    with SessionLocal() as db:
        existing = db.scalar(select(User).where(User.username == username))
        if existing:
            print(f'User "{username}" already exists.')
            return
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
