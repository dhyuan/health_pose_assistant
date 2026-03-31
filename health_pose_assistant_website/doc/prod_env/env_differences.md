# 生产环境与开发环境的主要区别清单

本文件总结了 health-video-assistant 项目在生产环境（production）与开发环境（development）下的主要差异，便于部署和调试时参考。

---

## 1. 环境变量
- `NODE_ENV=production`：生产环境
- `NODE_ENV=development`：开发环境（本地/测试）

## 2. Cookie 设置
- `secure: process.env.NODE_ENV === "production"`
  - 生产环境：`secure: true`，cookie 仅通过 HTTPS 传输
  - 开发环境：`secure: false`，允许 HTTP 传输，便于本地调试
- `httpOnly: true`、`sameSite: "lax"`、`path: "/"`、`maxAge` 等属性一致

## 3. 后端 API 地址
- 生产环境：`process.env.BACKEND_URL` 通常为线上后端地址（如 https://api.example.com）
- 开发环境：默认 `http://localhost:8000`

## 4. Nginx/反向代理
- 生产环境：Nginx 作为 HTTPS 入口，强制加密流量
- 开发环境：通常直接用 HTTP 端口，无 HTTPS

## 5. 日志与调试
- 生产环境：关闭详细调试日志，开启错误监控
- 开发环境：开启详细日志，便于排查问题

## 6. 静态资源
- 生产环境：静态资源通常经过构建、压缩、CDN 分发
- 开发环境：本地未压缩、热更新

## 7. 依赖与构建
- 生产环境：依赖锁定、严格版本、构建产物优化
- 开发环境：允许热重载、调试工具、未压缩代码

## 8. 其他安全设置
- 生产环境：
  - 强制 HTTPS
  - 更严格的 CORS、CSRF、防护策略
  - 关闭调试接口
- 开发环境：
  - 允许本地 HTTP
  - 放宽安全策略，便于调试

---

如需补充其他差异，请在此文件继续添加。
