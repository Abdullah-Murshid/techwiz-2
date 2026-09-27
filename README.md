# AssureX Claim Verification Engine 🚀

An end-to-end, AI-powered claim verification engine designed to automate electronic claim processing. The system combines **EasyOCR** for document extraction, an **XGBoost machine learning model** for pattern classification, and a deterministic **Rule Engine** for policy compliance enforcement.

---

## 🛠 System Architecture & Data Flow

```
+-------------------+      +-----------------------+
|  Input Claim Data | ---> |  OCR Processing Module |
|  (JSON / Images)  |      | (Extract Text/Serial)  |
+-------------------+      +-----------------------+
                                       |
                                       v
                            +-----------------------+
                            |   XGBoost ML Model    |
                            |  (Predicts Validity)  |
                            +-----------------------+
                                       |
                                       v
                            +-----------------------+
                            |  Policy Rule Engine   |
                            | (Hard Rejections /    |
                            |   Manual Reviews)     |
                            +-----------------------+
                                       |
                                       v
                            +-----------------------+
                            |     Final Verdict     |
                            | (Valid/Invalid/Review)|
                            +-----------------------+
```

---

## 📋 Prerequisites & Requirements

- **Python:** 3.10 or higher
- **Package Manager:** [`uv`](https://github.com/astral-sh/uv) (recommended) or standard `pip`

---

## ⚙️ Project Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Abdullah-Murshid/assurex-claim-engine.git
cd assurex-claim-engine
```

### 2. Create and Activate a Virtual Environment

```bash
# Create a virtual environment
uv venv

# Activate environment (Windows)
.venv\Scripts\activate

# Activate environment (macOS/Linux)
source .venv/bin/activate
```

### 3. Install Dependencies

Primary method (PEP 621 `pyproject.toml`):

```bash
uv pip install -e .
# or standard pip:
pip install .
```

Fallback method (`requirements.txt`):

```bash
uv pip install -r requirements.txt
```

---

## 🚀 Running the Web Application

To launch the Flask web application with the new enterprise presentation layer:

```bash
uv run python app.py
# or
python app.py
```

Open your browser to `http://127.0.0.1:5000`.

### 🔑 Authentication Credentials
- **Admin**: `admin` / `admin123`
- **Reviewer**: `reviewer` / `reviewer123`
- **Customer**: Register any user or login with `testcust` / `pass123`

---

## 🧪 Automated Testing

To run the complete test suite (15 backend tests + 5 Flask route tests):

```bash
uv run pytest
```