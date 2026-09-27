import pytest
import os
import sys
import tempfile

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from database.db import init_db, create_user, authenticate_user

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    init_db()
    with app.test_client() as client:
        yield client

def test_login_page_render(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b"AssureX Claim Engine" in response.data
    assert b"Account Login" in response.data

def test_admin_authentication_and_dashboard(client):
    # Authenticate as admin
    response = client.post('/login', data={'action': 'login', 'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    assert response.status_code == 200
    assert b"Executive Analytics" in response.data or b"Admin Overview" in response.data or b"Total Claims" in response.data

    # Overview page — KPI cards present, no longer contains full audit log section
    res_dash = client.get('/admin/dashboard')
    assert res_dash.status_code == 200
    assert b"Total Claims" in res_dash.data

    # New sub-pages all return 200 and contain their respective headings
    res_alerts = client.get('/admin/alerts')
    assert res_alerts.status_code == 200
    assert b"System Anomaly Alerts" in res_alerts.data

    res_claims = client.get('/admin/claims')
    assert res_claims.status_code == 200
    assert b"Claim Records" in res_claims.data

    res_controls = client.get('/admin/controls')
    assert res_controls.status_code == 200
    assert b"System Administration" in res_controls.data

    res_audit = client.get('/admin/audit-log')
    assert res_audit.status_code == 200
    assert b"System Audit Trail Logs" in res_audit.data

def test_reviewer_queue_and_decision(client):
    # Authenticate as reviewer
    response = client.post('/login', data={'action': 'login', 'username': 'reviewer', 'password': 'reviewer123'}, follow_redirects=True)
    assert response.status_code == 200

    # Check reviewer queue page
    res_queue = client.get('/reviewer/queue')
    assert res_queue.status_code == 200
    assert b"Claims Manual Review" in res_queue.data or b"Claims Awaiting Auditor Review" in res_queue.data

def test_customer_flow(client):
    # Register test customer
    create_user('testcust', 'testcust@example.com', 'pass123', 'Test Customer', 'Customer')
    
    # Login as customer
    response = client.post('/login', data={'action': 'login', 'username': 'testcust', 'password': 'pass123'}, follow_redirects=True)
    assert response.status_code == 200

    # Visit customer dashboard (overview — page title changed from "Customer Dashboard")
    res_dash = client.get('/customer/dashboard')
    assert res_dash.status_code == 200
    assert b"Welcome back" in res_dash.data or b"Customer Portal" in res_dash.data

    # Visit new products page
    res_products = client.get('/customer/products')
    assert res_products.status_code == 200
    assert b"Registered Products" in res_products.data

    # Visit new claims page
    res_claims = client.get('/customer/claims')
    assert res_claims.status_code == 200
    assert b"Claim Submission History" in res_claims.data

    # Visit wizard step 1
    res_wiz = client.get('/customer/submit-claim')
    assert res_wiz.status_code == 200
    assert b"Step 1: Product Information" in res_wiz.data

def test_admin_csv_export(client):
    client.post('/login', data={'action': 'login', 'username': 'admin', 'password': 'admin123'}, follow_redirects=True)
    res_csv = client.get('/admin/export/csv')
    assert res_csv.status_code == 200
    assert res_csv.mimetype == 'text/csv'
