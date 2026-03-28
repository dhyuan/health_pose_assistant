# JWT + httpOnly Cookie 认证方案详解

## 1. 为什么不把 JWT 存在 localStorage？

| 存储方式 | XSS 攻击能读到 token？ | CSRF 攻击能带上 token？ |
|---|---|---|
| `localStorage` | **能** — 任何注入的 JS 都能 `localStorage.getItem("token")` | 不能 |
| `httpOnly cookie` | **不能** — JS 无法访问 httpOnly cookie | 能（但可防） |

**结论**：httpOnly cookie 对最常见的 XSS 攻击免疫，是更安全的选择。
CSRF 可以通过 `SameSite=Lax`（默认值）+ 同源检查轻松防御。

---

## 2. 核心概念

### 2.1 什么是 httpOnly Cookie

浏览器 Cookie 可以设置多种属性：

```
Set-Cookie: access_token=eyJhbGci...; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=3600
```

| 属性 | 含义 |
|---|---|
| `HttpOnly` | 浏览器禁止 JavaScript 访问这个 cookie（`document.cookie` 看不到） |
| `Secure` | 仅通过 HTTPS 传输（localhost 开发时可以不加） |
| `SameSite=Lax` | 仅同站请求发送 cookie（防 CSRF）。`Lax` 允许顶级导航的 GET（如链接跳转） |
| `Path=/` | cookie 对哪些路径有效 |
| `Max-Age=3600` | cookie 有效期（秒）。等价于 `Expires` 但更简洁 |

### 2.2 JWT 是什么

JWT (JSON Web Token) 是一种紧凑的、自包含的令牌格式：

```
Header.Payload.Signature
```

- **Header**: `{"alg":"HS256","typ":"JWT"}` — 签名算法
- **Payload**: `{"sub":"42","exp":1711612800}` — 用户 ID、过期时间等声明
- **Signature**: `HMAC-SHA256(base64(Header) + "." + base64(Payload), SECRET_KEY)`

服务端验证时：用 SECRET_KEY 重新计算签名，与 token 中的签名比对。
无需查数据库就能确认 token 是否有效、是否过期 → 无状态认证。

---

## 3. 在本项目中的工作流程

```
┌─────────────┐         ┌──────────────────┐         ┌────────────┐
│   Browser    │         │  Next.js Server   │         │   FastAPI   │
│  (React)     │         │  (Route Handler)  │         │  Backend    │
└──────┬───────┘         └────────┬──────────┘         └──────┬──────┘
       │                          │                           │
       │  1. POST /api/auth/login │                           │
       │  {email, password}       │                           │
       │─────────────────────────>│                           │
       │                          │  2. POST /api/v1/auth/login
       │                          │  {email, password}        │
       │                          │──────────────────────────>│
       │                          │                           │
       │                          │  3. {access_token: "ey..."}
       │                          │<──────────────────────────│
       │                          │                           │
       │  4. Set-Cookie:          │                           │
       │     access_token=ey...;  │                           │
       │     HttpOnly; Secure;    │                           │
       │     SameSite=Lax         │                           │
       │<─────────────────────────│                           │
       │                          │                           │
       │  5. 后续请求自动带 cookie │                           │
       │  GET /api/admin/devices  │                           │
       │─────────────────────────>│                           │
       │                          │  6. 从 cookie 取 token    │
       │                          │  Authorization: Bearer ey...
       │                          │──────────────────────────>│
       │                          │                           │
```

### 关键点

1. **浏览器直接与 Next.js 服务器通信**（同源，无 CORS 问题）
2. **Next.js Route Handler 是"中间人"**，负责：
   - 登录时：转发到 FastAPI，拿到 token 后通过 `Set-Cookie` 写入 httpOnly cookie
   - 后续请求：从 cookie 中读取 token，以 `Authorization: Bearer` 转发给 FastAPI
3. **浏览器 JS 永远碰不到 token** → XSS 无法窃取

---

## 4. Next.js 中的实现要点

### 4.1 登录 Route Handler (`app/api/auth/login/route.ts`)

```typescript
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

export async function POST(req: NextRequest) {
  const body = await req.json();

  // 转发到 FastAPI 后端
  const res = await fetch("http://localhost:8000/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const error = await res.json();
    return NextResponse.json(error, { status: res.status });
  }

  const data = await res.json();

  // 设置 httpOnly cookie
  const cookieStore = await cookies();
  cookieStore.set("access_token", data.access_token, {
    httpOnly: true,       // JS 无法读取
    secure: process.env.NODE_ENV === "production",  // 生产环境强制 HTTPS
    sameSite: "lax",      // 防 CSRF
    path: "/",
    maxAge: 60 * 60,      // 1 小时，与 JWT 过期时间一致
  });

  return NextResponse.json({ success: true });
}
```

### 4.2 API 代理 Route Handler (`app/api/[...path]/route.ts`)

```typescript
import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL || "http://localhost:8000";

async function proxyRequest(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get("access_token")?.value;

  // 构建转发 URL
  const url = new URL(req.url);
  const backendPath = url.pathname.replace(/^\/api/, "/api/v1");

  const headers: HeadersInit = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${BACKEND_URL}${backendPath}`, {
    method: req.method,
    headers,
    body: req.method !== "GET" ? await req.text() : undefined,
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export { proxyRequest as GET, proxyRequest as POST, proxyRequest as PUT, proxyRequest as DELETE };
```

### 4.3 Middleware 路由保护 (`middleware.ts`)

```typescript
import { NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest) {
  const token = request.cookies.get("access_token");

  // 未登录 → 重定向到登录页
  if (!token) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

// 保护这些路径
export const config = {
  matcher: ["/dashboard/:path*", "/devices/:path*", "/settings/:path*", "/stats/:path*"],
};
```

---

## 5. 登出

登出只需清除 cookie：

```typescript
// app/api/auth/logout/route.ts
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

export async function POST() {
  const cookieStore = await cookies();
  cookieStore.delete("access_token");
  return NextResponse.json({ success: true });
}
```

---

## 6. CSRF 防护说明

使用 `SameSite=Lax` 后：
- 跨站 POST/PUT/DELETE 请求**不会带 cookie** → CSRF 攻击无效
- 仅同站点发起的请求和顶级导航 GET 才会带 cookie
- 对于本项目已经足够，无需额外的 CSRF token

---

## 7. 与 localStorage 方案的对比总结

| 维度 | localStorage | httpOnly Cookie |
|---|---|---|
| 实现复杂度 | 简单 | 需要 Next.js Route Handler 做代理 |
| XSS 防护 | ❌ token 可被窃取 | ✅ JS 无法读取 |
| CSRF 防护 | ✅ 不自动发送 | ✅ SameSite=Lax 解决 |
| Token 刷新 | 前端手动处理 | Route Handler 统一处理 |
| SSR 兼容 | ❌ 服务端无法读取 | ✅ 服务端可读 cookie |
| 推荐场景 | 快速原型、内部工具 | 生产应用 |

---

## 8. 参考资料

- [OWASP: JWT Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html)
- [MDN: Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie)
- [Next.js Docs: Route Handlers](https://nextjs.org/docs/app/building-your-application/routing/route-handlers)
- [Next.js Docs: Middleware](https://nextjs.org/docs/app/building-your-application/routing/middleware)
