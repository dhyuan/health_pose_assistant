# Health Video Assistant

A full-stack project for posture and sedentary-health assistance:
- Edge-side (camera / Raspberry Pi) real-time posture detection and sedentary reminders
- Web admin platform for device management, configuration delivery, and analytics
- Backend APIs for unified event and heartbeat ingestion

中文: [README_zh.md](README_zh.md)

## Table of Contents

- [Highlights](#highlights)
- [Tech Stack](#tech-stack)
- [Repository Structure](#repository-structure)
- [Quick Start](#quick-start)
- [Run Modes](#run-modes)
- [Development Notes](#development-notes)
- [Roadmap](#roadmap)

## Highlights

- Real-time posture detection: sitting/slouching recognition with sedentary reminders
- Edge-cloud decoupling: edge client can run locally or connect to backend config/event reporting
- Hot config updates: backend configuration can be polled and applied at runtime
- Admin console: device management, config management, and analytics

## Tech Stack

### Edge / CV (`pose-video`)

- Python 3.11+
- OpenCV, MediaPipe, NumPy, Pillow
- Optional: TensorFlow Lite (MoveNet-related scripts)

### Website / Platform (`health_pose_assistant_website`)

- Backend: FastAPI + SQLAlchemy + Alembic + PostgreSQL
- Frontend: Next.js (App Router) + React + TypeScript + Tailwind
- DevOps: Docker Compose

## Repository Structure

```text
health-video-assistant/
├── pose-video/                      # Edge CV app (Mac / Pi stream / local camera)
│   ├── pose_detect_mediapipe.py     # Main entry: detection + alerts + optional backend reporting
│   ├── config_client.py             # Config polling + event reporting client
│   ├── video_on_pi/pi_stream.py     # Pi-side video streaming script
│   └── requirements.txt
└── health_pose_assistant_website/   # Web platform (frontend + backend + DB)
    ├── backend/
    ├── frontend/
    ├── scripts/
    ├── docker-compose.yml
    └── start_dev_backend.sh
```

## Quick Start

### 1) Start the web platform (recommended first)

```bash
cd health_pose_assistant_website
bash scripts/setup_dev.sh
./start_dev_backend.sh
```

Default endpoints:
- Frontend: http://localhost:3000
- Backend: http://localhost:8000
- API Docs: http://localhost:8000/docs

### 2) Start the posture detection client

```bash
cd pose-video
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Local camera debug
python3 pose_detect_mediapipe.py --source 0

# Wait for Pi stream (default TCP 9999)
python3 pose_detect_mediapipe.py
```

### 3) Connect to backend (optional)

```bash
python3 pose_detect_mediapipe.py \
  --api-url http://localhost:8000 \
  --device-token <YOUR_DEVICE_TOKEN>
```

When connected, these features are enabled:
- Config polling (default every 10s)
- Event reporting and heartbeat
- Optional MJPEG output (default port 8080)

## Run Modes

### Local development mode

- Web platform with host PostgreSQL + Python venv + Node.js
- Best for API/frontend/algorithm integration debugging

### Docker Compose mode (Web)

From the `health_pose_assistant_website` directory:

```bash
cp .env.example .env
cp frontend/.env.example frontend/.env  # if present

docker compose up --build
```

## Development Notes

- Validate the minimum pipeline first: `device registration -> device token -> edge event reporting -> dashboard visibility`
- Start with default edge parameters, then calibrate from backend config
- Keep event model compatibility when adding new detections to preserve analytics continuity

## Roadmap

- [ ] 更完善的姿态类别与动作识别
- [ ] 更细粒度的统计看板与趋势分析
- [ ] 多设备与多用户协同管理
- [ ] 生产环境部署脚本与监控告警完善

## License

No license is declared yet. If you plan to open source this repository, add a `LICENSE` file (for example, MIT).
