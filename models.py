from datetime import date, datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Salary(db.Model):
    __tablename__ = "salary"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    salary_date = db.Column(db.Date, nullable=False, default=date.today)
    currency = db.Column(db.String(12), nullable=False, default="INR")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    icon = db.Column(db.String(80), default="fa-wallet")
    color = db.Column(db.String(20), default="#4f46e5")
    is_fixed = db.Column(db.Boolean, default=False)


class BudgetDistribution(db.Model):
    __tablename__ = "budget_distribution"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)
    percentage = db.Column(db.Float, nullable=False, default=0)
    allocated_amount = db.Column(db.Float, nullable=False, default=0)
    category = db.relationship("Category")


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    expense_date = db.Column(db.Date, nullable=False, default=date.today)
    description = db.Column(db.String(255), nullable=False)
    merchant = db.Column(db.String(120))
    source = db.Column(db.String(40), default="manual")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    category = db.relationship("Category")


class FixedExpense(db.Model):
    __tablename__ = "fixed_expenses"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    due_day = db.Column(db.Integer, default=1)
    active = db.Column(db.Boolean, default=True)
    category = db.relationship("Category")


class SavingsGoal(db.Model):
    __tablename__ = "savings_goals"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    target_amount = db.Column(db.Float, nullable=False)
    current_amount = db.Column(db.Float, nullable=False, default=0)
    deadline = db.Column(db.Date)
    notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def percent(self):
        if self.target_amount <= 0:
            return 0
        return min(100, round((self.current_amount / self.target_amount) * 100, 1))

    @property
    def remaining(self):
        return max(0, self.target_amount - self.current_amount)


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    title = db.Column(db.String(160), nullable=False)
    message = db.Column(db.String(255), nullable=False)
    level = db.Column(db.String(20), default="info")
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Rollover(db.Model):
    __tablename__ = "rollovers"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("categories.id"), nullable=False)
    month = db.Column(db.String(7), nullable=False)
    remaining_amount = db.Column(db.Float, nullable=False, default=0)
    preference = db.Column(db.String(40), default="carry_forward")
    processed = db.Column(db.Boolean, default=False)
    category = db.relationship("Category")


class Theme(db.Model):
    __tablename__ = "themes"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, unique=True)
    name = db.Column(db.String(40), default="light")
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
