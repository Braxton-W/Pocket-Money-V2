"""
    @author Emma Machle
    THIS FILE DOES NOT TEST DATA VISUALIZATION/GRAPHS, WHICH NEED TO BE MANUALLY TESTED!!
"""
import pytest
from app import app, db, Budget, Purchase

@pytest.fixture(scope = "session")
def test_budget_assistant():
    """
    Creates a fixture for the budget assistant app to be tested.
    """
    app.config["TESTING"] = True
    # Below: :memory: refers to the in-memory SQLITE database, which is ephemeral.
    # Good for testing because it doesn't touch the actual database file and corrupt/delete records.
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture(autouse = True)
def reset_db_between_tests(test_budget_assistant):
    """
    Resets the database between each test so that the DB state of each test is independent.
    """
    with test_budget_assistant.app_context():
        db.session.query(Purchase).delete()
        db.session.query(Budget).delete()
        db.session.commit()
        yield


@pytest.fixture()
def client(test_budget_assistant):
    """
    Returns the test client, which is something provided by Flask to test Flask apps.
    """
    return test_budget_assistant.test_client()

#######################################################
#
# TESTS FOR THE API
#
#######################################################

class TestHomepage:
    """
    Per the API code, it should return status code 200. On the web app, it returns index.html.
    """
    def test_returns_200_ok(self, client):
        result = client.get("/")
        assert result.status_code == 200

class TestAddCategory:
    """
    Tests the add category functionality.
    """
    def test_adds_new_category(self, client):
        res = client.post("/api/addcategory", json={"category": "Transportation"})
        assert res.status_code == 201
        assert res.get_json()["message"] == "Category added successfully!"

    def test_duplicate_category_rejected(self, client):
        # Add the Food category 2x, should be rejected the second time.
        res = client.post("/api/addcategory", json={"category": "Food"})
        res = client.post("/api/addcategory", json={"category": "Food"})
        assert res.status_code == 409
        assert res.get_json()["message"] == "Category already exists!"

    def test_new_category_starts_at_zero_amount(self, client, test_budget_assistant):
        client.post("/api/addcategory", json={"category": "Utilities"})
        with test_budget_assistant.app_context():
            b = Budget.query.filter_by(category="Utilities").first()
            assert b.amount == 0

class TestUpdateBudget:
    """
    Tests the functionality of updating the budget.
    """
    def test_creates_budget_when_category_missing(self, client):
        res = client.put("/api/setbudget", json={"category": "Rent", "amount": 1200.0})
        assert res.status_code == 200
        assert res.get_json()["message"] == "Budget set successfully!"

    def test_updates_existing_budget(self, client, test_budget_assistant):
        client.put("/api/setbudget", json={"category": "Food", "amount": 20.0})
        client.put("/api/setbudget", json={"category": "Food", "amount": 750.0})
        with test_budget_assistant.app_context():
            b = Budget.query.filter_by(category="Food").first()
            assert b.amount == 750.0

    def test_creates_new_row_in_db(self, client, test_budget_assistant):
        client.put("/api/setbudget", json={"category": "Gym", "amount": 50.0})
        with test_budget_assistant.app_context():
            b = Budget.query.filter_by(category="Gym").first()
            assert b is not None
            assert b.amount == 50.0

class TestLogPurchase:
    """
    Tests the functionality of logging purchases.
    """
    def test_logs_purchase_for_existing_category(self, client):
        res = client.post("/api/addcategory", json={"category": "Food"})
        res = client.post("/api/logpurchase", json={
            "name": "Groceries",
            "category": "Food",
            "amount": 80.0
        })
        assert res.status_code == 201
        assert res.get_json()["message"] == "Purchase successfully logged!"

    def test_rejects_purchase_for_nonexistent_category(self, client):
        res = client.post("/api/logpurchase", json={
            "name": "Bus pass",
            "category": "Transport",
            "amount": 30.0
        })
        assert res.status_code == 404
        assert "nonexistent category" in res.get_json()["message"]

    def test_purchase_persisted_to_db(self, client, test_budget_assistant):
        res = client.post("/api/addcategory", json={"category": "Food"})
        client.post("/api/logpurchase", json={
            "name": "Pizza",
            "category": "Food",
            "amount": 20.0
        })
        with test_budget_assistant.app_context():
            p = Purchase.query.filter_by(name="Pizza").first()
            assert p is not None
            assert p.amount == 20.0

class TestViewBudget:
    def test_empty_db_returns_empty_lists(self, client):
        res = client.get("/api/viewbudget")
        assert res.status_code == 200
        body = res.get_json()
        assert body["categories"] == []
        assert body["purchases"] == []

    def test_returns_correct_budget_category(self, client):
        res = client.post("/api/addcategory", json={"category": "Food"})
        client.put("/api/setbudget", json={"category": "Food", "amount": 500.0})
        res = client.get("/api/viewbudget")
        assert res.status_code == 200
        cats = res.get_json()["categories"]
        assert len(cats) == 1
        assert cats[0]["category"] == "Food"
        assert cats[0]["budget"] == 500.0

    def test_remaining_calculated_correctly(self, client):
        res = client.post("/api/addcategory", json={"category": "Food"})
        client.put("/api/setbudget", json={"category": "Food", "amount": 500.0})
        client.post("/api/logpurchase", json={
            "name": "Groceries", "category": "Food", "amount": 150.0
        })
        res = client.get("/api/viewbudget")
        cat = res.get_json()["categories"][0]
        assert cat["spent"] == 150.0
        assert cat["remaining"] == 350.0

    def test_overspend_shows_negative_remaining(self, client):
        res = client.post("/api/addcategory", json={"category": "Food"})
        client.put("/api/setbudget", json={"category": "Food", "amount": 500.0})
        client.post("/api/logpurchase", json={
            "name": "whatever", "category": "Food", "amount": 600.0
        })
        res = client.get("/api/viewbudget")
        cat = res.get_json()["categories"][0]
        assert cat["remaining"] == -100.0

    def test_purchases_list_included_in_response(self, client):
        res = client.post("/api/addcategory", json={"category": "Food"})
        client.put("/api/setbudget", json={"category": "Food", "amount": 500.0})
        client.post("/api/logpurchase", json={
            "name": "Sushi", "category": "Food", "amount": 45.0
        })
        purchases = client.get("/api/viewbudget").get_json()["purchases"]
        assert any(p["name"] == "Sushi" for p in purchases)

class TestReset:
    def test_reset_returns_200(self, client):
        res = client.post("/api/reset")
        assert res.status_code == 200
        assert res.get_json()["message"] == "Database reset successfully!"

    def test_reset_clears_budgets(self, client, test_budget_assistant):
        res = client.post("/api/addcategory", json={"category": "Food"})
        client.post("/api/reset")
        with test_budget_assistant.app_context():
            assert Budget.query.count() == 0

    def test_reset_clears_purchases(self, client, test_budget_assistant):
        res = client.post("/api/addcategory", json={"category": "Food"})
        client.post("/api/logpurchase", json={
            "name": "Coffee", "category": "Food", "amount": 5.0
        })
        client.post("/api/reset")
        with test_budget_assistant.app_context():
            assert Purchase.query.count() == 0