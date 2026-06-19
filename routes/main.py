import csv
import io
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import (
    Blueprint,
    Response,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required
from sqlalchemy import extract, func
from werkzeug.utils import secure_filename

from models import (
    BudgetDistribution,
    Category,
    Expense,
    FixedExpense,
    Notification,
    Rollover,
    Salary,
    SavingsGoal,
    Theme,
    User,
    db,
)

main_bp = Blueprint("main", __name__)


def month_key(value=None):
    value = value or date.today()
    return value.strftime("%Y-%m")


def parse_date(value, fallback=None):
    if not value:
        return fallback or date.today()
    return datetime.strptime(value, "%Y-%m-%d").date()


def money(value):
    return round(float(value or 0), 2)


def latest_salary():
    return Salary.query.filter_by(user_id=current_user.id).order_by(Salary.salary_date.desc()).first()


def salary_for_month(month=None):
    month = month or month_key()
    return (
        Salary.query.filter_by(user_id=current_user.id)
        .filter(func.strftime("%Y-%m", Salary.salary_date) == month)
        .order_by(Salary.salary_date.desc())
        .first()
    )


def currency_symbol(code):
    return {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "NPR": "रू"}.get(code or "INR", code or "₹")


def user_categories():
    return Category.query.filter_by(user_id=current_user.id).order_by(Category.name.asc()).all()


def get_or_create_category(name, icon="fa-wallet", color="#64748b"):
    category = Category.query.filter(
        Category.user_id == current_user.id,
        func.lower(Category.name) == name.lower(),
    ).first()
    if category:
        return category
    category = Category(user_id=current_user.id, name=name.title(), icon=icon, color=color)
    db.session.add(category)
    db.session.commit()
    return category


def rebuild_budget(month=None):
    month = month or month_key()
    salary = salary_for_month(month) or latest_salary()
    if not salary:
        return []
    rows = BudgetDistribution.query.filter_by(user_id=current_user.id, month=month).all()
    if not rows:
        defaults = {
            "Rent": 30,
            "Groceries": 20,
            "Transport": 10,
            "Utilities": 10,
            "Entertainment": 5,
            "Savings": 15,
            "Emergency Fund": 5,
            "Miscellaneous": 5,
        }
        for category in user_categories():
            pct = defaults.get(category.name, 0)
            row = BudgetDistribution(
                user_id=current_user.id,
                category_id=category.id,
                month=month,
                percentage=pct,
            )
            db.session.add(row)
            rows.append(row)
    for row in rows:
        row.allocated_amount = money(salary.amount * row.percentage / 100)
    db.session.commit()
    return rows


def expenses_for_month(month=None):
    month = month or month_key()
    return (
        Expense.query.filter_by(user_id=current_user.id)
        .filter(func.strftime("%Y-%m", Expense.expense_date) == month)
        .order_by(Expense.expense_date.desc(), Expense.id.desc())
        .all()
    )


def apply_fixed_expenses(month=None):
    month = month or month_key()
    fixed_rows = FixedExpense.query.filter_by(user_id=current_user.id, active=True).all()
    if not fixed_rows:
        return
    year, mon = [int(part) for part in month.split("-")]
    for fixed in fixed_rows:
        due_day = min(max(fixed.due_day or 1, 1), 28)
        expense_date = date(year, mon, due_day)
        exists = Expense.query.filter_by(
            user_id=current_user.id,
            source=f"fixed:{fixed.id}",
            expense_date=expense_date,
        ).first()
        if not exists:
            db.session.add(
                Expense(
                    user_id=current_user.id,
                    category_id=fixed.category_id,
                    amount=fixed.amount,
                    expense_date=expense_date,
                    description=fixed.name,
                    merchant=fixed.name,
                    source=f"fixed:{fixed.id}",
                )
            )
    db.session.commit()


def dashboard_metrics(month=None):
    month = month or month_key()
    apply_fixed_expenses(month)
    distributions = rebuild_budget(month)
    expenses = expenses_for_month(month)
    salary = salary_for_month(month) or latest_salary()
    total_income = money(salary.amount if salary else 0)
    total_expenses = money(sum(e.amount for e in expenses))
    savings_allocated = money(sum(d.allocated_amount for d in distributions if d.category.name in ("Savings", "Emergency Fund")))
    spent_by_category = defaultdict(float)
    for expense in expenses:
        spent_by_category[expense.category_id] += expense.amount
    allocation_cards = []
    for row in distributions:
        spent = money(spent_by_category[row.category_id])
        remaining = money(row.allocated_amount - spent)
        used_percent = round((spent / row.allocated_amount) * 100, 1) if row.allocated_amount else 0
        allocation_cards.append(
            {
                "row": row,
                "spent": spent,
                "remaining": remaining,
                "used_percent": min(999, used_percent),
            }
        )
    return {
        "month": month,
        "salary": salary,
        "symbol": currency_symbol(salary.currency if salary else "INR"),
        "total_income": total_income,
        "total_expenses": total_expenses,
        "remaining_balance": money(total_income - total_expenses),
        "savings": savings_allocated,
        "expenses": expenses,
        "distributions": distributions,
        "allocation_cards": allocation_cards,
    }


def sync_notifications(month=None):
    month = month or month_key()
    data = dashboard_metrics(month)
    if not salary_for_month(month):
        add_notification("Salary missing", "Salary has not been entered for this month.", "warning")
    for card in data["allocation_cards"]:
        row = card["row"]
        if row.allocated_amount <= 0:
            continue
        if card["used_percent"] >= 100:
            add_notification("Budget exceeded", f"{row.category.name} budget exceeded.", "danger")
        elif card["used_percent"] >= 80:
            add_notification("Budget warning", f"{row.category.name} budget is {card['used_percent']}% used.", "warning")
    for goal in SavingsGoal.query.filter_by(user_id=current_user.id).all():
        if goal.deadline and goal.deadline < date.today() and goal.current_amount < goal.target_amount:
            add_notification("Savings target missed", f"{goal.name} is past the deadline with {currency_symbol(data['salary'].currency if data['salary'] else 'INR')}{goal.remaining:,.0f} remaining.", "warning")


def add_notification(title, message, level="info"):
    exists = Notification.query.filter_by(user_id=current_user.id, title=title, message=message, is_read=False).first()
    if not exists:
        db.session.add(Notification(user_id=current_user.id, title=title, message=message, level=level))
        db.session.commit()


def suggest_category(text):
    lowered = text.lower()
    rules = {
        "Food": ["restaurant", "cafe", "lunch", "dinner", "pizza", "burger", "kfc"],
        "Transport": ["uber", "ola", "taxi", "fuel", "petrol", "metro", "bus"],
        "Utilities": ["electricity", "internet", "water", "gas", "bill", "utility"],
        "Shopping": ["amazon", "flipkart", "mall", "store", "market"],
        "Groceries": ["grocery", "supermarket", "mart", "vegetable"],
    }
    for category, terms in rules.items():
        if any(term in lowered for term in terms):
            return category
    return "Miscellaneous"


def extract_receipt_data(path):
    text = ""
    try:
        import cv2
        import pytesseract

        image = cv2.imread(path)
        if image is not None:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            text = pytesseract.image_to_string(gray)
    except Exception as exc:
        text = f"OCR unavailable: {exc}"

    amounts = [float(match.replace(",", "")) for match in re.findall(r"(?:₹|rs\.?|inr|\$)?\s*(\d{1,6}(?:,\d{3})*(?:\.\d{1,2})?)", text, re.I)]
    amount = max(amounts) if amounts else 0
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    merchant = lines[0][:120] if lines and not lines[0].lower().startswith("ocr unavailable") else "Unknown merchant"
    return {
        "text": text,
        "amount": amount,
        "merchant": merchant,
        "category": suggest_category(text),
    }


@main_bp.route("/dashboard")
@login_required
def dashboard():
    sync_notifications()
    data = dashboard_metrics()
    goals = SavingsGoal.query.filter_by(user_id=current_user.id).order_by(SavingsGoal.deadline.asc()).limit(3).all()
    notifications = Notification.query.filter_by(user_id=current_user.id).order_by(Notification.created_at.desc()).limit(5).all()
    return render_template("dashboard.html", **data, goals=goals, notifications=notifications)


@main_bp.route("/salary", methods=["GET", "POST"])
@login_required
def salary():
    if request.method == "POST":
        row = Salary(
            user_id=current_user.id,
            amount=money(request.form.get("amount")),
            salary_date=parse_date(request.form.get("salary_date")),
            currency=request.form.get("currency", "INR"),
        )
        db.session.add(row)
        db.session.commit()
        rebuild_budget(month_key(row.salary_date))
        flash("Salary saved and budget allocations recalculated.", "success")
        return redirect(url_for("main.budget"))
    salaries = Salary.query.filter_by(user_id=current_user.id).order_by(Salary.salary_date.desc()).all()
    return render_template("salary.html", salaries=salaries)


@main_bp.route("/budget", methods=["GET", "POST"])
@login_required
def budget():
    month = request.values.get("month") or month_key()
    categories = user_categories()
    salary = salary_for_month(month) or latest_salary()
    if request.method == "POST":
        for category in categories:
            pct = money(request.form.get(f"pct_{category.id}", 0))
            row = BudgetDistribution.query.filter_by(user_id=current_user.id, category_id=category.id, month=month).first()
            if not row:
                row = BudgetDistribution(user_id=current_user.id, category_id=category.id, month=month)
                db.session.add(row)
            row.percentage = pct
            row.allocated_amount = money((salary.amount if salary else 0) * pct / 100)
        db.session.commit()
        flash("Budget distribution updated.", "success")
        return redirect(url_for("main.budget", month=month))
    rows = rebuild_budget(month)
    total_pct = sum(row.percentage for row in rows)
    return render_template("budget.html", rows=rows, salary=salary, month=month, total_pct=total_pct, symbol=currency_symbol(salary.currency if salary else "INR"))


@main_bp.route("/expenses", methods=["GET", "POST"])
@login_required
def expenses():
    if request.method == "POST":
        category = Category.query.get(int(request.form.get("category_id")))
        if not category or category.user_id != current_user.id:
            flash("Choose a valid category.", "danger")
            return redirect(url_for("main.expenses"))
        expense = Expense(
            user_id=current_user.id,
            amount=money(request.form.get("amount")),
            category_id=category.id,
            expense_date=parse_date(request.form.get("expense_date")),
            description=request.form.get("description", "").strip() or category.name,
            merchant=request.form.get("merchant", "").strip(),
        )
        db.session.add(expense)
        db.session.commit()
        flash("Expense added.", "success")
        return redirect(url_for("main.expenses"))
    rows = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.expense_date.desc(), Expense.id.desc()).limit(100).all()
    return render_template("expenses.html", categories=user_categories(), expenses=rows)


@main_bp.route("/fixed", methods=["GET", "POST"])
@login_required
def fixed():
    if request.method == "POST":
        fixed_id = request.form.get("fixed_id")
        row = FixedExpense.query.filter_by(id=fixed_id, user_id=current_user.id).first() if fixed_id else FixedExpense(user_id=current_user.id)
        row.name = request.form.get("name", "").strip()
        row.amount = money(request.form.get("amount"))
        row.category_id = int(request.form.get("category_id"))
        row.due_day = int(request.form.get("due_day") or 1)
        row.active = bool(request.form.get("active", "1"))
        if not fixed_id:
            db.session.add(row)
        category = Category.query.get(row.category_id)
        if category and category.user_id == current_user.id:
            category.is_fixed = True
        db.session.commit()
        flash("Fixed category saved.", "success")
        return redirect(url_for("main.fixed"))
    rows = FixedExpense.query.filter_by(user_id=current_user.id).order_by(FixedExpense.name.asc()).all()
    return render_template("fixed.html", rows=rows, categories=user_categories())


@main_bp.route("/fixed/<int:fixed_id>/delete", methods=["POST"])
@login_required
def delete_fixed(fixed_id):
    row = FixedExpense.query.filter_by(id=fixed_id, user_id=current_user.id).first_or_404()
    db.session.delete(row)
    db.session.commit()
    flash("Fixed category deleted.", "info")
    return redirect(url_for("main.fixed"))


@main_bp.route("/goals", methods=["GET", "POST"])
@login_required
def goals():
    if request.method == "POST":
        goal_id = request.form.get("goal_id")
        goal = SavingsGoal.query.filter_by(id=goal_id, user_id=current_user.id).first() if goal_id else SavingsGoal(user_id=current_user.id)
        goal.name = request.form.get("name", "").strip()
        goal.target_amount = money(request.form.get("target_amount"))
        goal.current_amount = money(request.form.get("current_amount"))
        goal.deadline = parse_date(request.form.get("deadline"), None) if request.form.get("deadline") else None
        goal.notes = request.form.get("notes", "").strip()
        if not goal_id:
            db.session.add(goal)
        db.session.commit()
        flash("Savings goal saved.", "success")
        return redirect(url_for("main.goals"))
    rows = SavingsGoal.query.filter_by(user_id=current_user.id).order_by(SavingsGoal.deadline.asc()).all()
    return render_template("goals.html", goals=rows, symbol=currency_symbol((latest_salary() or Salary(currency="INR")).currency))


@main_bp.route("/goals/<int:goal_id>/delete", methods=["POST"])
@login_required
def delete_goal(goal_id):
    row = SavingsGoal.query.filter_by(id=goal_id, user_id=current_user.id).first_or_404()
    db.session.delete(row)
    db.session.commit()
    flash("Goal deleted.", "info")
    return redirect(url_for("main.goals"))


@main_bp.route("/scanner", methods=["GET", "POST"])
@login_required
def scanner():
    extracted = None
    if request.method == "POST" and "receipt" in request.files:
        file = request.files["receipt"]
        if file and file.filename:
            filename = secure_filename(file.filename)
            path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
            file.save(path)
            extracted = extract_receipt_data(path)
            extracted["filename"] = filename
    elif request.method == "POST":
        category = get_or_create_category(request.form.get("category", "Miscellaneous"))
        expense = Expense(
            user_id=current_user.id,
            amount=money(request.form.get("amount")),
            category_id=category.id,
            expense_date=parse_date(request.form.get("expense_date")),
            description=request.form.get("description", "Scanned receipt"),
            merchant=request.form.get("merchant", ""),
            source="ocr",
        )
        db.session.add(expense)
        db.session.commit()
        flash("Scanned expense saved.", "success")
        return redirect(url_for("main.expenses"))
    return render_template("scanner.html", extracted=extracted, categories=user_categories())


@main_bp.route("/transactions")
@login_required
def transactions():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category_id")
    sort = request.args.get("sort", "date_desc")
    query = Expense.query.filter_by(user_id=current_user.id)
    if q:
        query = query.filter(Expense.description.ilike(f"%{q}%") | Expense.merchant.ilike(f"%{q}%"))
    if category_id:
        query = query.filter_by(category_id=int(category_id))
    if sort == "amount_asc":
        query = query.order_by(Expense.amount.asc())
    elif sort == "amount_desc":
        query = query.order_by(Expense.amount.desc())
    else:
        query = query.order_by(Expense.expense_date.desc(), Expense.id.desc())
    rows = query.all()
    return render_template("transactions.html", rows=rows, categories=user_categories(), q=q, category_id=category_id, sort=sort)


@main_bp.route("/transactions/export/<fmt>")
@login_required
def export_transactions(fmt):
    rows = Expense.query.filter_by(user_id=current_user.id).order_by(Expense.expense_date.desc()).all()
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Description", "Category", "Type", "Amount"])
        for row in rows:
            writer.writerow([row.expense_date, row.description, row.category.name, "Expense", row.amount])
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=transactions.csv"})
    return simple_pdf("transactions.pdf", "Transactions", [[str(r.expense_date), r.description, r.category.name, f"{r.amount:.2f}"] for r in rows])


def simple_pdf(filename, title, rows):
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas

        buffer = io.BytesIO()
        pdf = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        y = height - 50
        pdf.setFont("Helvetica-Bold", 16)
        pdf.drawString(40, y, title)
        pdf.setFont("Helvetica", 10)
        y -= 30
        for row in rows:
            pdf.drawString(40, y, " | ".join(str(item) for item in row)[:110])
            y -= 18
            if y < 50:
                pdf.showPage()
                y = height - 50
                pdf.setFont("Helvetica", 10)
        pdf.save()
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype="application/pdf")
    except Exception:
        text = title + "\n\n" + "\n".join(" | ".join(str(item) for item in row) for row in rows)
        return Response(text, mimetype="text/plain", headers={"Content-Disposition": f"attachment; filename={filename}.txt"})


@main_bp.route("/reports")
@login_required
def reports():
    year = int(request.args.get("year", date.today().year))
    monthly = []
    for mon in range(1, 13):
        expenses = (
            Expense.query.filter_by(user_id=current_user.id)
            .filter(extract("year", Expense.expense_date) == year, extract("month", Expense.expense_date) == mon)
            .all()
        )
        salaries = (
            Salary.query.filter_by(user_id=current_user.id)
            .filter(extract("year", Salary.salary_date) == year, extract("month", Salary.salary_date) == mon)
            .all()
        )
        monthly.append({"month": f"{year}-{mon:02d}", "income": sum(s.amount for s in salaries), "expenses": sum(e.amount for e in expenses)})
    goals_rows = SavingsGoal.query.filter_by(user_id=current_user.id).all()
    return render_template("reports.html", monthly=monthly, goals=goals_rows, year=year)


@main_bp.route("/reports/export/<fmt>")
@login_required
def export_reports(fmt):
    data = dashboard_metrics()
    rows = [["Total income", data["total_income"]], ["Total expenses", data["total_expenses"]], ["Remaining balance", data["remaining_balance"]], ["Savings allocation", data["savings"]]]
    if fmt == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Metric", "Amount"])
        writer.writerows(rows)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": "attachment; filename=report.csv"})
    return simple_pdf("report.pdf", "Budget Report", rows)


@main_bp.route("/rollovers", methods=["GET", "POST"])
@login_required
def rollovers():
    month = request.values.get("month") or month_key()
    data = dashboard_metrics(month)
    if request.method == "POST":
        for card in data["allocation_cards"]:
            pref = request.form.get(f"pref_{card['row'].category_id}", "ignore")
            row = Rollover.query.filter_by(user_id=current_user.id, category_id=card["row"].category_id, month=month).first()
            if not row:
                row = Rollover(user_id=current_user.id, category_id=card["row"].category_id, month=month)
                db.session.add(row)
            row.remaining_amount = max(0, card["remaining"])
            row.preference = pref
            row.processed = pref != "ignore"
        db.session.commit()
        flash("Rollover preferences saved.", "success")
        return redirect(url_for("main.rollovers", month=month))
    existing = {r.category_id: r for r in Rollover.query.filter_by(user_id=current_user.id, month=month).all()}
    return render_template("rollovers.html", cards=data["allocation_cards"], month=month, existing=existing, symbol=data["symbol"])


@main_bp.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    theme = Theme.query.filter_by(user_id=current_user.id).first()
    if request.method == "POST":
        if not theme:
            theme = Theme(user_id=current_user.id)
            db.session.add(theme)
        theme.name = request.form.get("theme", "light")
        db.session.commit()
        flash("Theme preference saved.", "success")
        return redirect(url_for("main.settings"))
    return render_template("settings.html", theme=theme.name if theme else "light")


@main_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        current_user.name = request.form.get("name", current_user.name).strip()
        password = request.form.get("password", "")
        if password:
            current_user.set_password(password)
        db.session.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("main.profile"))
    return render_template("profile.html")


@main_bp.route("/notifications/read", methods=["POST"])
@login_required
def mark_notifications_read():
    Notification.query.filter_by(user_id=current_user.id, is_read=False).update({"is_read": True})
    db.session.commit()
    return redirect(request.referrer or url_for("main.dashboard"))


@main_bp.route("/api/charts")
@login_required
def charts():
    data = dashboard_metrics()
    by_category = defaultdict(float)
    for expense in data["expenses"]:
        by_category[expense.category.name] += expense.amount
    months = []
    income = []
    expenses = []
    savings_growth = []
    running_saved = 0
    base = date.today().replace(day=1)
    for offset in range(5, -1, -1):
        month_date = (base - timedelta(days=offset * 31)).replace(day=1)
        key = month_key(month_date)
        months.append(key)
        month_salary = salary_for_month(key)
        month_expenses = expenses_for_month(key)
        inc = money(month_salary.amount if month_salary else 0)
        exp = money(sum(e.amount for e in month_expenses))
        income.append(inc)
        expenses.append(exp)
        running_saved += max(0, inc - exp)
        savings_growth.append(money(running_saved))
    return jsonify(
        {
            "expensePie": {"labels": list(by_category.keys()), "values": [money(v) for v in by_category.values()]},
            "incomeExpense": {"labels": months, "income": income, "expenses": expenses},
            "monthlyTrend": {"labels": months, "values": expenses},
            "savingsGrowth": {"labels": months, "values": savings_growth},
        }
    )
