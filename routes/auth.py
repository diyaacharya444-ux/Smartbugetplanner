from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user

from models import User, db

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or len(password) < 6:
            flash("Enter a name, email, and password of at least 6 characters.", "danger")
            return render_template("auth/register.html")
        if User.query.filter_by(email=email).first():
            flash("An account already exists for that email.", "danger")
            return render_template("auth/register.html")
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        from app import ensure_user_defaults

        ensure_user_defaults(user.id)
        login_user(user)
        flash("Account created. Add your salary to start planning.", "success")
        return redirect(url_for("main.salary"))
    return render_template("auth/register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if not user or not user.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html")
        from app import ensure_user_defaults

        ensure_user_defaults(user.id)
        login_user(user)
        return redirect(url_for("main.dashboard"))
    return render_template("auth/login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for("auth.login"))
