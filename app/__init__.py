from flask import Flask

from app.config import Config
from app.extensions import db, login_manager, migrate
from app.models import User
from app.routes import register_routes


def create_app():
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static",
    )
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "login"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    register_routes(app)
    return app


app = create_app()

__all__ = ["app", "db", "migrate", "create_app"]
