# Health Pose Assistant — Backend

FastAPI backend for the Health Pose Assistant platform.

## Prerequisites

- Python 3.11+
- PostgreSQL 16 (or 15)
- Homebrew (macOS) or apt (Linux)

## Quick Start (one-liner)

```bash
bash scripts/setup_dev.sh
```

This installs PostgreSQL, creates the database/user, sets up the Python venv, runs migrations, and seeds an admin user.

## Manual Setup

For Docker Compose, create a root `.env` from `.env.example` before starting containers.

### 1. Install & Start PostgreSQL

```bash
# macOS
brew install postgresql@16
brew services start postgresql@16

# Linux
sudo apt install -y postgresql postgresql-contrib
sudo systemctl enable --now postgresql
```

### 2. Create Database & User

```bash
# macOS (current OS user is superuser by default)
createdb health_pose_assistant
psql health_pose_assistant -c "CREATE USER hva_user WITH PASSWORD '<set-a-local-password>';"
psql health_pose_assistant -c "GRANT ALL PRIVILEGES ON DATABASE health_pose_assistant TO hva_user;"
psql health_pose_assistant -c "GRANT ALL ON SCHEMA public TO hva_user;"

# Also create the test database
createdb health_pose_assistant_test
psql health_pose_assistant_test -c "GRANT ALL PRIVILEGES ON DATABASE health_pose_assistant_test TO hva_user;"
psql health_pose_assistant_test -c "GRANT ALL ON SCHEMA public TO hva_user;"
```

### 3. Create Virtual Environment & Install Dependencies

```bash
cd backend
python3.11 -m venv hpa_backend_env
source hpa_backend_env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure Environment

```bash
cp backend/.env.example backend/.env
# Edit backend/.env — set DATABASE_URL, SECRET_KEY, etc.
```

### 4a. Configure Docker Compose

```bash
cp .env.example .env
# Edit .env — set POSTGRES_PASSWORD, BACKEND_SECRET_KEY, and related values.
```

### 5. Run Migrations

```bash
alembic upgrade head
```

### 6. Seed Admin User

```bash
python ../scripts/seed_admin.py --email admin@example.com --password <set-a-local-password>
```

## Running the Server

```bash
cd backend
source hpa_backend_env/bin/activate
uvicorn app.main:app --reload --port 8000
```

API docs available at: http://localhost:8000/docs

## Running Tests

```bash
cd backend
source hpa_backend_env/bin/activate
python -m pytest tests/ -v
```

Test database (`health_pose_assistant_test`) must exist before running tests — see step 2 above.

### Test Coverage Summary

| File | Tests | Covers |
|---|---|---|
| `test_security.py` | 11 | Password hash/verify, JWT create/decode/expire, device token generation |
| `test_auth.py` | 8 | Login success/fail/invalid, /me with valid/no/bad token |
| `test_device.py` | 11 | Config with/without profile/binding, event reporting, heartbeat, auth rejection |
| `test_admin.py` | 17 | Device CRUD, duplicate check, auto-binding, config versioning, stats filtering, permission checks |

## API Endpoints

### Auth (`/api/v1/auth`)

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/login` | — | Returns JWT access_token |
| GET | `/me` | JWT | Current user info |

### Device (`/api/v1/device`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/config` | X-Device-Token | Pull active config + version |
| POST | `/events` | X-Device-Token | Report posture event |
| POST | `/heartbeat` | X-Device-Token | Update last_seen_at |

### Admin (`/api/v1/admin`)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/devices` | JWT (admin) | List all devices |
| POST | `/devices` | JWT (admin) | Register device (returns token) |
| GET | `/config` | JWT (admin) | Get active config profile |
| PUT | `/config` | JWT (admin) | Update config (version++) |
| GET | `/stats` | JWT (admin) | Query daily stats (?device_id&from&to) |

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, CORS, router mounts
│   ├── deps.py              # Auth dependencies (JWT, device token)
│   ├── core/
│   │   ├── config.py        # pydantic-settings .env loader
│   │   └── security.py      # JWT, bcrypt, device token SHA256
│   ├── db/
│   │   ├── base.py          # SQLAlchemy engine + Base
│   │   └── session.py       # get_db dependency
│   ├── models/
│   │   └── models.py        # 7 ORM tables
│   ├── schemas/
│   │   └── schemas.py       # Pydantic request/response models
│   └── routers/
│       ├── auth.py          # POST /login, GET /me
│       ├── device.py        # Device-side endpoints
│       └── admin.py         # Admin endpoints
├── alembic/                 # Migration files
├── tests/                   # pytest test suite
├── requirements.txt
├── .env.example
└── .env                     # Local config (gitignored)
```
