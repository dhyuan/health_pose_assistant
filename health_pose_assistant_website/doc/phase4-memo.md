# Phase 4 备忘录 — Devices & Stats Pages

## 完成日期
2026-03-29

## 新增后端接口

| 方法 | 路径 | 说明 |
|------|------|------|
| PUT | `/api/v1/admin/devices/{id}` | 编辑设备名称 |
| DELETE | `/api/v1/admin/devices/{id}` | 删除设备（级联删除token、事件、统计） |
| POST | `/api/v1/admin/devices/{id}/regenerate-token` | 重新生成Token（旧Token立即失效） |
| GET | `/api/v1/admin/dashboard` | 仪表盘汇总（设备总数、在线数、今日统计聚合） |

## Device Token 机制

### 生成
- `secrets.token_urlsafe(32)` → 43字符随机明文
- SHA-256 哈希后存入 `device_tokens.token_hash`
- 明文仅在创建/重新生成时返回一次

### 使用
- pose-video 设备请求携带 `X-Device-Token: <明文>` header
- 后端SHA-256哈希后查表匹配 → 认证通过

### 重新生成
- 删除旧 `DeviceToken` 记录 → 旧token立即失效
- 生成新 plain + hash 对
- 设备端需更新配置

### 安全设计
- 数据库只存哈希，泄露无法直接使用
- 类似GitHub PAT模式

## 前端依赖新增
- `recharts` — React图表库（折线图）
- `react-day-picker` — 日期选择器（shadcn Calendar依赖）
- shadcn组件: calendar, popover, dialog, dropdown-menu, table, alert-dialog

## 页面实现

### 设备管理 `/devices`
- 设备列表表格（编号、名称、在线状态、最后在线时间）
- 在线判断: `last_seen_at` < 60秒
- 自动轮询: 默认5分钟 + 手动刷新按钮
- 注册对话框: 输入编号+名称 → 返回Token → 复制提示
- 操作菜单: 重命名、重新生成Token（带确认）、删除（带确认）

### 统计 `/stats`
- 设备选择器（全部/单个设备）
- 日期范围选择器（Calendar + Popover）
- 4个独立折线图: 不良姿势次数、久坐提醒次数、久坐分钟数、离开次数
- 多设备时前端按日期聚合

### 仪表盘 `/dashboard`
- 设备总数、在线设备数
- 今日统计卡片: 不良姿势、久坐提醒、久坐时长、离开次数
- 自动轮询5分钟 + 手动刷新

## UI语言
- 全站中文（导航栏、所有页面标签）
- 不做i18n

## 测试数据
- `scripts/seed_stats.py`: 为所有已注册设备生成过去30天模拟daily_stats
- 用法: `python scripts/seed_stats.py [--days 30]`

## 测试结果
- 后端: 55 tests passed（含11个Phase 4新增测试）
- 前端: `next build` 编译通过，TypeScript类型检查通过

## 注意事项
- shadcn v4 使用 `@base-ui/react` 而非 Radix，Trigger组件无 `asChild` prop
- base-ui Select 的 `onValueChange` 可能传 `null`，需要做降级处理
