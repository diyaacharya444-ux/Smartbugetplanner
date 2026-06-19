import os
from datetime import date

from flask import Flask, redirect, url_for
from flask_login import LoginManager, current_user

from models import Category, Theme, User, db
from routes.auth import auth_bp
from routes.main import main_bp


DEFAULT_CATEGORIES = [
    ("Rent", "fa-house", "#2563eb", True),
    ("Groceries", "fa-basket-shopping", "#16a34a", False),
    ("Transport", "fa-car", "#f97316", False),
    ("Utilities", "fa-bolt", "#eab308", True),
    ("Entertainment", "fa-film", "#a855f7", False),
    ("Savings", "fa-piggy-bank", "#0f766e", False),
    ("Emergency Fund", "fa-shield-heart", "#dc2626", False),
    ("Miscellaneous", "fa-wallet", "#64748b", False),
    ("Food", "fa-utensils", "#ef4444", False),
    ("Shopping", "fa-bag-shopping", "#db2777", False),
]


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["UPLOAD_FOLDER"] = os.path.join(app.root_path, "static", "uploads")
    app.config["MAX_CONTENT_LENGTH"] = 8 * 1024 * 1024

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db.init_app(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.context_processor
    def inject_globals():
        theme = "light"
        unread_count = 0
        if current_user.is_authenticated:
            theme_row = Theme.query.filter_by(user_id=current_user.id).first()
            theme = theme_row.name if theme_row else "light"
            from models import Notification

            unread_count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
        return {
            "active_theme": theme,
            "unread_count": unread_count,
            "today": date.today(),
        }

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for("main.dashboard"))
        return redirect(url_for("auth.login"))

    return app


def ensure_user_defaults(user_id):
    if Category.query.filter_by(user_id=user_id).count() == 0:
        for name, icon, color, fixed in DEFAULT_CATEGORIES:
            db.session.add(Category(user_id=user_id, name=name, icon=icon, color=color, is_fixed=fixed))
    if not Theme.query.filter_by(user_id=user_id).first():
        db.session.add(Theme(user_id=user_id, name="light"))
    db.session.commit()


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
