import sqlite3
import hashlib
import os
from datetime import datetime

DB_PATH = os.path.join('database', 'assurex.db')

def get_connection():
    os.makedirs('database', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # 1. Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT CHECK(role IN ('Customer', 'Service Center', 'Reviewer', 'Admin')) NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # 2. Products Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            product_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            category TEXT NOT NULL,
            brand TEXT NOT NULL,
            model_number TEXT NOT NULL,
            serial_number TEXT UNIQUE NOT NULL,
            purchase_date TEXT NOT NULL,
            purchase_price REAL NOT NULL,
            retailer TEXT NOT NULL,
            warranty_duration_months INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # 3. Claims Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS claims (
            claim_id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            fault_type TEXT NOT NULL,
            fault_description TEXT,
            claim_status TEXT DEFAULT 'Submitted',
            ml_prediction TEXT,
            ml_confidence REAL,
            teachable_prediction TEXT,
            teachable_confidence REAL,
            original_ai_verdict TEXT,
            final_verdict TEXT,
            override_reason TEXT,
            reviewer_comments TEXT,
            reviewed_by TEXT,
            reviewed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (product_id) REFERENCES products (product_id)
        )
    ''')

    # 4. Audit Trail Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS audit_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Seed Default Admin & Reviewer Accounts if missing
    cursor.execute("SELECT * FROM users WHERE username = 'admin'")
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name, role)
            VALUES (?, ?, ?, ?, ?)
        ''', ('admin', 'admin@assurex.com', hash_password('admin123'), 'System Admin', 'Admin'))

    cursor.execute("SELECT * FROM users WHERE username = 'reviewer'")
    if not cursor.fetchone():
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name, role)
            VALUES (?, ?, ?, ?, ?)
        ''', ('reviewer', 'reviewer@assurex.com', hash_password('reviewer123'), 'Claims Auditor', 'Reviewer'))

    # Run migrations for legacy claims table if missing new columns
    cursor.execute("PRAGMA table_info(claims)")
    existing_cols = [row[1] for row in cursor.fetchall()]
    new_cols = {
        'original_ai_verdict': 'TEXT',
        'override_reason': 'TEXT',
        'reviewed_by': 'TEXT',
        'reviewed_at': 'TIMESTAMP'
    }
    for col_name, col_type in new_cols.items():
        if col_name not in existing_cols:
            cursor.execute(f"ALTER TABLE claims ADD COLUMN {col_name} {col_type}")

    conn.commit()
    conn.close()


def authenticate_user(username, password):
    conn = get_connection()
    cursor = conn.cursor()
    pwd_hash = hash_password(password)
    cursor.execute("SELECT * FROM users WHERE username = ? AND password_hash = ?", (username, pwd_hash))
    user = cursor.fetchone()
    conn.close()
    return user

def create_user(username, email, password, full_name, role='Customer'):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO users (username, email, password_hash, full_name, role)
            VALUES (?, ?, ?, ?, ?)
        ''', (username, email, hash_password(password), full_name, role))
        conn.commit()
        return True, "User registered successfully!"
    except sqlite3.IntegrityError:
        return False, "Username or Email already exists."
    finally:
        conn.close()

def get_manual_review_queue():
    """Fetches all claims awaiting manual review or under evaluation."""
    conn = get_connection()
    cursor = conn.cursor()
    query = """
        SELECT c.claim_id, c.fault_type, c.claim_status, c.ml_prediction, c.ml_confidence,
               c.teachable_prediction, c.teachable_confidence, c.original_ai_verdict,
               c.final_verdict, c.created_at, u.full_name as customer_name,
               p.product_name, p.category, p.brand, p.serial_number
        FROM claims c
        JOIN users u ON c.user_id = u.user_id
        JOIN products p ON c.product_id = p.product_id
        WHERE c.final_verdict = 'Manual Review Required' OR c.claim_status IN ('Submitted', 'Manual Review', 'Under Evaluation')
        ORDER BY c.created_at DESC
    """
    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def submit_reviewer_decision(claim_id: str, reviewer_user_id: int, reviewer_name: str, new_verdict: str, override_reason: str):
    """
    Updates a claim verdict (Approved / Rejected / Overridden) and logs 
    audit entry preserving original AI result alongside override reason.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Fetch existing AI verdict
        cursor.execute("SELECT final_verdict, original_ai_verdict, ml_prediction FROM claims WHERE claim_id = ?", (claim_id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return False, f"Claim {claim_id} not found."
            
        current_verdict = row['final_verdict']
        orig_ai = row['original_ai_verdict'] or current_verdict or row['ml_prediction'] or 'N/A'

        new_status = 'Approved' if new_verdict in ['Approved', 'Likely Valid'] else ('Rejected' if new_verdict in ['Rejected', 'Likely Invalid'] else 'Closed')

        cursor.execute("""
            UPDATE claims
            SET final_verdict = ?,
                claim_status = ?,
                override_reason = ?,
                reviewer_comments = ?,
                reviewed_by = ?,
                reviewed_at = CURRENT_TIMESTAMP
            WHERE claim_id = ?
        """, (new_verdict, new_status, override_reason, override_reason, reviewer_name, claim_id))

        # Insert into Audit Trail Log (Req 10)
        audit_details = (
            f"Claim '{claim_id}': Reviewer '{reviewer_name}' (ID: {reviewer_user_id}) set verdict to '{new_verdict}'. "
            f"Original AI Verdict: '{orig_ai}'. Reason: {override_reason}"
        )
        cursor.execute("""
            INSERT INTO audit_logs (user_id, action, details)
            VALUES (?, ?, ?)
        """, (reviewer_user_id, f"CLAIM_VERDICT_OVERRIDE_{new_status.upper()}", audit_details))


        conn.commit()
        conn.close()
        return True, f"Claim {claim_id} updated successfully to '{new_verdict}'!"
    except Exception as e:
        conn.close()
        return False, f"Failed to submit decision: {str(e)}"

def get_audit_trail_logs(limit=50):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT log_id, user_id, action, details, timestamp FROM audit_logs ORDER BY timestamp DESC LIMIT ?", (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_uploaded_file(uploaded_file, claim_id, file_type):
    upload_dir = os.path.join('data', 'uploads', claim_id)
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{file_type}_{getattr(uploaded_file, 'name', 'file')}")
    if hasattr(uploaded_file, 'getbuffer'):
        data = uploaded_file.getbuffer()
    elif hasattr(uploaded_file, 'read'):
        data = uploaded_file.read()
    else:
        data = uploaded_file
    with open(file_path, "wb") as f:
        f.write(data)
    return file_path

def record_claim_to_db(claim_data, user, pipeline_result=None):
    """Persists product details and customer claim records to SQLite DB."""
    if not os.path.exists(DB_PATH):
        return False, "Database file not found."
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        user_id = user.get('user_id') or user.get('id')
        if user_id is None:
            cursor.execute("SELECT user_id FROM users WHERE username = ?", (user.get('username'),))
            user_row = cursor.fetchone()
            if user_row:
                user_id = user_row[0]
            else:
                user_id = 1

        # 1. Product Insertion / Lookup
        cursor.execute("SELECT product_id FROM products WHERE serial_number = ?", (claim_data['serial_number'],))
        row = cursor.fetchone()
        
        if row:
            product_id = row[0]
        else:
            product_name = f"{claim_data.get('brand', '')} {claim_data.get('model_number', '')}".strip()
            cursor.execute("""
                INSERT INTO products (
                    user_id, product_name, category, brand, model_number, serial_number, 
                    purchase_price, warranty_duration_months, purchase_date, retailer
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                int(user_id),
                product_name if product_name else "Unknown Device",
                claim_data.get('category', 'General'),
                claim_data.get('brand', 'Unknown'),
                claim_data.get('model_number', 'N/A'),
                claim_data.get('serial_number', 'N/A'),
                float(claim_data.get('purchase_price', 0.0)),
                int(claim_data.get('warranty_duration', 12)),
                str(claim_data.get('purchase_date', datetime.now().strftime('%Y-%m-%d'))),
                claim_data.get('retailer', 'Authorized Retailer')
            ))
            product_id = cursor.lastrowid

        # Extract predictions from pipeline result if available
        if pipeline_result and 'python_model' in pipeline_result and 'teachable_machine' in pipeline_result:
            py_pred = pipeline_result['python_model'].get('prediction', 'Unknown')
            py_conf = float(pipeline_result['python_model'].get('confidence', 0.0) or 0.0)
            tm_pred = pipeline_result['teachable_machine'].get('prediction', 'Unknown')
            tm_conf = float(pipeline_result['teachable_machine'].get('confidence', 0.0) or 0.0)
            final_verdict = pipeline_result.get('final_verdict', 'Manual Review Required')
            status_map = {
                'Likely Valid': 'Submitted',
                'Likely Invalid': 'Closed',
                'Manual Review Required': 'Manual Review'
            }
            claim_status = status_map.get(final_verdict, 'Manual Review')
        else:
            py_pred = None
            py_conf = None
            tm_pred = None
            tm_conf = None
            final_verdict = 'Processing Failed'
            claim_status = 'Processing Failed'

        fault_desc = claim_data.get('fault_description')
        if fault_desc is None:
            fault_desc = ""
        else:
            fault_desc = str(fault_desc)

        # 2. Insert claim record into database
        cursor.execute("""
            INSERT OR REPLACE INTO claims (
                claim_id, user_id, product_id, fault_type, fault_description, claim_status,
                ml_prediction, ml_confidence, teachable_prediction, teachable_confidence,
                original_ai_verdict, final_verdict, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            str(claim_data['claim_id']),
            int(user_id),
            int(product_id),
            str(claim_data.get('fault_type', 'General Defect')),
            fault_desc,
            claim_status,
            py_pred,
            py_conf,
            tm_pred,
            tm_conf,
            final_verdict,
            final_verdict,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        
        conn.commit()
        conn.close()
        return True, "Claim submitted successfully!"
    except Exception as e:
        conn.close()
        return False, f"Failed to record claim: {str(e)}"

def fetch_claims_data():
    if not os.path.exists(DB_PATH):
        import pandas as pd
        return pd.DataFrame()
    import pandas as pd
    conn = sqlite3.connect(DB_PATH)
    query = """
        SELECT c.claim_id, c.fault_type, c.claim_status, c.ml_prediction, 
               c.ml_confidence, c.teachable_prediction, c.teachable_confidence,
               c.original_ai_verdict, c.final_verdict, c.override_reason,
               c.reviewer_comments, c.reviewed_by, c.reviewed_at, c.created_at,
               p.product_name, p.category, p.brand, p.serial_number, p.purchase_price,
               u.full_name as customer_name, u.email as customer_email
        FROM claims c
        LEFT JOIN products p ON c.product_id = p.product_id
        LEFT JOIN users u ON c.user_id = u.user_id
        ORDER BY c.created_at DESC
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def generate_claim_report_markdown(claim_row):
    """Generates a downloadable structured evaluation report for a single claim."""
    import pandas as pd
    md = f"# ASSUREX CLAIM ENGINE - INDIVIDUAL CLAIM REPORT\n"
    md += f"**Generated At:** {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    md += f"--- \n\n"
    md += f"### 📄 1. Claim Identification & Customer Information\n"
    md += f"- **Claim ID:** `{claim_row.get('claim_id')}`\n"
    md += f"- **Customer Name:** {claim_row.get('customer_name', 'N/A')}\n"
    md += f"- **Customer Email:** {claim_row.get('customer_email', 'N/A')}\n"
    md += f"- **Submission Date:** {claim_row.get('created_at')}\n"
    md += f"- **Current Lifecycle Status:** `{claim_row.get('claim_status')}`\n\n"
    
    md += f"### 📦 2. Product & Fault Information\n"
    md += f"- **Product Name:** {claim_row.get('product_name')}\n"
    md += f"- **Category:** {claim_row.get('category')}\n"
    md += f"- **Brand:** {claim_row.get('brand')}\n"
    md += f"- **Serial Number:** `{claim_row.get('serial_number')}`\n"
    md += f"- **Purchase Price:** ${claim_row.get('purchase_price')}\n"
    md += f"- **Reported Fault:** {claim_row.get('fault_type')}\n\n"

    ml_pred = claim_row.get('ml_prediction') or 'N/A'
    ml_conf = float(claim_row.get('ml_confidence') or 0.0)
    tm_pred = claim_row.get('teachable_prediction') or 'N/A'
    tm_conf = float(claim_row.get('teachable_confidence') or 0.0)
    md += f"- **Python Tabular Model Prediction:** {ml_pred} ({ml_conf * 100:.1f}% confidence)\n"
    md += f"- **Teachable Machine Visual Prediction:** {tm_pred} ({tm_conf * 100:.1f}% confidence)\n"
    md += f"- **Original AI System Verdict:** `{claim_row.get('original_ai_verdict', 'N/A')}`\n"
    md += f"- **Final System / Reviewer Verdict:** `{claim_row.get('final_verdict')}`\n\n"

    if claim_row.get('reviewed_by'):
        md += f"### 👤 4. Manual Reviewer Audit Log\n"
        md += f"- **Reviewed By:** {claim_row.get('reviewed_by')}\n"
        md += f"- **Reviewed At:** {claim_row.get('reviewed_at')}\n"
        md += f"- **Override Reason / Comments:** {claim_row.get('override_reason') or claim_row.get('reviewer_comments')}\n\n"
        
    md += f"--- \n"
    md += f"*AssureX Automated Claim Verification Engine - Confidential Evaluation Artifact*\n"
    return md

if __name__ == '__main__':
    init_db()
    print("Database initialized with Reviewer Queue & Audit Trail support!")
