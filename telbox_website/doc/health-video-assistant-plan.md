# Health Video Assistant — Implementation Plan

## Overview

Build a multi-user, multi-device health assistant web platform (`telbox_website`)
on Oracle Cloud Always Free. Stack: **Next.js 15** (frontend) + **FastAPI** (backend)
+ **PostgreSQL**. `pose-video` connects via Device Token to pull config and push events.

---

## Project Structure

```
telbox_website/
├── backend/                    # FastAPI (Python)
│   ├── app/
│   │   ├── main.py
│   │   ├── core/config.py      # .env loader
│   │   ├── core/security.py    # JWT + token hashing
│   │   ├── db/base.py          # SQLAlchemy engine
│   │   ├── models/             # ORM models (7 tables)
│   │   ├── schemas/            # Pydantic request/response models
│   │   └── routers/            # API routes
│   ├── alembic/
│   ├── requirements.txt
│   └── .env.example
└── frontend/                   # Next.js 15 (App Router)
    ├── app/
    │   ├── (auth)/login/
    │   ├── dashboard/          # device overview + today summary
    │   ├── devices/            # device registration & token management
    │   ├── settings/           # pose-video config editor
    │   └── stats/              # charts & history
    ├── components/
    ├── lib/api.ts              # typed backend request wrapper
    └── package.json
```

---

## Database Schema (PostgreSQL)

| Table | Key Columns |
|---|---|
| `users` | id, email, hashed_password, is_admin, created_at |
| `devices` | id, device_code (unique), name, owner_id, last_seen_at |
| `device_tokens` | id, device_id, token_hash, created_at |
| `config_profiles` | id, name, version (int), config_json (JSONB), is_active, updated_at |
| `device_config_bindings` | device_id, profile_id, updated_at |
| `posture_events` | id, device_id, event_type, payload (JSONB), created_at |
| `daily_stats` | id, device_id, stat_date, bad_posture_count, prolonged_alert_count, sitting_minutes, away_count |

`config_json` maps directly to pose-video's `CONFIG` dict — zero migration cost.

---

## API Design

### Device Endpoints (auth: `X-Device-Token` header)

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/device/config` | Pull active config + version |
| POST | `/api/v1/device/events` | Report posture event |
| POST | `/api/v1/device/heartbeat` | Update last_seen_at |

### Admin Endpoints (auth: JWT Bearer)

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/auth/login` | Returns access_token |
| GET | `/api/v1/auth/me` | Current user info |
| GET/POST | `/api/v1/admin/devices` | List / register device |
| GET/PUT | `/api/v1/admin/config` | Read / update active config (version++) |
| GET | `/api/v1/admin/stats` | Stats dashboard (`?device_id&from&to`) |

---

## Implementation Phases

### Phase 1 — Database & Backend Skeleton

1. Init `telbox_website/backend/` with `requirements.txt`
   (fastapi, uvicorn, sqlalchemy, alembic, psycopg2-binary, python-jose, passlib, python-dotenv)
2. Create SQLAlchemy ORM models for all 7 tables (with JSONB fields)
3. Configure Alembic, generate initial migration
4. Implement `core/security.py` (JWT sign/verify, token hashing) and `core/config.py`
5. Implement 3 device-side routes with `X-Device-Token` auth
6. Implement 5 admin routes with JWT Bearer auth
7. Write `.env.example`; verify all endpoints locally with uvicorn + Postman

### Phase 2 — Next.js Frontend Skeleton & Auth

*(depends on Phase 1 step 6)*

8. Init `telbox_website/frontend/` with Tailwind CSS
9. Implement `lib/api.ts` with auto JWT header injection
10. Login page `app/(auth)/login/` with form validation, store token in httpOnly cookie
11. `middleware.ts` to protect all non-auth routes

### Phase 3 — Settings Page (Config Editor)

*(depends on Phase 2)*

12. `app/settings/` page: number sliders/inputs for thresholds, toggles for feature flags,
    editable text lists for `leave_messages` / `welcome_back_messages`
13. Save calls `PUT /admin/config`; page shows current version and last updated time

### Phase 4 — Devices & Stats Pages

*(parallel with Phase 3)*

14. `app/devices/`: device list, online badge (last_seen_at < 60s), register dialog, copy token
15. `app/stats/`: device selector + date range, line charts via Recharts
    (bad_posture, prolonged alerts, sitting minutes, away count per day)
16. `app/dashboard/`: online device count, today's stat summary cards

### Phase 5 — pose-video Client Integration

*(depends on Phase 1)*

17. New file `pose-video/config_client.py`:
    - Background daemon thread, `GET /device/config` every 5 s
    - On version change: hot-patch `PoseStateMachine` threshold attributes in-place
      (no state loss — only thresholds updated, not timers)
18. Modify `pose_detect_mediapipe.py`:
    - `main()` starts `ConfigClient` thread
    - `voice_event` triggers non-blocking `POST /device/events`
      via `ThreadPoolExecutor`
    - Dedicated timer thread, `POST /device/heartbeat` every 30 s
19. Add CLI args `--api-url` and `--device-token`; if omitted → pure local mode
    (fully backward compatible)

### Phase 6 — Oracle Cloud Deployment

*(depends on Phases 1–4)*

20. VM setup: Python 3.11, Node.js 20, PostgreSQL 15, Nginx, Certbot
21. PostgreSQL: localhost-only, create DB + user, run Alembic migration
22. FastAPI: systemd service, uvicorn on `127.0.0.1:8000`
23. Next.js: `npm run build`, PM2, on `127.0.0.1:3000`
24. Nginx: `/api/` → uvicorn, `/` → Next.js, HTTPS via Let's Encrypt
25. Firewall: only 22/80/443; DB never exposed externally

---

## Key Files

| File | Role |
|---|---|
| `pose-video/pose_detect_mediapipe.py` | Add ConfigClient integration, event reporting, heartbeat |
| `pose-video/config_client.py` | New — background config sync thread |
| `telbox_website/backend/app/models/` | 7 ORM table definitions |
| `telbox_website/backend/app/routers/` | Device + admin route handlers |
| `telbox_website/frontend/app/settings/` | Config editor (highest priority page) |
| `telbox_website/frontend/app/stats/` | Stats charts |

---

## Verification Checklist

1. **Phase 1**: Postman runs all 8 endpoints; token auth blocks unauthorized calls
2. **Phase 3**: Save a setting → `config_profiles.version` increments in DB
3. **Phase 5**: Change version in DB → pose-video logs "config updated" within 5 s;
   trigger `bad_posture` → record appears in `posture_events`
4. **Phase 6**: External HTTPS access → full login + config edit + stat view flow works

---

## Design Decisions

- `config_json` is JSONB, directly mapping pose-video's `CONFIG` dict — no schema translation needed
- Device Token is returned plaintext once on creation, stored as hash (like GitHub PAT)
- Config hot-update patches `PoseStateMachine` attributes in-place — no state machine rebuild,
  no loss of accumulated sitting time
- `posture_events` stores raw events; `daily_stats` is aggregated by a backend scheduled task
  (flexible for future re-analysis)
- `--api-url` omitted → pose-video runs in standalone local mode (zero breaking change)
