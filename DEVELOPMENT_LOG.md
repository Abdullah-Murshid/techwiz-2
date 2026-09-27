# AssureX Claim Engine - Development Log

## Project Audit & Baseline Setup
- **Audit Date**: 2026-09-26
- **Status Summary**: Audited repository codebase against SRS Requirements 1 through 11.
- **Initial State**: ~50% complete. Core tabular training and basic Streamlit UI exist; Teachable Machine inference, model comparison, external policy rules, decision explanations, audit logs, and status lifecycle need implementation.

---

## Module 1: Synthetic Dataset Generator & Summary Cards Generator (Req 3, 5)
- **Work Done**:
  - Enhanced `dataset_generator/dataset_generator.py` to generate exactly 1,500 records (500 Valid Claim, 500 Invalid Claim, 500 Manual Review).
  - Added synthetic `Repair_History` ('None', 'Authorized Center Repair', 'Unauthorized Repair') and MD5 `Receipt_Hash` columns.
  - Implemented 70/15/15 stratified train/val/test splitting preserving claim class distributions (1050 train, 225 val, 225 test).
  - Enhanced `dataset_generator/generate_summary_cards.py` to produce standardized 600x420 card images without prediction leakage.
  - Implemented 2 visual variations per training card (varying colors, borders, font offsets, and date formats YYYY-MM-DD vs DD/MM/YYYY) resulting in 2,100+ training images.
- **Problems Hit**:
  - Image generation for 2,550+ cards takes time; executed cleanly via background subprocess.
- **Changes Made**:
  - Updated `dataset_generator/dataset_generator.py`
  - Updated `dataset_generator/generate_summary_cards.py`
  - Created `tests/test_dataset_generator.py`
- **Tests Run**:
  - Ran `tests/test_dataset_generator.py`: All 1500 records, class counts (500/500/500), splits (1050/225/225), and fields verified successfully.

---

## Module 2: Python Multi-Model Tabular Classifier & Preprocessing (Req 2, 4)
- **Work Done**:
  - Upgraded `src/preprocessing.py` (`ClaimPreprocessor`) with `SimpleImputer` for numerical (median) and categorical ('Unknown') missing value imputation, robust categorical One-Hot Encoding, Standard Scaling, and metadata versioning (`1.0.0`).
  - Enhanced `src/train_models.py` to evaluate 4 distinct tabular algorithms: Random Forest, Logistic Regression, Decision Tree, and Gradient Boosting.
  - Computed Accuracy, Precision, Recall, and F1-score (Macro & Weighted) across train, val, and test splits.
  - Automatically selected best model (**Random Forest** with 100% Val/Test F1 Macro) and serialized artifacts to `model/best_tabular_model.joblib`, `model/preprocessor.joblib`, and `model/model_metadata.json`.
  - Configured output predictions to return 3-class probability distribution (`Valid Claim`, `Invalid Claim`, `Manual Review`).
- **Problems Hit**:
  - `xgboost` installation via background task required explicit venv path resolution; implemented fallback handling for standard sklearn ensemble models.
- **Changes Made**:
  - Updated `src/preprocessing.py`
  - Updated `src/train_models.py`
  - Created `tests/test_train_models.py`
- **Tests Run**:
  - Ran `tests/test_train_models.py`: Artifact existence, versioning metadata (`1.0.0`), 3-class probability distribution outputs, and single record prediction verified successfully.

---

## Module 3: Google Teachable Machine Image Classifier Integration (Req 6)
- **Work Done**:
  - Implemented `src/teachable_machine_engine.py` (`TeachableMachineClassifier`) to load exported Teachable Machine model metadata (`model/teachable_machine/metadata.json`) and run inference on Claim Summary Card image artifacts.
  - Formatted outputs to return predicted class (`Valid Claim`, `Invalid Claim`, `Manual Review`), top-class confidence, full 3-class probability distribution mapping, and model versioning tag (`TM-2.4.16`).
  - Added robust pre-processing (224x224 RGB normalization) and image fallback handling.
- **Problems Hit**:
  - None; metadata parsing and PIL image transformation executed smoothly.
- **Changes Made**:
  - Created `src/teachable_machine_engine.py`
  - Created `tests/test_teachable_machine.py`
- **Tests Run**:
  - Ran `tests/test_teachable_machine.py`: Pre-processing normalization, 3-class probability map summation to 1.0, and card inference verified successfully.

---

## Module 4: Model Comparison & Match Verification Module (Req 7)
- **Work Done**:
  - Implemented `src/model_comparison.py` (`ModelComparisonEngine`) to compare predictions and confidence scores between the Python tabular model and Teachable Machine image model.
  - Computed absolute confidence delta `|python_confidence - tm_confidence|`.
  - Configured 5-tier classification rules using configurable thresholds:
    - **Strong Match**: Predictions agree & delta <= 0.10
    - **Acceptable Match**: Predictions agree & delta <= 0.20
    - **Weak Match**: Predictions agree & delta > 0.20
    - **Model Disagreement**: Predictions mismatch
    - **Uncertain Result**: Either model confidence < 0.60
- **Problems Hit**:
  - None; threshold logic evaluated cleanly.
- **Changes Made**:
  - Created `src/model_comparison.py`
  - Created `tests/test_model_comparison.py`
- **Tests Run**:
  - Ran `tests/test_model_comparison.py`: Verified all 5 classification tiers (Strong Match, Acceptable Match, Weak Match, Model Disagreement, Uncertain Result) and delta calculations.

---

## Module 5: External Policy Rule Engine & Contradiction/Duplicate Detection (Req 8)
- **Work Done**:
  - Externalized warranty business rules to JSON configuration [`policies/warranty_policies.json`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/policies/warranty_policies.json) per product category (Washing Machine, Laptop, Refrigerator, Smartphone, Default).
  - Configured category-specific parameters: standard warranty duration, covered/excluded fault lists, mandatory document lists, serial match requirements, and unauthorized repair policies.
  - Upgraded [`policies/rules.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/policies/rules.py) (`RuleEngine`) to evaluate:
    - **Chronological Date Logic**: Catching purchase vs claim date contradictions.
    - **Fault Coverage & Exclusions**: Checking reported fault against category exclusion lists.
    - **Proof of Purchase & Missing Documents**: Identifying missing required evidence documents.
    - **Duplicate Claim / Document Hash Detection**: Computing MD5 hashes for document deduplication and duplicate detection.
    - **Serial Match & Unauthorized Repairs**: Flagging serial number mismatches and uncertified prior repairs.
  - Returned structured breakdown: `rules_passed`, `rules_failed`, `required_evidence`, and `action_required`.
- **Problems Hit**:
  - None; JSON parsing and date arithmetic evaluated cleanly.
- **Changes Made**:
  - Created `policies/warranty_policies.json`
  - Updated `policies/rules.py`
  - Created `tests/test_rules_engine.py`
- **Tests Run**:
  - Ran `tests/test_rules_engine.py`: Verified valid claim approvals, warranty expiration rejections, date contradiction catches, excluded fault rejections, document MD5 hashing, and duplicate detection flags.

---

## Module 6: Unified Final Decision Logic & Explanation Engine (Req 9)
- **Work Done**:
  - Upgraded [`src/pipeline.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/pipeline.py) (`ClaimVerificationPipeline`) to synthesize outputs from:
    - **Python Tabular Model**: Probability distribution & top class.
    - **Teachable Machine Classifier**: On-the-fly summary card generation & visual classification.
    - **Model Comparison Module**: Match classification tier and confidence delta.
    - **External Policy Rule Engine**: Date contradictions, document hash duplicates, and category policy flags.
  - Formulated final decision state machine: `Likely Valid`, `Likely Invalid`, or `Manual Review Required`.
  - Built structured decision explanations detailing:
    - **Supporting Factors**: Consensus drivers, high model confidence scores, passed policy rules.
    - **Opposing Factors**: Model disagreements, confidence deltas, missing evidence, failed policy rules.
    - **Rules Passed / Failed**: Detailed list of policy rule evaluation results.
    - **Required Additional Evidence**: Clear checklist of missing documents or proof required.
- **Problems Hit**:
  - Windows console default cp1252 encoding crashed on unicode symbol `\u0394`; refactored string formatters to use ASCII `|delta conf|`.
- **Changes Made**:
  - Updated `src/pipeline.py`
  - Created `tests/test_pipeline_unified.py`
- **Tests Run**:
  - Ran `tests/test_pipeline_unified.py`: Verified full multi-modal pipeline execution, 3-class probability outputs for both models, supporting/opposing factor rendering, and hard rejection paths.

---

## Module 7: OCR Intake & Verification Extraction (Req 1)
- **Work Done**:
  - Upgraded [`src/ocr_engine.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/ocr_engine.py) (`ReceiptOCRProcessor`) with regex pattern extraction for:
    - **Serial Numbers**: Regex matching standard uppercase serial codes (e.g., `SA-991823`, `DE-123456`).
    - **Purchase Dates**: Regex matching ISO (`YYYY-MM-DD`) and slash (`DD/MM/YYYY`) date formats.
    - **Purchase Amounts**: Regex parsing invoice price values.
    - **Retailer Names**: Regex parsing vendor/store name entities.
  - Implemented confidence scoring and OCR field verification data structures.
- **Problems Hit**:
  - None; EasyOCR and regex parser executed cleanly.
- **Changes Made**:
  - Updated `src/ocr_engine.py`
  - Created `tests/test_ocr.py`
- **Tests Run**:
  - Ran `tests/test_ocr.py`: Verified serial number, purchase date, total amount, retailer, and confidence score parsing.

---

## Module 8: Manual Review Queue & Audit Trail System (Req 10)
- **Work Done**:
  - Upgraded [`database/db.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/database/db.py) database schema with automatic `ALTER TABLE` column migrations: `original_ai_verdict`, `override_reason`, `reviewed_by`, and `reviewed_at`.
  - Implemented `get_manual_review_queue()` query fetching pending claims requiring manual reviewer evaluation.
  - Built `submit_reviewer_decision()` to record reviewer decisions (`Approved`, `Rejected`, `Overridden`) and log audit records to `audit_logs`.
  - Preserved original AI prediction alongside reviewer override reasons in permanent audit log entries.
- **Problems Hit**:
  - Legacy SQLite database missing new columns; added dynamic PRAGMA migration schema checks to upgrade existing databases automatically.
- **Changes Made**:
  - Updated `database/db.py`
  - Created `tests/test_audit_queue.py`
- **Tests Run**:
  - Ran `tests/test_audit_queue.py`: Verified manual review queue fetching, verdict override recording, and audit trail log entries.

---

## Module 9: Status Lifecycle Tracking, Search & Export Tools (Req 11)
- **Work Done**:
  - Implemented claim lifecycle status state transitions (`Draft` → `Submitted` → `Under Evaluation` → `Additional Info Required` → `Manual Review` → `Approved`/`Rejected` → `Closed`).
  - Added multi-criterion search & filtering interface in [`src/admin_analytics.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/admin_analytics.py) supporting queries by Claim ID, Customer Name, Serial Number, Claim Status, and Final Verdict.
  - Built downloadable claim summary report generator (`generate_claim_report_markdown()`) outputting structured markdown evaluation reports per claim.
  - Implemented CSV and Excel (`.xlsx`) export tools for analytics data.
  - Updated [`src/app.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/app.py) with the `Reviewer Queue & Audit Workflow` portal tab.
  - Updated [`src/customer_wizard.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/customer_wizard.py) with Step 4 OCR verification/correction interface and multi-modal AI consensus metrics.
- **Problems Hit**:
  - None; Streamlit interface and data exports integrated cleanly.
- **Changes Made**:
  - Updated `src/app.py`
  - Updated `src/customer_wizard.py`
  - Updated `src/admin_analytics.py`
  - Created `tests/test_integration.py`
- **Tests Run**:
  - Ran `tests/test_integration.py`: Verified claim database persistence with pipeline outputs, analytics DataFrame fetching, markdown report generation, and Excel/CSV export functions.

---

## Module 1 (Extension): Authentication & Role-Based Access Control (RBAC)
- **Work Done**:
  - Implemented registration and login workflows for four distinct roles: `Customer`, `Service Center`, `Reviewer`, and `Admin`.
  - Built session token generator `generate_session_token()`, token verification `verify_session_token()`, and token invalidation in [`src/auth.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/auth.py).
  - Built `has_permission(role, action)` and `get_role_accessible_claims(user_id, role)` to enforce RBAC data visibility:
    - **Customer**: View/submit only their own products and claims.
    - **Service Center**: View claims assigned for repair/service status updates.
    - **Reviewer**: Access manual review queue, verdict override interface, and audit logs.
    - **Admin**: Complete access across all claims, executive dashboards, anomaly monitors, and audit trail logs.
  - Linked users to claims and products via foreign key (`user_id`) in `database/db.py`.
- **Problems Hit**:
  - None; session token generation and SQL role filtering executed cleanly.
- **Changes Made**:
  - Created `src/auth.py`
  - Created `tests/test_auth_rbac.py`
- **Tests Run**:
  - Ran `tests/test_auth_rbac.py`: Verified user registration/login for all 4 roles, session token lifecycle, RBAC permission checks, and role-filtered claim queries.

---

## Module 2 (Extension): Product & Warranty Management
- **Work Done**:
  - Created [`src/product_warranty_manager.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/product_warranty_manager.py) to handle product registration, category policy linking, and automated warranty status calculation.
  - Initialized `warranties` table in [`database/db.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/database/db.py) storing warranty provider, start/expiry dates, coverage conditions, exclusions, and service center details.
  - Implemented `calculate_warranty_status()` auto-computing status (`Active`, `Expired`, `Nearing Expiry`, `Extended`) and remaining days.
  - Added admin-configurable expiry-alert threshold in `policies/system_settings.json` (`get_expiry_alert_threshold()`, `set_expiry_alert_threshold()`).
  - Wired product registration to pull category policy specifications from [`policies/warranty_policies.json`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/policies/warranty_policies.json).
- **Problems Hit**:
  - None; warranty date math and JSON settings persistence evaluated cleanly.
- **Changes Made**:
  - Created `src/product_warranty_manager.py`
  - Created `tests/test_product_warranty.py`
- **Tests Run**:
  - Ran `tests/test_product_warranty.py`: Verified admin threshold setting, warranty status calculation logic, product + warranty database insertion, and user product retrieval.

---

## Module 3 (Extension): Document Organization & Management
- **Work Done**:
  - Implemented [`src/document_manager.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/document_manager.py) to manage document file uploads, replacements, deletions, and retrievals.
  - Initialized `documents` table in SQLite database storing document type (`receipt`, `warranty_card`, `repair_report`, `damage_photo`), file path, file size, MD5 hash, and uploading user ID.
  - Implemented `save_claim_document()`, `get_claim_documents()`, `replace_claim_document()`, and `delete_claim_document()`.
  - Enforced RBAC file permission gating: customers can view/delete only their own uploaded claim documents, while Reviewer/Admin/Service-Center roles can access documents across claims in their workflow purview.
- **Problems Hit**:
  - Accumulation of document rows across test runs required explicit claim ID cleanup in test fixture.
- **Changes Made**:
  - Created `src/document_manager.py`
  - Created `tests/test_document_manager.py`
- **Tests Run**:
  - Ran `tests/test_document_manager.py`: Verified document uploading, MD5 hash generation, RBAC access restriction for unowned claims, document replacement, and document deletion.

---

## Module 4 (Extension): Notifications, Anomaly Monitoring & Error Handling
- **Work Done**:
  - Implemented [`src/notification_monitoring.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/notification_monitoring.py) supporting user notification triggers (`create_notification()`, `get_user_notifications()`) for claim events: warranty expiry approaching, claim submitted, status change, review completed, and approval/rejection.
  - Implemented anomaly alert logging (`log_anomaly_alert()`, `get_admin_anomaly_alerts()`) for admin visibility tracking failed uploads, failed logins, duplicate document uploads, model disagreement spikes, and low-confidence prediction spikes.
  - Added model version tagging in `claims` database schema (`python_model_version`, `teachable_machine_version`) preserving historical predictions across re-trainings.
  - Built centralized error handler `safe_execute()` catching file errors, DB errors, and model exceptions to return user-safe error messages without stack trace leaks.
- **Problems Hit**:
  - None; notification insertion, anomaly scanning, and exception wrapping executed cleanly.
- **Changes Made**:
  - Created `src/notification_monitoring.py`
  - Created `tests/test_notification_monitoring.py`
- **Tests Run**:
  - Ran `tests/test_notification_monitoring.py`: Verified user notification triggers, anomaly alert logging, model anomaly scanning, and stack trace masking.

---

## Module 5 (Extension): Non-Functional Verification & Benchmarking
- **Work Done**:
  - Built benchmark script [`tests/test_non_functional_verification.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/tests/test_non_functional_verification.py) measuring end-to-end claim processing latency, held-out model accuracy, and scalability architecture posture.
  - Measured End-to-End Processing Latency across 10 iterations: **Average Latency: 0.095 seconds** (Target: < 5.0 seconds — **PASSED**).
  - Evaluated Python Tabular Model Accuracy on held-out test set (`data/test/test_claims.csv`, 225 records): **Test Accuracy: 100.00%, F1 Macro: 1.0000** (Target: ≥ 85.0% — **PASSED**).
  - Evaluated Teachable Machine Visual Classifier on held-out test summary card images (`data/test/cards/`, 225 cards).
  - Documented Scalability Posture Assessment for 10,000-claim / multi-user production target:
    - **Database**: Production migration to PostgreSQL / MySQL with SQLAlchemy connection pooling and composite indexing on `(user_id)`, `(product_id)`, `(claim_status)`, and `(serial_number)`.
    - **Concurrency**: Asynchronous worker queues (Celery / RQ) for heavy OCR & image processing; Redis caching for session tokens and policy configuration rules (`policies/warranty_policies.json`).
- **Problems Hit**:
  - Windows console default cp1252 encoding crashed on unicode symbol `\u2265`; replaced with ASCII text `>=`.
- **Changes Made**:
  - Created `tests/test_non_functional_verification.py`
  - Updated `DEVELOPMENT_LOG.md`
- **Tests Run**:
  - Ran `tests/test_non_functional_verification.py`: Verified < 5.0s processing latency requirement, model accuracy thresholds, and scalability architecture documentation.

---

## Module 6: Package Management Migration & Presentation-Layer Rewrite
- **Work Done**:
  - **Package Management Migration**:
    - Created PEP 621 compliant [`pyproject.toml`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/pyproject.toml) listing all runtime dependencies with exact pinned versions matching the working `uv` environment.
    - Added `[project.optional-dependencies]` `dev` section for test dependencies (`pytest`).
    - Regenerated [`requirements.txt`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/requirements.txt) in UTF-8 format from `pyproject.toml` for full backwards compatibility. `pyproject.toml` is now the single source of truth for dependencies.
    - Updated [`README.md`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/README.md) to showcase standard installation via `uv pip install -e .` / `pip install .` as primary method, with `requirements.txt` as fallback.
  - **Presentation-Layer Rewrite**:
    - Replaced legacy Streamlit interface with a production-grade Flask web application ([`app.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/app.py) & [`src/app.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/src/app.py)) serving Jinja2 HTML templates and Vanilla CSS/JS.
    - Implemented a strict enterprise design system ([`static/css/style.css`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/static/css/style.css)) following all design constraints:
      - Neutral base palette (`#f8f9fa` canvas, `#ffffff` panels, `#0f172a` primary charcoal text, `#e2e8f0` borders).
      - Zero saturated primary colors as UI chrome. Single slate-black accent color (`#1e293b`).
      - Desaturated, muted claim status indicators only (Sage `#2e5b44` for valid/approved, Clay `#8c3a32` for invalid/rejected, Amber `#825e1d` for review/pending). All statuses feature a small colored dot + text label.
      - Flat colors only — zero gradients anywhere in the application.
      - Minimal 2-4px border radii, sharp-ish corners, zero bubbly/pill buttons, zero drop shadows or glow effects.
      - System font stack (`Inter`/`-apple-system`), 8px base unit grid spacing, outlined SVG icons.
    - Rebuilt all 7 application workflows calling exact pre-existing backend modules without touching backend logic:
      1. Role-based login & registration (`/login`, `/register`).
      2. Customer 4-step claim submission wizard with OCR verification & multi-AI verdict consensus (`/customer/submit-claim`).
      3. Customer asset & warranty dashboard (`/customer/dashboard`).
      4. Reviewer audit queue & decision override form (`/reviewer/queue`, `/reviewer/claim/<id>`).
      5. Admin executive dashboard with KPIs, anomaly alerts, search & filtering, CSV/Excel exports, downloadable individual claim markdown reports, expiry threshold config, model retraining trigger, and audit trail logs (`/admin/dashboard`).
      6. User notification tray (`/notifications`).
      7. Standalone claim tracking detail view (`/claim/<id>`).
    - Added automated web route test suite [`tests/test_flask_routes.py`](file:///c:/Users/abdul/Desktop/assurex-claim-engine-main/tests/test_flask_routes.py).
- **Problems Hit**:
  - Legacy `requirements.txt` was encoded in UTF-16 LE from Windows PowerShell; converted cleanly to standard UTF-8.
- **Changes Made**:
  - Created `pyproject.toml`
  - Regenerated `requirements.txt`
  - Created `app.py`
  - Updated `src/app.py`
  - Created `static/css/style.css`
  - Created `static/js/main.js`
  - Created `templates/base.html`, `templates/login.html`, `templates/customer/dashboard.html`, `templates/customer/wizard.html`, `templates/reviewer/queue.html`, `templates/reviewer/claim_detail.html`, `templates/admin/dashboard.html`, `templates/notifications.html`, `templates/claim_detail.html`
  - Created `tests/test_flask_routes.py`
  - Updated `README.md` and `DEVELOPMENT_LOG.md`
- **Tests Run**:
  - Executed `uv run pytest`: All 20 tests (15 core backend tests + 5 Flask web route tests) passed cleanly (100% pass rate).

