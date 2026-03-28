# Phase 5 — pose-video Client Integration

## 完成内容

### 后端新增

| 文件 | 变更 |
|------|------|
| `backend/requirements.txt` | 新增 `apscheduler>=3.10,<4.0` |
| `backend/app/tasks.py` | **新文件** — `aggregate_daily_stats_for_date()` 聚合 posture_events → daily_stats；`run_aggregation()` 定时任务入口 |
| `backend/app/main.py` | 增加 `lifespan` 上下文管理器，启动 APScheduler（每 10 分钟聚合 today + yesterday），启动时立即执行一次 |
| `backend/app/schemas/schemas.py` | `DeviceConfigResponse` 增加 `today_sitting_minutes: int = 0` |
| `backend/app/routers/device.py` | `GET /device/config` 返回 `today_sitting_minutes`（从 sitting_summary 事件的 MAX 值计算） |
| `backend/tests/test_aggregation.py` | **新文件** — 8 个测试覆盖聚合逻辑和 today_sitting_minutes |

### pose-video 新增

| 文件 | 变更 |
|------|------|
| `pose-video/config_client.py` | **新文件** — `ConfigClient`（后台轮询配置，热更新阈值）+ `EventReporter`（非阻塞事件上报 + 心跳） |
| `pose-video/requirements.txt` | **新文件** — opencv-python, mediapipe, numpy, Pillow, requests |
| `pose-video/pose_detect_mediapipe.py` | 新增 `--api-url`, `--device-token`, `--config-interval` CLI 参数；集成 ConfigClient + EventReporter + 心跳线程 + 久坐汇报 |

---

## 关键设计

### 1. 聚合策略

- APScheduler `BackgroundScheduler`，每 10 分钟执行一次
- 同时聚合 today 和 yesterday（确保跨午夜数据完整）
- 聚合规则：
  - `bad_posture_count` = COUNT(event_type='bad_posture')
  - `prolonged_alert_count` = COUNT(event_type='prolonged_sitting')
  - `away_count` = COUNT(event_type='leave')
  - `sitting_minutes` = MAX(payload->>'sitting_minutes') from sitting_summary events
- Upsert: 同一 device + date 只保留一行

### 2. 配置热更新

- `ConfigClient` 每 10 秒轮询 `GET /device/config`
- 首次轮询：从 `today_sitting_minutes` 恢复累计坐时（设备重启恢复机制）
- 版本变更时：
  - 热更新 `PoseStateMachine` 的 10 个阈值属性（直接 `setattr`）
  - 热更新 `ExerciseCounter` 的 4 个角度阈值
  - 更新运行时 `CONFIG` 字典（语音、开关等）
- Python GIL 保证简单属性赋值的线程安全

### 3. 事件上报

- `EventReporter` 使用 `ThreadPoolExecutor(max_workers=2)` 非阻塞上报
- 上报的事件类型：
  - `bad_posture` — 坐姿不良语音触发时
  - `prolonged_sitting` — 久坐提醒语音触发时
  - `leave` — 人离开画面时
  - `welcome_back` — 人回到画面时
  - `sitting_summary` — 每 10 分钟上报，payload: `{"sitting_minutes": N}`
- 心跳线程每 30 秒 POST `/device/heartbeat`

### 4. 久坐分钟恢复

- 设备每 10 分钟上报 `sitting_summary`，payload 包含当天累计坐时
- 后端在 `GET /device/config` 响应中返回 `today_sitting_minutes`
- 设备重启后，首次配置轮询时从服务端恢复 `_accumulated_sitting`
- 后端聚合使用 MAX（多次上报取最大值）

### 5. 向后兼容

- `--api-url` 和 `--device-token` 均不提供时，pose-video 以纯本地模式运行
- 不引入任何新的必需依赖（requests 仅在连接后端时使用）
- 所有 config_client 线程均为 daemon thread，主进程退出时自动终止

---

## 时区处理

- 所有时间比较统一使用 UTC（`datetime.datetime.now(datetime.timezone.utc).date()`）
- PostgreSQL `timestamp with time zone` 存储 UTC
- 避免 `datetime.date.today()`（返回本地日期，可能与 UTC 日期不同）

---

## 测试结果

```
63 passed, 0 failed
```

新增 8 个测试：
- `test_aggregate_basic` — 各事件类型计数 + sitting_minutes MAX
- `test_aggregate_upsert` — 重复聚合更新而非重复创建
- `test_aggregate_no_events` — 无事件不创建 daily_stats 行
- `test_aggregate_ignores_other_dates` — 不跨日聚合
- `test_aggregate_welcome_back_ignored` — welcome_back 不影响统计
- `test_config_includes_today_sitting_zero` — 无事件返回 0
- `test_config_includes_today_sitting` — 多次上报取 MAX
- `test_config_today_sitting_with_profile` — 配置和坐时同时返回

---

## 使用示例

```bash
# 纯本地模式（向后兼容，无后端连接）
python pose_detect_mediapipe.py --source 0

# 连接后端
python pose_detect_mediapipe.py --source 0 \
    --api-url http://localhost:8000 \
    --device-token <your-device-token> \
    --config-interval 10
```

## 下一步：Phase 6 — Oracle Cloud 部署
