# Phase 3 完成备忘录

**完成日期**: 2026-03-28

## 目标

实现 Settings（配置编辑器）页面，允许管理员通过Web界面远程编辑 pose-video 的所有配置项，支持创建默认配置、分类编辑和版本追踪。

## 完成内容

### 1. 默认配置定义 (`src/lib/default-config.ts`)

从 `pose-video/pose_detect_mediapipe.py` 中的 `CONFIG` 字典提取 36 个配置键值，硬编码在前端中：

| 类别 | 键数量 | 举例 |
|---|---|---|
| 功能开关 | 3 | `enable_posture`, `enable_exercise`, `enable_sitting` |
| 视频旋转 | 1 | `video_rotation_angle` |
| 坐姿检测 | 3 | `posture_torso_threshold`, `posture_head_forward_threshold`, `posture_alert_seconds` |
| 运动计数 | 4 | `squat_down_angle`, `squat_up_angle`, `pushup_down_angle`, `pushup_up_angle` |
| 久坐提醒 | 3 | `sitting_alert_minutes`, `sitting_stand_seconds`, `sitting_repeat_alert_minutes` |
| 语音提醒 | 2 | `alert_voice`, `alert_message` |
| 离开/回来消息 | 2 (数组) | `leave_messages` (8条), `welcome_back_messages` (9条) |
| 坐/站判断阈值 | 6 | `sitting_torso_span_threshold`, `sitting_hip_y_threshold` 等 |

**隐藏键**：`host` 和 `port` 不在 UI 中暴露（`HIDDEN_KEYS`），远程修改可能导致 pose-video 网络中断。

### 2. Settings 页面 (`src/app/(app)/settings/page.tsx`)

约 580 行的完整配置编辑器，分为以下部分：

#### 页面状态

| 状态 | 描述 |
|---|---|
| Loading | 加载中 → 显示 "Loading..." |
| No Config | 404 → 显示卡片 + "使用默认配置初始化" 按钮 |
| Config Loaded | 编辑界面，显示 version 和最后更新时间 |

#### 两个 Tab

| Tab | 标签 | 内容 |
|---|---|---|
| 常用设置 | `common` | 功能开关、视频旋转、坐姿检测、久坐提醒、语音提醒、消息列表 |
| 高级阈值 | `advanced` | 运动计数阈值（深蹲/俯卧撑角度）、坐/站判断阈值（6个） |

#### 控件类型映射

| 数据类型 | 控件 | 示例 |
|---|---|---|
| `boolean` | Switch（开关） | `enable_posture` ↔ 开/关 |
| `video_rotation_angle` | Select dropdown（0°/90°/180°/270°） | 下拉选择旋转角度 |
| `string` | Input 文本框 | `alert_voice`, `alert_message` |
| `number` | Slider 滑块 + Input 数值框 | `posture_torso_threshold` = 145 |
| `string[]` | 独立 Input 文本框列表 + 添加/删除按钮 | `leave_messages` (每条消息一个输入框) |

每个控件都有：
- **中文标签**（`Label`）
- **中文描述**（灰色小字）
- 按分类分组，组之间用 `Separator` 分隔

#### 数值范围

`getNumberRange()` 函数为每个数值键指定合理的 min/max/step：

| 键 | 范围 | 步长 |
|---|---|---|
| 角度阈值（躯干/膝盖） | 90–180 或 100–180 | 1 |
| 运动角度 (down) | 60–150 | 1 |
| 运动角度 (up) | 120–180 | 1 |
| 头部前倾阈值 | 0–0.2 | 0.01 |
| 坐姿距离阈值 | 0.1–0.5 | 0.01 |
| 坐姿 Y 阈值 | 0.2–0.8 | 0.01 |
| 久坐提醒分钟 | 1–120 | 1 |
| 站立确认秒数 | 10–300 | 5 |
| 帧平滑 | 1–10 | 1 |

#### 功能特性

1. **Dirty 追踪**：修改任何字段后 "保存配置" 按钮激活，未修改时 disabled
2. **保存反馈**：成功后显示绿色 Badge `"已保存 (version N)"`，错误时显示红色 Badge
3. **版本号 + 时间**：页面顶部显示当前 version 和最后更新时间（`zh-CN` 格式化）
4. **默认配置初始化**：无配置时一键创建，使用 `DEFAULT_CONFIG` 的全部值
5. **隐藏键清理**：保存前自动删除 `host`/`port`

### 3. 新增 shadcn/ui 组件

本阶段新安装了 1 个 shadcn 组件：

| 组件 | 用途 |
|---|---|
| `select` | `video_rotation_angle` 的下拉选择 (0°/90°/180°/270°) |

总已安装 shadcn 组件数：**12 个**（Phase 2 的 11 个 + select）

### 4. 端到端验证

创建 `scripts/test_settings.py` 自动化测试，通过 Next.js 代理执行完整流程：

```
1. Login: 200 -> {'success': True}
2. Get config: 200
3. PUT config: 200 -> version=3
4. PUT config: 200 -> version=4, sitting_alert_minutes=30
All checks passed!
```

验证项：
- ✅ 登录并获取 httpOnly cookie
- ✅ GET /api/admin/config 返回配置
- ✅ PUT /api/admin/config 创建/更新配置
- ✅ 每次更新 version 自增 +1
- ✅ 配置值正确持久化（sitting_alert_minutes=30）

### 5. TypeScript 修复

- `Slider` 的 `onValueChange` 回调可能返回 `number | readonly number[]`，使用 `Array.isArray(v) ? v[0] : v` 安全解包
- `next build` 编译通过，无 TypeScript 错误

## 文件清单

```
health_pose_assistant_website/
├── frontend/src/
│   ├── lib/
│   │   └── default-config.ts                # 默认配置 (36键) + HIDDEN_KEYS
│   ├── components/ui/
│   │   └── select.tsx                        # 【新增】shadcn Select 组件
│   └── app/(app)/
│       └── settings/page.tsx                 # 完整配置编辑器 (~580行)
└── scripts/
    └── test_settings.py                      # 端到端 API 测试
```

## 设计决策

| 决策 | 选型 | 理由 |
|---|---|---|
| Tab 分割 | 常用 + 高级 | 避免一个长页面；日常只需看常用设置 |
| 消息列表控件 | 每条消息独立 Input + 添加/删除 | 比 textarea 更直观，方便单条编辑/排序 |
| 旋转角度控件 | Select dropdown | 只有 4 个有效值（0/90/180/270），dropdown 比 input 更不易出错 |
| 隐藏 host/port | 前端过滤 | 远程修改网络参数可能导致设备不可达 |
| 默认值来源 | 前端硬编码 | 与 pose-video 的 CONFIG 字典保持一致，无需额外 API |

## 已知事项

- 默认配置值从 `pose_detect_mediapipe.py` 手动复制，如果 pose-video 更新了 CONFIG 字典需要同步更新 `default-config.ts`
- 当前后端 config API 只支持一个 active profile（`is_active=True`），Settings 页面直接操作该全局配置
- 消息列表无拖拽排序功能（可作为后续优化）

## 启动方式

```bash
# 后端
cd backend
source hpa_backend/bin/activate
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
nvm use
npm run dev

# 访问
# http://localhost:3000/settings

# 运行测试
python3 scripts/test_settings.py
```
