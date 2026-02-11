from pathlib import Path
import sys

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app import create_app
from app.extensions import db
from app.models import User


@pytest.fixture()
def app(tmp_path: Path):
    db_file = tmp_path / "test.sqlite3"
    app = create_app()
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{db_file}",
        SQLALCHEMY_ENGINE_OPTIONS={},
        WTF_CSRF_ENABLED=False,
    )

    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db_session(app):
    with app.app_context():
        yield db.session


@pytest.fixture()
def admin_user(db_session):
    user = User(
        username="admin1",
        email="admin1@example.com",
        password_hash="hashed-password",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def other_admin_user(db_session):
    user = User(
        username="admin2",
        email="admin2@example.com",
        password_hash="hashed-password",
    )
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture()
def auth_client(client, admin_user):
    with client.session_transaction() as session:
        session["_user_id"] = str(admin_user.id)
        session["_fresh"] = True
    return client
