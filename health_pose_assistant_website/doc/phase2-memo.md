# Phase 2 完成备忘录

**完成日期**: 2026-03-28

## 目标

搭建 Next.js 前端骨架，实现 httpOnly Cookie 认证方案，并保护所有需认证路由。

## 完成内容

### 1. Next.js 项目初始化

- 使用 `create-next-app@16.2.1` 创建，App Router + TypeScript + Tailwind CSS v4
- React 19.2.4 + Next.js 16.2.1（Turbopack 构建）
- 源码放在 `src/` 目录下

### 2. Node.js 环境管理

- 使用 **Node 22 LTS**（v22.21.1），通过 nvm 管理
- `.nvmrc` 文件写入 `22`，进入项目后 `nvm use` 自动切版本
- `package.json` 中 `engines: { "node": ">=22.0.0" }` 硬性约束
- `scripts/setup_dev.sh` 新增 `setup_node()` 函数：
  - 检测 Node.js 是否安装
  - 版本不足时自动通过 nvm 安装/切换
  - nvm 不可用时提示手动安装
- `scripts/setup_dev.sh` 新增 `setup_frontend()` 函数：运行 `npm ci` 安装依赖

### 3. UI 组件库 — shadcn/ui

使用 `shadcn@4.1.1` 初始化，已安装 11 个组件：

| 组件 | 用途 |
|---|---|
| `button` | 按钮（登录、提交等） |
| `input` | 文本输入框 |
| `label` | 表单标签 |
| `card` | 登录卡片、信息卡片 |
| `sonner` | Toast 通知 |
| `switch` | 功能开关（Phase 3 配置编辑器） |
| `slider` | 数值滑块（Phase 3 配置编辑器） |
| `textarea` | 多行文本（Phase 3 消息编辑） |
| `separator` | 分隔线 |
| `badge` | 标签/徽章 |
| `tabs` | 选项卡 |

附带依赖：`class-variance-authority`, `clsx`, `lucide-react`, `tailwind-merge`, `tw-animate-css`, `next-themes`

### 4. JWT httpOnly Cookie 认证方案

**核心原理**：浏览器 JS 无法读取 httpOnly cookie，防 XSS 窃取 token。
Next.js Route Handler 作为中间人代理所有 API 请求，从 cookie 中取 token 转发给 FastAPI。

| Route Handler | 方法 | 功能 |
|---|---|---|
| `/api/auth/login` | POST | 转发登录到 FastAPI，将返回的 JWT 设为 httpOnly cookie |
| `/api/auth/logout` | POST | 清除 `access_token` cookie |
| `/api/auth/me` | GET | 从 cookie 取 token，转发到 FastAPI `/api/v1/auth/me` |
| `/api/admin/[...path]` | GET/POST/PUT/DELETE | 通用代理，转发到 FastAPI `/api/v1/admin/*` |

Cookie 属性：
- `httpOnly: true` — JS 不可读
- `secure: true`（生产环境）— 仅 HTTPS
- `sameSite: "lax"` — 防 CSRF
- `maxAge: 3600` — 1 小时，与 JWT 过期时间一致

**端到端验证通过**：登录 → Set-Cookie 设置 → `/api/auth/me` 自动带 cookie → 返回用户信息

### 5. 路由保护 Middleware

`src/middleware.ts` 检查 `access_token` cookie 是否存在：
- 无 cookie → 重定向到 `/login?from=原路径`
- 有 cookie → 放行

保护的路径：`/dashboard/*`, `/devices/*`, `/settings/*`, `/stats/*`

> 注：Next.js 16 提示 middleware 已 deprecated，建议迁移到 "proxy"，但目前仍正常工作。

### 6. 类型化 API 客户端 (`src/lib/api.ts`)

- `ApiError` 类：封装 HTTP 错误（status + detail）
- 通用 `request<T>()` 函数：自动添加 `Content-Type`，错误时抛 `ApiError`
- 导出类型化函数：`login()`, `logout()`, `getMe()`, `listDevices()`, `createDevice()`, `getConfig()`, `updateConfig()`, `getStats()`
- 所有请求走 `/api/...` 同源路径，cookie 自动发送

### 7. 页面结构

| 路径 | 文件 | 状态 |
|---|---|---|
| `/` | `page.tsx` | 重定向到 `/dashboard` |
| `/login` | `(auth)/login/page.tsx` | 完整登录表单 + 错误处理 |
| `/dashboard` | `(app)/dashboard/page.tsx` | 骨架页（Phase 4 实现） |
| `/devices` | `(app)/devices/page.tsx` | 骨架页（Phase 4 实现） |
| `/settings` | `(app)/settings/page.tsx` | 骨架页（Phase 3 实现） |
| `/stats` | `(app)/stats/page.tsx` | 骨架页（Phase 4 实现） |

布局：
- `(auth)/layout.tsx` — 无导航栏的认证页面布局
- `(app)/layout.tsx` — 带顶部导航栏 + Sign out 按钮的应用布局

导航栏项目：Dashboard, Devices, Settings, Stats（当前路径高亮）

### 8. 后端 CORS 修改

- `app/core/config.py` 新增 `FRONTEND_URL` 配置项（默认 `http://localhost:3000`）
- `app/main.py` CORS `allow_origins` 从 `["*"]` 改为 `[settings.FRONTEND_URL]`
- `allow_credentials=True` 保留（httpOnly cookie 跨域需要）

### 9. 学习文档

生成了 `doc/to_learn/jwt-httponly-cookie.md`，涵盖：
- 为什么不用 localStorage
- httpOnly Cookie 属性详解
- 本项目认证流程图
- Next.js Route Handler 实现要点
- 登出方案
- CSRF 防护说明
- 与 localStorage 方案的对比

### 10. 计划文档更新

- `health-video-assistant-plan.md` 中 Node.js 版本从 20 改为 22

## 文件清单

```
health_pose_assistant_website/
├── doc/
│   └── to_learn/
│       └── jwt-httponly-cookie.md            # JWT + httpOnly 学习文档
├── scripts/
│   └── setup_dev.sh                          # 新增 setup_node() + setup_frontend()
├── backend/
│   └── app/
│       ├── main.py                           # CORS 改用 FRONTEND_URL
│       └── core/config.py                    # 新增 FRONTEND_URL 配置
└── frontend/                                 # 【新目录】
    ├── .nvmrc                                # Node 22
    ├── .env.local                            # BACKEND_URL=http://localhost:8000
    ├── .env.example
    ├── package.json                          # engines: node>=22
    ├── tsconfig.json
    ├── next.config.ts
    ├── postcss.config.mjs
    ├── eslint.config.mjs
    ├── components.json                       # shadcn/ui 配置
    ├── src/
    │   ├── middleware.ts                      # 路由保护
    │   ├── lib/
    │   │   ├── api.ts                        # 类型化 API 客户端
    │   │   └── utils.ts                      # shadcn cn() 工具
    │   ├── components/ui/                    # shadcn 组件（11 个）
    │   │   ├── badge.tsx
    │   │   ├── button.tsx
    │   │   ├── card.tsx
    │   │   ├── input.tsx
    │   │   ├── label.tsx
    │   │   ├── separator.tsx
    │   │   ├── slider.tsx
    │   │   ├── sonner.tsx
    │   │   ├── switch.tsx
    │   │   ├── tabs.tsx
    │   │   └── textarea.tsx
    │   └── app/
    │       ├── layout.tsx                    # 根布局（字体 + 全局样式）
    │       ├── page.tsx                      # / → /dashboard 重定向
    │       ├── globals.css                   # Tailwind v4 + shadcn 主题
    │       ├── (auth)/
    │       │   ├── layout.tsx                # 认证页布局（无导航栏）
    │       │   └── login/page.tsx            # 登录页
    │       ├── (app)/
    │       │   ├── layout.tsx                # 应用布局（导航栏 + Sign out）
    │       │   ├── dashboard/page.tsx        # 骨架
    │       │   ├── devices/page.tsx          # 骨架
    │       │   ├── settings/page.tsx         # 骨架
    │       │   └── stats/page.tsx            # 骨架
    │       └── api/
    │           ├── auth/
    │           │   ├── login/route.ts        # 登录代理 + Set-Cookie
    │           │   ├── logout/route.ts       # 清除 cookie
    │           │   └── me/route.ts           # 用户信息代理
    │           └── admin/
    │               └── [...path]/route.ts    # Admin API 通用代理
    └── public/                               # 静态资源（Next.js 默认）
```

## 已知事项

- Next.js 16 的 middleware 文件约定已被标记为 deprecated，建议迁移到 "proxy"。目前功能正常，后续版本可能需要调整。
- `BACKEND_URL` 默认 `http://localhost:8000`，当前测试时后端在 8001 端口运行（8000 被占用），需注意端口一致性。
- 前端 `npm run dev` 的 background terminal 必须从 workspace 根目录通过 `cd frontend && npm run dev` 启动。

## 启动方式

```bash
# 后端
cd backend
source hpa_backend/bin/activate
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
nvm use          # 自动切到 Node 22（读取 .nvmrc）
npm run dev      # http://localhost:3000

# 登录
# 浏览器访问 http://localhost:3000/login
# 账号: admin@example.com / admin123
```
