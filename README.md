# SenitalAI

**AI-Powered Document Verification and Risk Assessment System**

SenitalAI is a document verification and identity-risk assessment platform designed for immigration and border-security workflows. It combines passport/document analysis, MRZ validation, face matching, blacklist/database verification, and risk scoring into a unified officer dashboard.

The project is designed as a **Smart India Hackathon (SIH) demonstration prototype**, with synthetic test data for safe and reproducible testing.

---

## 🚀 Features

* Passport/document image upload
* MRZ extraction and validation
* MRZ check-digit verification
* Document authenticity/risk assessment
* Selfie-to-document face matching
* Database/document verification
* Blacklist detection
* Automated risk scoring
* Secondary-inspection recommendation
* Officer approval/rejection workflow
* Officer decision persistence
* Dashboard for verification results
* REST API backend using FastAPI
* Modern frontend using React + Vite

---

## 🏗️ Project Architecture

```text
                    ┌─────────────────────┐
                    │      Frontend       │
                    │   React + Vite      │
                    │ localhost:5173      │
                    └──────────┬──────────┘
                               │
                               │ REST API
                               ▼
                    ┌─────────────────────┐
                    │      Backend        │
                    │      FastAPI        │
                    │  127.0.0.1:8000     │
                    └──────────┬──────────┘
                               │
             ┌─────────────────┼─────────────────┐
             ▼                 ▼                 ▼
      ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
      │ MRZ         │   │ Face        │   │ Database /  │
      │ Validation  │   │ Matching    │   │ Blacklist   │
      └─────────────┘   └─────────────┘   └─────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Risk Assessment   │
                    │                     │
                    │ Low / Medium / High │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Officer Dashboard   │
                    │ Decision & Review   │
                    └─────────────────────┘
```

---

# 📁 Project Structure

```text
SenitalAI/
│
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   └── ...
│   │
│   ├── tests/
│   │   ├── demo_samples/
│   │   └── ...
│   │
│   ├── requirements.txt
│   └── ...
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   └── ...
│
├── README.md
└── ...
```

---

# 🛠️ Prerequisites

Install the following before running the project:

### Backend

* Python 3.9+
* pip

### Frontend

* Node.js 18+
* npm

Verify the installations:

```bash
python --version
pip --version
node --version
npm --version
```

---

# ⚙️ Installation

Clone the repository:

```bash
git clone https://github.com/Ashwin-rathinakumar/SenitalAI.git
```

Navigate into the project:

```bash
cd SenitalAI
```

---

# 🔧 Backend Setup

Open a terminal and navigate to the backend directory:

### Windows PowerShell

```powershell
cd backend
```

Create a virtual environment:

```powershell
python -m venv venv
```

Activate the virtual environment:

```powershell
.\venv\Scripts\Activate.ps1
```

If PowerShell prevents script execution, you can activate it using:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

Then:

```powershell
.\venv\Scripts\Activate.ps1
```

Install the required Python packages:

```powershell
pip install -r requirements.txt
```

---

# ▶️ Run the Backend

From the `backend` directory:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

The backend will be available at:

```text
http://127.0.0.1:8000
```

FastAPI's interactive API documentation can normally be accessed at:

```text
http://127.0.0.1:8000/docs
```

Keep this terminal running.

---

# 🎨 Frontend Setup

Open a **second terminal** and navigate to the frontend directory:

```powershell
cd frontend
```

Install the Node.js dependencies:

```powershell
npm install
```

---

# ▶️ Run the Frontend

Start the Vite development server:

```powershell
npm run dev
```

The frontend will normally be available at:

```text
http://localhost:5173
```

Open the displayed URL in a browser.

---

# 🧪 SIH Demo Testing

The repository contains synthetic demonstration samples intended for testing the verification workflow.

> **Important:** Use the supplied synthetic/demo documents for testing. Do not upload real passports, identity documents, or other sensitive personal information.

---

## Manual Verification Flow

### Step 1: Start the Backend

In **Terminal 1**:

```powershell
cd backend

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Confirm that the FastAPI server is running on:

```text
http://127.0.0.1:8000
```

---

### Step 2: Start the Frontend

In **Terminal 2**:

```powershell
cd frontend

npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

---

# 🔍 Demo Test Cases

## Test Case 1: Valid Passport + Matching Selfie

### Input

Upload:

* Valid synthetic passport
* Matching synthetic selfie

### Expected Result

The system should indicate:

```text
Risk Score: < 30
MRZ: VALID
Face Match: MATCH
Database: FOUND
Officer Decision: APPROVAL
```

### Expected Workflow

```text
Passport Upload
      ↓
MRZ Validation
      ↓
Face Verification
      ↓
Database Verification
      ↓
Risk Assessment
      ↓
Low Risk
      ↓
Officer Approval
```

---

## Test Case 2: Mismatched Passport / Invalid Check Digit

### Input

Upload a synthetic passport containing an invalid MRZ/check digit or mismatched document information.

### Expected Result

The system should indicate:

```text
Risk Level: HIGH
MRZ: FAIL
Risk Contribution: +20
Recommendation: SECONDARY INSPECTION
```

The officer should be able to review the verification result and record the appropriate decision.

### Expected Workflow

```text
Passport Upload
      ↓
MRZ Extraction
      ↓
Check-Digit Validation
      ↓
MRZ FAIL
      ↓
Risk Score Increased
      ↓
Secondary Inspection Recommended
```

---

## Test Case 3: Blacklisted Document

### Input

Upload the supplied synthetic blacklisted-document sample.

### Expected Result

The system should indicate:

```text
Blacklist Match: DETECTED
Risk Contribution: +30
Database Alert: ACTIVE
Priority: HIGH
```

The system should recommend high-priority review.

### Expected Workflow

```text
Passport Upload
      ↓
Document / Database Verification
      ↓
Blacklist Match
      ↓
Risk Score Increased
      ↓
Database Alert
      ↓
High Priority Review
```

---

# 👮 Officer Decision Workflow

After the automated verification process:

1. Review the verification results.
2. Review MRZ validation status.
3. Review face-match status.
4. Review database/blacklist status.
5. Review the calculated risk level.
6. Review the system recommendation.
7. Select the appropriate officer decision.
8. Submit the decision.
9. Verify that the decision is persisted.
10. Refresh or revisit the dashboard and confirm that the decision remains recorded.

The expected workflow is:

```text
Automated Verification
        ↓
Risk Assessment
        ↓
Officer Review
        ↓
Officer Decision
        ↓
Decision Persistence
        ↓
Dashboard
```

---

# 📊 Risk Assessment

The system uses multiple verification signals to determine the overall risk level.

Example risk contributors include:

| Verification Signal          |     Example Effect |
| ---------------------------- | -----------------: |
| Valid MRZ                    | No additional risk |
| Invalid MRZ/check digit      |                +20 |
| Blacklist match              |                +30 |
| Face mismatch                |     Increased risk |
| Other verification anomalies |     Increased risk |

The final risk assessment is used to classify the verification result and determine whether additional officer review is required.

> The exact scoring logic is implemented in the backend and should be treated as part of the prototype's demonstration logic rather than a production immigration decision system.

---

# 🔌 API

Once the backend is running, FastAPI provides interactive API documentation at:

```text
http://127.0.0.1:8000/docs
```

You can use the Swagger UI to inspect and test the available API endpoints.

The OpenAPI schema is also available at:

```text
http://127.0.0.1:8000/openapi.json
```

---

# 🧪 Testing

Backend tests can be executed from the `backend` directory.

If the project uses `pytest`, run:

```powershell
pytest
```

For verbose output:

```powershell
pytest -v
```

Synthetic demo samples are available under:

```text
backend/tests/demo_samples/
```

---

# 🐛 Troubleshooting

## Backend does not start

Verify Python:

```powershell
python --version
```

Make sure the virtual environment is activated:

```powershell
.\venv\Scripts\Activate.ps1
```

Reinstall dependencies:

```powershell
pip install -r requirements.txt
```

Then start the server again:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

---

## `uvicorn` command not found

Use:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

instead of:

```powershell
uvicorn app.main:app
```

---

## Frontend dependencies are missing

From the frontend directory:

```powershell
npm install
```

Then:

```powershell
npm run dev
```

---

## Port 8000 is already in use

Stop the process using port `8000`, or start FastAPI on another port:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

If the frontend expects port `8000`, make sure the frontend API configuration is updated accordingly.

---

## Port 5173 is already in use

Vite can automatically select another available port. Check the terminal output for the actual URL.

---

# 🔐 Security and Privacy

SenitalAI is a demonstration/research prototype.

### Do not upload:

* Real passports
* Real identity documents
* Real biometric data
* Real personal information
* Production credentials
* Sensitive government data

Use only synthetic or intentionally generated demonstration data while testing this repository.

If deploying the project in a real environment, additional security controls, authentication, authorization, encryption, audit logging, secure storage, privacy controls, and regulatory compliance would be required.

---

# ⚠️ Disclaimer

SenitalAI is a **prototype developed for demonstration and educational/hackathon purposes**.

The system must not be used as the sole basis for real-world immigration, border-control, law-enforcement, identity, or other high-impact decisions.

Automated risk scores and verification results should be treated as decision-support information requiring appropriate human review.

---

# 🧑‍💻 Development

Typical development workflow:

```powershell
# Clone repository
git clone https://github.com/Ashwin-rathinakumar/SenitalAI.git

# Enter project
cd SenitalAI

# Terminal 1
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2
cd frontend
npm install
npm run dev
```

---

# 📌 Quick Start

For developers who already have Python and Node.js installed:

### Terminal 1

```powershell
cd SenitalAI\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Terminal 2

```powershell
cd SenitalAI\frontend
npm install
npm run dev
```

Then open:

```text
http://localhost:5173
```

Backend:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

---

# 📜 License

Add the project's chosen license here.

For example:

```text
MIT License
```

if the repository is intended to be released under the MIT License.

---

# 👥 Contributors

Developed as part of a **Smart India Hackathon (SIH)** project.

Contributions, improvements, bug fixes, and suggestions are welcome.

---

## ⭐ SenitalAI

**Document Verification → Risk Assessment → Human Review → Decision Persistence**

Built as an AI-assisted verification prototype for secure and efficient identity-document screening.

