import os
import sys
import subprocess
from datetime import datetime
from decimal import Decimal
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from flask import Flask, request, jsonify, render_template, send_from_directory, abort
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, CheckConstraint, cast

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

# Basic database configurations
# We set the URI for the database to 'pocketmoney.db' in the directory that hosts this file.
basedir = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(basedir, "database.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# SQLite database models
class Budget(db.Model):
    # A budget is a total carved up into categories
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(50), unique=True, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    __table_args__ = (
        CheckConstraint('amount >= 0', name='check_amount_non_negative'),
        CheckConstraint('length(category) <= 50', name='check_category_length'),
    )

class Purchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=False, nullable=False)
    category = db.Column(db.String(50), unique=False, nullable=False)
    amount = db.Column(db.Numeric(10, 2), nullable=False)

    __table_args__ = (
        CheckConstraint('amount >= 0', name='check_purchase_amount_non_negative'),
        CheckConstraint('length(name) <= 50', name='check_name_length'),
        CheckConstraint('length(category) <= 50', name='check_purchase_category_length'),
    )


# Visualization
def visualize_budgets(budgets, spending):
    categories = list(budgets.keys())
    budget_values = [budgets[cat] for cat in categories]
    spending_values = [spending.get(cat, 0) for cat in categories]
    spent_within = []
    remaining = []
    overspent = []

    for i in range(len(categories)):
        budget = budget_values[i]
        spent = spending_values[i]
        if spent <= budget:
            spent_within.append(spent)
            remaining.append(budget - spent)
            overspent.append(0)
        else:
            spent_within.append(budget)
            remaining.append(0)
            overspent.append(spent - budget)

    x = range(len(categories))
    plt.figure(figsize=(10,6))
    plt.bar(x, spent_within, label='Spent Within Budget', color='lightgreen')
    plt.bar(x, remaining, bottom=spent_within, label='Remaining Budget', color='grey')
    plt.bar(x, overspent, bottom=[spent_within[i] + remaining [i] for i in range(len(categories))], label='Overspent', color='maroon')

    for i in range(len(categories)):
        if spent_within[i] > 0:
            plt.text(x[i], spent_within[i]/2, f"${spending_values[i]:.2f}" if overspent[i] == 0 else f"${budget_values[i]:.2f}", ha='center', va='center', fontsize=9, color='white')
        if remaining[i] > 0:
            plt.text(x[i], spent_within[i] + remaining[i]/2, f"${remaining[i]:.2f}", ha='center', va='center', fontsize=9)
        if overspent[i] > 0:
            plt.text(x[i], spent_within[i] + overspent[i]/2, f"+${overspent[i]:.2f}", ha='center', va='center', fontsize=9, color='red')

    plt.xticks(x, categories, rotation=45)
    plt.xlabel('Categories')
    plt.ylabel('Amount')
    plt.title('Budget vs Spending')
    plt.legend()
    plt.tight_layout()

    dir = "charts"
    os.makedirs(dir, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    file_name = f"{now}.png"
    path = os.path.join(dir, file_name)
    plt.savefig(path, dpi=300, bbox_inches='tight')
    plt.close()

    return path

def validate_amount(amount):
    """Validate monetary amount: non-negative, max 2 decimals, max 999999.99"""
    try:
        amt = Decimal(str(amount))
        if amt < 0 or amt > Decimal('999999.99'):
            return False
        # Check exactly 2 decimal places
        if amt != amt.quantize(Decimal('0.01')):
            return False
        return True
    except:
        return False

def validate_category_name(text):
    """Validate category/name: alphanumeric, spaces, max 50 chars"""
    if not isinstance(text, str) or len(text) > 50 or len(text) == 0:
        return False
    return bool(re.match(r'^[a-zA-Z0-9\s]+$', text))

# WEB APPLICATION ROUTES
@app.route('/')
def hello_world():
    return render_template("index.html")

@app.route("/api/logpurchase", methods=['POST'])
def logpurchase():
    '''
    Users can add a purchased item to their monthly budget.
    '''
    try:
        data = request.get_json()
        if not data:
            return jsonify({"message": "Invalid JSON"}), 400

        name = data.get('name')
        category = data.get('category')
        amount = data.get('amount')

        if not all([name, category, amount is not None]):
            return jsonify({"message": "Missing required fields"}), 400

        if not validate_category_name(name) or not validate_category_name(category):
            return jsonify({"message": "Invalid name or category format"}), 400

        if not validate_amount(amount):
            return jsonify({"message": "Invalid amount: must be non-negative, max 2 decimals, max 999999.99"}), 400

        if Budget.query.filter_by(category=category).first():
            # the category we are trying to add the purchase to exists
            purchase = Purchase(
                name=name,
                category=category,
                amount=Decimal(str(amount))
            )

            db.session.add(purchase)
            db.session.commit()

            return jsonify({"message": "Purchase successfully logged!"}), 201
        else:
            # the category doesn't exist
            return jsonify({"message": "Purchase log failed due to nonexistent category"}), 404
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "Internal server error"}), 500

@app.route("/api/setbudget", methods=["PUT"])
def setbudget():
    '''
    Users can create or update their monthly budget.
    '''
    try:
        data = request.get_json()
        if not data:
            return jsonify({"message": "Invalid JSON"}), 400

        category = data.get('category')
        amount = data.get('amount')

        if not category or amount is None:
            return jsonify({"message": "Missing required fields"}), 400

        if not validate_category_name(category):
            return jsonify({"message": "Invalid category format"}), 400

        if not validate_amount(amount):
            return jsonify({"message": "Invalid amount: must be non-negative, max 2 decimals, max 999999.99"}), 400

        budget = Budget.query.filter_by(category=category).first()

        if budget:
            budget.amount = Decimal(str(amount))
        else:
            budget = Budget(
                category=category,
                amount=Decimal(str(amount))
            )
            db.session.add(budget)

        db.session.commit()

        return jsonify({"message": "Budget set successfully!"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "Internal server error"}), 500

@app.route("/api/viewbudget", methods=['GET'])
def viewbudget():
    '''
    Users can view their monthly budget, including all categories past purchases made, as well as
    how much money they have left for the month. It also generates a graph showing 1) their past
    monthly spending trends and 2) their spending trends in the current month and 3) their spending
    by category (pie chart).
    '''
    budgets = Budget.query.all()
    purchases = Purchase.query.all()

    spent = db.session.query(
        Purchase.category,
        func.sum(Purchase.amount)
    ).group_by(Purchase.category).all()

    spent_dict = {c: a if a is not None else Decimal('0.00') for c, a in spent}

    result = []

    for b in budgets:
        used = spent_dict.get(b.category, Decimal('0.00'))
        remaining = b.amount - used

        result.append({
            "category": b.category,
            "budget": b.amount,
            "spent": used,
            "remaining": remaining
        })

    return jsonify({
        "categories": result,
        "purchases": [
            {
                "name": p.name,
                "category": p.category,
                "amount": p.amount
            } for p in purchases
        ]
    })

@app.route("/api/addcategory", methods=['POST'])
def addcategory():
    '''
    Adds a category to the monthly budget.
    '''
    try:
        data = request.get_json()
        if not data:
            return jsonify({"message": "Invalid JSON"}), 400

        category = data.get('category')

        if not category:
            return jsonify({"message": "Missing category"}), 400

        if not validate_category_name(category):
            return jsonify({"message": "Invalid category format"}), 400

        # guard to make sure duplicate categories do not get created
        if not Budget.query.filter_by(category=category).first():
            category_obj = Budget(
                category=category,
                amount=Decimal('0.00')
            )

            db.session.add(category_obj)
            db.session.commit()

            return jsonify({"message": "Category added successfully!"}), 201

        else:
            # the category is a duplicate
            return jsonify({"message": "Category already exists!"}), 409
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": "Internal server error"}), 500


@app.route("/api/reset", methods=['POST'])
def reset():
    '''
    Deletes all data and categories and resets the budget totally.
    '''
    with app.app_context():
        db.drop_all()
        db.create_all()
    return jsonify({"message": "Database reset successfully!"}), 200


@app.route("/charts/<path:filename>")
def chart_file(filename):
    safe_path = os.path.abspath(os.path.join("charts", filename))
    charts_dir = os.path.abspath("charts")
    if not safe_path.startswith(charts_dir):
        abort(403)  # Forbidden
    if not os.path.exists(safe_path):
        abort(404)
    return send_from_directory("charts", filename)

@app.route("/api/chart", methods=["POST"])
def generate_chart():
    data = request.get_json()
    budgets = {k: Decimal(v) for k, v in data.get("budgets", {}).items()}
    spending = {k: Decimal(v) for k, v in data.get("spending", {}).items()}

    path = visualize_budgets(budgets, spending)

    if not path:
        return jsonify({"message": "No budget data available"}), 400

    return jsonify({"chart_path": f"/charts/{os.path.basename(path)}"}), 200


# install required packages
def install_requirements():
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "--quiet"])
        print(f"Successfully installed packages from requirements.txt")
    except subprocess.CalledProcessError as e:
        print(f"Error during package installation: {e}")


if __name__ == '__main__':
    install_requirements()

    with app.app_context():
        db.create_all()
        rows = db.session.execute(db.text("SELECT name FROM sqlite_master WHERE type='table'")).all()
        print("sqlite tables:", [r[0] for r in rows])

    app.run(debug=False)