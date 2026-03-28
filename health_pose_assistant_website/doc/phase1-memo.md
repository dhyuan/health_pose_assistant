# Phase 1 完成备忘录

**完成日期**: 2026-03-28

## 目标

搭建 FastAPI 后端骨架 + PostgreSQL 数据库，实现全部 8 个 API 端点并通过测试。

## 完成内容

### 1. PostgreSQL 数据库

- 通过 Homebrew 安装 PostgreSQL 16
- 创建数据库 `health_video`（开发）和 `health_video_test`（测试）
- 创建用户 `hva_user`，密码 `hva_dev_pass123`

### 2. 7 张 ORM 表

| 表 | 用途 |
|---|---|
| `users` | 用户账号，含 email、hashed_password、is_admin |
| `devices` | 设备注册，含 device_code（唯一）、owner_id、last_seen_at |
| `device_tokens` | 设备认证令牌，存 SHA-256 hash |
| `config_profiles` | 配置档案，含 version（递增）、config_json（JSONB） |
| `device_config_bindings` | 设备与配置档案的绑定关系 |
| `posture_events` | 姿态事件上报，含 event_type、payload（JSONB） |
| `daily_stats` | 每日统计，含 bad_posture_count、sitting_minutes 等 |

### 3. 8 个 API 端点

**Auth（JWT Bearer）**
- `POST /api/v1/auth/login` — 登录，返回 access_token
- `GET /api/v1/auth/me` — 当前用户信息

**Device（X-Device-Token）**
- `GET /api/v1/device/config` — 拉取配置 + 版本号
- `POST /api/v1/device/events` — 上报姿态事件
- `POST /api/v1/device/heartbeat` — 心跳，更新 last_seen_at

**Admin（JWT Bearer，需 is_admin）**
- `GET/POST /api/v1/admin/devices` — 列表 / 注册设备
- `GET/PUT /api/v1/admin/config` — 读取 / 更新配置（version 自增）
- `GET /api/v1/admin/stats` — 按设备、日期范围查询统计

### 4. 安全机制

- 密码使用 bcrypt 哈希存储
- JWT 签发/验证（python-jose，HS256）
- Device Token 仿 GitHub PAT 模式：创建时返回明文，数据库存 SHA-256
- 未认证请求一律 401，非管理员访问 admin 端点 403

### 5. 测试套件（47 个测试，全部通过）

| 文件 | 数量 | 覆盖 |
|---|---|---|
| `test_security.py` | 11 | 密码 hash/verify、JWT 签发/解析/过期、device token |
| `test_auth.py` | 8 | 登录成功/失败/无效格式、/me 各种认证场景 |
| `test_device.py` | 11 | config 无配置/有 profile/有 binding、事件上报、心跳 |
| `test_admin.py` | 17 | 设备 CRUD、重复检测、auto-binding、config 版本递增、stats 过滤、权限拦截 |

### 6. 工具脚本

- `scripts/setup_dev.sh` — 一键初始化（支持 macOS + Linux VPS）
- `scripts/seed_admin.py` — 种子管理员用户
- `scripts/test_endpoints.py` — 端点冒烟测试（无需 pytest）

### 7. Alembic 迁移

- 已配置 `alembic/env.py` 从 `.env` 读取 DATABASE_URL
- 初始迁移 `3a324cf4391b_initial_tables.py` 包含全部 7 张表

## 文件清单

```
health_pose_assistant_website/
├── README.md
├── scripts/
│   ├── setup_dev.sh
│   ├── seed_admin.py
│   └── test_endpoints.py
└── backend/
    ├── .env.example
    ├── .env
    ├── .gitignore
    ├── requirements.txt
    ├── alembic.ini
    ├── alembic/
    │   ├── env.py
    │   └── versions/3a324cf4391b_initial_tables.py
    ├── hpa_backend/          (Python 3.11 venv)
    ├── app/
    │   ├── main.py
    │   ├── deps.py
    │   ├── core/config.py
    │   ├── core/security.py
    │   ├── db/base.py
    │   ├── db/session.py
    │   ├── models/models.py
    │   ├── schemas/schemas.py
    │   ├── routers/auth.py
    │   ├── routers/device.py
    │   └── routers/admin.py
    └── tests/
        ├── conftest.py
        ├── test_security.py
        ├── test_auth.py
        ├── test_device.py
        └── test_admin.py
```

## 已知事项

- `passlib` 与 `bcrypt>=4.3` 不兼容，已在 requirements.txt 锁定 `bcrypt>=4.0,<4.3`
- 运行测试前需先创建 `health_video_test` 数据库（setup_dev.sh 未自动处理测试库）
- `config_json` 为全量替换（PUT 时整体覆盖，非合并）

## 启动方式

```bash
cd backend
source hpa_backend/bin/activate
uvicorn app.main:app --reload --port 8000
# API 文档: http://localhost:8000/docs
# 运行测试: python -m pytest tests/ -v
```
