import os
import tempfile
import uuid
# A unique file-backed database keeps test data isolated while allowing truly
# independent connections in concurrency tests.
_test_db = os.path.join(tempfile.gettempdir(), f'migration_ai_studio_{uuid.uuid4().hex}.db')
os.environ['DATABASE_URL']=f'sqlite:///{_test_db}'
os.environ['JWT_SECRET']='test-secret-that-is-at-least-32-characters-long'
import pytest
from fastapi.testclient import TestClient
from app.core.database import Base, engine, SessionLocal
from app.main import app

@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
    yield

@pytest.fixture
def db():
    s=SessionLocal(); yield s; s.close()

@pytest.fixture
def client(): return TestClient(app)

@pytest.fixture
def auth_headers(client):
    client.post('/api/bootstrap-admin',json={'username':'admin','password':'A-Strong-Test-Password-123!'})
    token=client.post('/api/login',json={'username':'admin','password':'A-Strong-Test-Password-123!'}).json()['access_token']
    return {'Authorization':f'Bearer {token}'}
