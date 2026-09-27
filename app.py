import os
import sys
import datetime
import io
import pandas as pd
from flask import (
    Flask, render_template, request, redirect, url_for, flash, session, make_response, send_file
)

sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from database.db import (
    init_db, authenticate_user, create_user, get_manual_review_queue,
    submit_reviewer_decision, get_audit_trail_logs, get_connection,
    fetch_claims_data, generate_claim_report_markdown, record_claim_to_db, save_uploaded_file
)
from src.auth import (
    generate_session_token, verify_session_token, invalidate_session_token, has_permission
)
from src.product_warranty_manager import (
    get_registered_user_products, get_expiry_alert_threshold, set_expiry_alert_threshold
)
from src.notification_monitoring import (
    get_user_notifications, get_admin_anomaly_alerts, check_and_log_model_anomalies
)
from src.ocr_engine import ReceiptOCRProcessor
from src.pipeline import ClaimVerificationPipeline
from src.document_manager import replace_claim_document, save_claim_document, get_claim_documents

# Initialize SQLite database schema
init_db()

app = Flask(__name__, template_folder='templates', static_folder='static')
app.secret_key = os.urandom(24)

# Context Processor for User Notifications & Navigation
@app.context_processor
def inject_global_context():
    context = {'unread_notification_count': 0}
    if session.get('logged_in') and session.get('user'):
        user_id = session['user'].get('user_id') or session['user'].get('id') or 1
        notifications = get_user_notifications(user_id)
        context['unread_notification_count'] = len([n for n in notifications if not n.get('is_read')])
    return context

# Session Verification Middleware
@app.before_request
def check_session_token():
    if session.get('logged_in') and session.get('session_token'):
        user = verify_session_token(session['session_token'])
        if not user:
            session.clear()
            flash("Your session has expired. Please log in again.", "warning")
            return redirect(url_for('login'))

# Helper Auth Decorator
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            flash("Please sign in to access this page.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def role_required(*roles):
    from functools import wraps
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get('logged_in'):
                return redirect(url_for('login'))
            user_role = session.get('user', {}).get('role')
            if user_role not in roles:
                flash("Access denied. Insufficient privileges.", "error")
                return redirect(url_for('index'))
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# --- ROUTES ---

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    user_role = session.get('user', {}).get('role')
    if user_role in ['Admin']:
        return redirect(url_for('admin_dashboard'))
    elif user_role in ['Reviewer']:
        return redirect(url_for('reviewer_queue'))
    else:
        return redirect(url_for('customer_dashboard'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    mode = request.args.get('mode', 'login')
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'login':
            username = request.form.get('username')
            password = request.form.get('password')
            user = authenticate_user(username, password)
            if user:
                token = generate_session_token(user)
                session['logged_in'] = True
                session['session_token'] = token
                session['user'] = dict(user)
                flash(f"Welcome, {user['full_name']}!", "success")
                return redirect(url_for('index'))
            else:
                flash("Invalid Username or Password.", "error")
                return redirect(url_for('login', mode='login'))
        elif action == 'register':
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            full_name = request.form.get('full_name')
            role = request.form.get('role', 'Customer')
            success, msg = create_user(username, email, password, full_name, role)
            if success:
                flash(msg + " You may now log in.", "success")
                return redirect(url_for('login', mode='login'))
            else:
                flash(msg, "error")
                return redirect(url_for('login', mode='register'))

    return render_template('login.html', mode=mode)

@app.route('/logout')
def logout():
    token = session.get('session_token')
    if token:
        invalidate_session_token(token)
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

# --- CUSTOMER DASHBOARD (Overview) ---
@app.route('/customer/dashboard')
@login_required
def customer_dashboard():
    user = session['user']
    user_id = user.get('user_id') or user.get('id') or 1
    products = get_registered_user_products(user_id, user.get('role', 'Customer'))

    # Counts for stat cards
    products_count = len(products)
    active_warranties_count = sum(1 for p in products if p.get('warranty_status') in ('Active', 'Nearing Expiry', 'Extended'))

    # Fetch recent claims for preview (last 3 only)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, p.product_name, p.serial_number
        FROM claims c
        LEFT JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = ?
        ORDER BY c.created_at DESC
        LIMIT 3
    """, (user_id,))
    recent_claims = [dict(r) for r in cursor.fetchall()]

    # Total claims count
    cursor.execute("SELECT COUNT(*) FROM claims WHERE user_id = ?", (user_id,))
    claims_count = cursor.fetchone()[0]
    conn.close()

    return render_template(
        'customer/dashboard.html',
        products_count=products_count,
        active_warranties_count=active_warranties_count,
        claims_count=claims_count,
        claims=recent_claims,
        active_page='dashboard'
    )

# --- CUSTOMER PRODUCTS PAGE ---
@app.route('/customer/products')
@login_required
def customer_products():
    user = session['user']
    user_id = user.get('user_id') or user.get('id') or 1
    products = get_registered_user_products(user_id, user.get('role', 'Customer'))
    return render_template('customer/products.html', products=products, active_page='customer_products')

# --- CUSTOMER CLAIMS PAGE ---
@app.route('/customer/claims')
@login_required
def customer_claims():
    user = session['user']
    user_id = user.get('user_id') or user.get('id') or 1
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, p.product_name, p.serial_number
        FROM claims c
        LEFT JOIN products p ON c.product_id = p.product_id
        WHERE c.user_id = ?
        ORDER BY c.created_at DESC
    """, (user_id,))
    claims = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return render_template('customer/claims.html', claims=claims, active_page='customer_claims')

# --- CUSTOMER SUBMISSION WIZARD ---
@app.route('/customer/submit-claim', methods=['GET', 'POST'])
@login_required
def customer_wizard():
    user = session['user']
    
    # Initialize wizard session state
    if 'wizard_step' not in session:
        session['wizard_step'] = 1
    if 'ocr_data' not in session:
        session['ocr_data'] = {}
    if 'claim_draft' not in session:
        session['claim_draft'] = {
            'claim_id': f"CLM-{int(datetime.datetime.now().timestamp()) % 100000}",
            'receipt_uploaded': False,
            'warranty_uploaded': False,
            'photo_uploaded': False
        }

    # Handle step navigation from query parameters
    set_step = request.args.get('set_step', type=int)
    if set_step in [1, 2, 3, 4]:
        session['wizard_step'] = set_step
        session.modified = True
        return redirect(url_for('customer_wizard'))

    step = session['wizard_step']
    draft = session['claim_draft']
    ocr_data = session['ocr_data']

    if request.method == 'POST':
        post_step = request.form.get('step', type=int)
        
        # Step 1: Product details
        if post_step == 1:
            draft['category'] = request.form.get('category', 'Washing Machine')
            draft['brand'] = request.form.get('brand', 'Samsung')
            draft['model_number'] = request.form.get('model_number', 'SAM-801')
            draft['retailer'] = request.form.get('retailer', 'Official Store')
            draft['serial_number'] = request.form.get('serial_number', 'SA-991823')
            draft['purchase_price'] = float(request.form.get('purchase_price', 850))
            # Validate purchase date — must be a real ISO date (YYYY-MM-DD)
            purchase_date_str = request.form.get('purchase_date', str(datetime.date.today()))
            try:
                datetime.date.fromisoformat(purchase_date_str)
                draft['purchase_date'] = purchase_date_str
            except ValueError:
                flash("Invalid purchase date. Please enter a valid date in YYYY-MM-DD format.", "error")
                return redirect(url_for('customer_wizard'))
            session['claim_draft'] = draft
            session['wizard_step'] = 2
            session.modified = True
            return redirect(url_for('customer_wizard'))

        # Step 2: Fault details
        elif post_step == 2:
            draft['fault_type'] = request.form.get('fault_type', 'Motor Failure')
            draft['product_age'] = int(request.form.get('product_age', 10))
            draft['warranty_duration'] = int(request.form.get('warranty_duration', 24))
            draft['fault_description'] = request.form.get('fault_description', '')
            draft['remaining_warranty'] = max(0, draft['warranty_duration'] - draft['product_age'])
            session['claim_draft'] = draft
            session['wizard_step'] = 3
            session.modified = True
            return redirect(url_for('customer_wizard'))

        # Step 3: Document Uploads & OCR
        elif post_step == 3:
            upload_type = request.form.get('upload_type')
            
            if upload_type == 'receipt':
                file = request.files.get('receipt_file')
                if file:
                    upload_dir = os.path.join('data', 'uploads', draft['claim_id'])
                    os.makedirs(upload_dir, exist_ok=True)
                    path = os.path.join(upload_dir, f"receipt_{file.filename}")
                    file.save(path)
                    draft['receipt_uploaded'] = True
                    draft['receipt_path'] = path
                    
                    # Run OCR
                    try:
                        ocr_engine = ReceiptOCRProcessor()
                        raw_text = ocr_engine.extract_text_from_image(path)
                        session['ocr_data'] = ocr_engine.parse_receipt_data(raw_text)
                        flash("Receipt uploaded & OCR extracted successfully!", "success")
                    except Exception as e:
                        flash(f"Receipt uploaded, but OCR extraction encountered an error: {str(e)}", "warning")
            
            elif upload_type == 'warranty':
                file = request.files.get('warranty_file')
                if file:
                    upload_dir = os.path.join('data', 'uploads', draft['claim_id'])
                    os.makedirs(upload_dir, exist_ok=True)
                    file.save(os.path.join(upload_dir, f"warranty_{file.filename}"))
                    draft['warranty_uploaded'] = True
                    flash("Warranty card attached successfully!", "success")
            
            elif upload_type == 'damage':
                file = request.files.get('photo_file')
                if file:
                    upload_dir = os.path.join('data', 'uploads', draft['claim_id'])
                    os.makedirs(upload_dir, exist_ok=True)
                    file.save(os.path.join(upload_dir, f"damage_photo_{file.filename}"))
                    draft['photo_uploaded'] = True
                    flash("Damage photo attached successfully!", "success")

            elif upload_type == 'replace':
                doc_id = int(request.form.get('doc_id', 1))
                file = request.files.get('replacement_file')
                if file:
                    u_id = user.get('user_id') or user.get('id') or 1
                    u_role = user.get('role', 'Customer')
                    success, msg = replace_claim_document(u_id, u_role, doc_id, file.filename, file.read())
                    if success:
                        flash(f"Document #{doc_id} replaced successfully!", "success")
                    else:
                        flash(msg, "error")

            session['claim_draft'] = draft
            session.modified = True
            return redirect(url_for('customer_wizard'))

        # Step 4: Verification & Final Submission
        elif post_step == 4:
            action_type = request.form.get('action_type')
            
            if action_type == 'verify':
                draft['serial_number'] = request.form.get('confirmed_sn', draft.get('serial_number'))
                draft['purchase_price'] = float(request.form.get('confirmed_price', draft.get('purchase_price', 850)))
                draft['retailer'] = request.form.get('confirmed_retailer', draft.get('retailer'))
                session['claim_draft'] = draft
                session.modified = True
                flash("Inputs updated. Re-evaluating verification pipeline...", "info")
                return redirect(url_for('customer_wizard'))

            elif action_type == 'finalize':
                # Build claim dictionary for pipeline evaluation & database submission
                claim_dict = {
                    'Claim_ID': draft['claim_id'],
                    'Customer_Name': user['full_name'],
                    'Product_Category': draft.get('category', 'Laptop'),
                    'Brand': draft.get('brand', 'Samsung'),
                    'Model_Number': draft.get('model_number', 'SAM-801'),
                    'Serial_Number': draft.get('serial_number', 'SA-991823'),
                    'Purchase_Price': draft.get('purchase_price', 850),
                    'Purchase_Date': str(draft.get('purchase_date', datetime.date.today())),
                    'Claim_Date': datetime.date.today().strftime('%Y-%m-%d'),
                    'Product_Age_Months': draft.get('product_age', 10),
                    'Warranty_Duration_Months': draft.get('warranty_duration', 24),
                    'Remaining_Warranty_Months': draft.get('remaining_warranty', 14),
                    'Fault_Type': draft.get('fault_type', 'Motor Failure'),
                    'Repair_History': 'None',
                    'Has_Receipt': draft.get('receipt_uploaded', True),
                    'Has_Warranty_Card': draft.get('warranty_uploaded', True),
                    'Has_Damage_Photo': draft.get('photo_uploaded', True),
                    'Serial_Number_Match': True,
                    'Previous_Unauthorized_Repairs': False,
                    'Duplicate_Claim_Flag': False,
                    'Date_Contradiction_Flag': False,
                    'Missing_Documents_Count': (0 if draft.get('receipt_uploaded') else 1) + (0 if draft.get('warranty_uploaded') else 1) + (0 if draft.get('photo_uploaded') else 1)
                }

                pipeline_res = None
                try:
                    pipeline = ClaimVerificationPipeline()
                    pipeline_res = pipeline.process_claim(claim_dict)
                    check_and_log_model_anomalies(pipeline_res, draft['claim_id'])
                except Exception as e:
                    import traceback
                    print(f"[ERROR] ClaimVerificationPipeline failed for claim '{draft['claim_id']}': {str(e)}\n{traceback.format_exc()}")
                    flash(f"⚠️ Multi-AI Verification Pipeline Error: {str(e)}", "error")

                success, msg = record_claim_to_db(draft, user, pipeline_result=pipeline_res)
                if success:
                    if pipeline_res is None:
                        flash(f"⚠️ Claim {draft['claim_id']} saved with status 'Processing Failed'. Pipeline processing encountered an error.", "warning")
                    else:
                        flash(f"Claim {draft['claim_id']} submitted successfully!", "success")
                    # Reset wizard state
                    session['wizard_step'] = 1
                    session['ocr_data'] = {}
                    session['claim_draft'] = {
                        'claim_id': f"CLM-{int(datetime.datetime.now().timestamp()) % 100000}",
                        'receipt_uploaded': False,
                        'warranty_uploaded': False,
                        'photo_uploaded': False
                    }
                    return redirect(url_for('customer_dashboard'))
                else:
                    flash(msg, "error")

    # Run pipeline evaluation for Step 4 render
    pipeline_res = None
    if step == 4:
        claim_dict = {
            'Claim_ID': draft['claim_id'],
            'Customer_Name': user['full_name'],
            'Product_Category': draft.get('category', 'Laptop'),
            'Brand': draft.get('brand', 'Samsung'),
            'Model_Number': draft.get('model_number', 'SAM-801'),
            'Serial_Number': draft.get('serial_number', 'SA-991823'),
            'Purchase_Price': draft.get('purchase_price', 850),
            'Purchase_Date': str(draft.get('purchase_date', datetime.date.today())),
            'Claim_Date': datetime.date.today().strftime('%Y-%m-%d'),
            'Product_Age_Months': draft.get('product_age', 10),
            'Warranty_Duration_Months': draft.get('warranty_duration', 24),
            'Remaining_Warranty_Months': draft.get('remaining_warranty', 14),
            'Fault_Type': draft.get('fault_type', 'Motor Failure'),
            'Repair_History': 'None',
            'Has_Receipt': draft.get('receipt_uploaded', True),
            'Has_Warranty_Card': draft.get('warranty_uploaded', True),
            'Has_Damage_Photo': draft.get('photo_uploaded', True),
            'Serial_Number_Match': True,
            'Previous_Unauthorized_Repairs': False,
            'Duplicate_Claim_Flag': False,
            'Date_Contradiction_Flag': False,
            'Missing_Documents_Count': (0 if draft.get('receipt_uploaded') else 1) + (0 if draft.get('warranty_uploaded') else 1) + (0 if draft.get('photo_uploaded') else 1)
        }
        try:
            pipeline = ClaimVerificationPipeline()
            pipeline_res = pipeline.process_claim(claim_dict)
        except Exception:
            pipeline_res = None

    default_purchase_date = (datetime.date.today() - datetime.timedelta(days=300)).strftime('%Y-%m-%d')

    return render_template(
        'customer/wizard.html',
        step=step,
        draft=draft,
        ocr_data=ocr_data,
        pipeline_res=pipeline_res,
        default_purchase_date=default_purchase_date,
        active_page='submit_claim'
    )

# --- REVIEWER QUEUE ---
@app.route('/reviewer/queue')
@role_required('Reviewer', 'Admin')
def reviewer_queue():
    queue_claims = get_manual_review_queue()
    return render_template('reviewer/queue.html', queue_claims=queue_claims, active_page='queue')

@app.route('/reviewer/claim/<claim_id>', methods=['GET', 'POST'])
@role_required('Reviewer', 'Admin')
def reviewer_claim_detail(claim_id):
    user = session['user']
    conn = get_connection()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        new_verdict = request.form.get('new_verdict')
        override_reason = request.form.get('override_reason')
        clean_verdict = new_verdict.replace("Override - ", "")
        u_id = user.get('user_id') or user.get('id') or 1
        
        success, msg = submit_reviewer_decision(
            claim_id=claim_id,
            reviewer_user_id=u_id,
            reviewer_name=user['full_name'],
            new_verdict=clean_verdict,
            override_reason=override_reason
        )
        if success:
            flash(msg, "success")
            return redirect(url_for('reviewer_queue'))
        else:
            flash(msg, "error")

    cursor.execute("""
        SELECT c.*, u.full_name as customer_name, u.email as customer_email,
               p.product_name, p.category, p.brand, p.serial_number, p.purchase_price
        FROM claims c
        LEFT JOIN users u ON c.user_id = u.user_id
        LEFT JOIN products p ON c.product_id = p.product_id
        WHERE c.claim_id = ?
    """, (claim_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        flash(f"Claim {claim_id} not found.", "error")
        return redirect(url_for('reviewer_queue'))

    return render_template('reviewer/claim_detail.html', claim=dict(row), active_page='queue')

# --- ADMIN DASHBOARD ---
@app.route('/admin/dashboard')
@role_required('Admin')
def admin_dashboard():
    df = fetch_claims_data()
    total_claims = len(df)
    valid_claims = len(df[df['final_verdict'].isin(['Likely Valid', 'Approved'])]) if not df.empty else 0
    invalid_claims = len(df[df['final_verdict'].isin(['Likely Invalid', 'Rejected'])]) if not df.empty else 0
    manual_reviews = len(df[df['final_verdict'].isin(['Manual Review Required', 'Manual Review'])]) if not df.empty else 0
    avg_conf = df['ml_confidence'].mean() * 100 if not df.empty and 'ml_confidence' in df and not df['ml_confidence'].isna().all() else 0.0

    kpis = {
        'total_claims': total_claims,
        'valid_claims': valid_claims,
        'valid_pct': (valid_claims / total_claims * 100) if total_claims else 0.0,
        'invalid_claims': invalid_claims,
        'invalid_pct': (invalid_claims / total_claims * 100) if total_claims else 0.0,
        'manual_reviews': manual_reviews,
        'avg_conf': avg_conf
    }
    anomaly_alerts = get_admin_anomaly_alerts(limit=10)

    return render_template(
        'admin/dashboard.html',
        kpis=kpis,
        anomaly_alerts=anomaly_alerts,
        active_page='admin'
    )

@app.route('/admin/alerts')
@role_required('Admin')
def admin_alerts():
    anomaly_alerts = get_admin_anomaly_alerts(limit=200)
    return render_template(
        'admin/alerts.html',
        anomaly_alerts=anomaly_alerts,
        active_page='admin_alerts'
    )

@app.route('/admin/claims')
@role_required('Admin')
def admin_claims():
    df = fetch_claims_data()
    claims = df.to_dict(orient='records') if not df.empty else []
    return render_template(
        'admin/claims.html',
        claims=claims,
        active_page='admin_claims'
    )

@app.route('/admin/controls')
@role_required('Admin')
def admin_controls():
    curr_threshold = get_expiry_alert_threshold()
    return render_template(
        'admin/controls.html',
        curr_threshold=curr_threshold,
        active_page='admin_controls'
    )

@app.route('/admin/audit-log')
@role_required('Admin')
def admin_audit_log():
    audit_logs = get_audit_trail_logs(limit=500)
    return render_template(
        'admin/audit_log.html',
        audit_logs=audit_logs,
        active_page='admin_audit_log'
    )

@app.route('/admin/export/<format>')
@role_required('Admin')
def admin_export(format):
    df = fetch_claims_data()
    if format == 'csv':
        csv_data = df.to_csv(index=False)
        response = make_response(csv_data)
        response.headers["Content-Disposition"] = "attachment; filename=assurex_claims_export.csv"
        response.headers["Content-Type"] = "text/csv"
        return response
    elif format == 'excel':
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Claims_Analytics')
        buffer.seek(0)
        return send_file(
            buffer,
            as_attachment=True,
            download_name="assurex_claims_export.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/download-report')
@role_required('Admin')
def admin_download_report():
    claim_id = request.args.get('claim_id')
    df = fetch_claims_data()
    if not df.empty and claim_id:
        rows = df[df['claim_id'] == claim_id]
        if not rows.empty:
            claim_row = rows.iloc[0].to_dict()
            md_content = generate_claim_report_markdown(claim_row)
            response = make_response(md_content)
            response.headers["Content-Disposition"] = f"attachment; filename=AssureX_Report_{claim_id}.md"
            response.headers["Content-Type"] = "text/markdown"
            return response
    flash("Claim report not found.", "error")
    return redirect(url_for('admin_claims'))

@app.route('/admin/retrain', methods=['POST'])
@role_required('Admin')
def admin_retrain_model():
    try:
        from src.train_models import train_and_evaluate
        train_and_evaluate()
        flash("Tabular ML Models retrained and serialized successfully!", "success")
    except Exception as e:
        flash(f"Model retraining failed: {str(e)}", "error")
    return redirect(url_for('admin_controls'))

@app.route('/admin/threshold', methods=['POST'])
@role_required('Admin')
def admin_set_threshold():
    val = request.form.get('expiry_threshold', type=int)
    if val and set_expiry_alert_threshold(val):
        flash(f"Expiry alert threshold updated to {val} days!", "success")
    else:
        flash("Failed to save threshold setting.", "error")
    return redirect(url_for('admin_controls'))

# --- NOTIFICATIONS TRAY ---
@app.route('/notifications')
@login_required
def notifications():
    user = session['user']
    u_id = user.get('user_id') or user.get('id') or 1
    user_notifications = get_user_notifications(u_id)
    return render_template('notifications.html', notifications=user_notifications, active_page='notifications')

# --- CLAIM TRACKING DETAIL VIEW ---
@app.route('/claim/<claim_id>')
@login_required
def claim_detail(claim_id):
    user = session['user']
    u_id = user.get('user_id') or user.get('id') or 1
    u_role = user.get('role', 'Customer')

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT c.*, p.product_name, p.category, p.serial_number
        FROM claims c
        LEFT JOIN products p ON c.product_id = p.product_id
        WHERE c.claim_id = ?
    """, (claim_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        flash("Claim record not found.", "error")
        return redirect(url_for('index'))

    claim = dict(row)
    docs = get_claim_documents(claim_id, u_id, u_role)

    return render_template('claim_detail.html', claim=claim, docs=docs)

if __name__ == '__main__':
    print("Starting AssureX Claim Engine Flask Web Application on http://127.0.0.1:5000")
    app.run(host='127.0.0.1', port=5000, debug=True)
