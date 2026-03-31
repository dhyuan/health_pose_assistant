# 生产环境部署前的准备与配置

本文件总结在部署 pose-video、前端（Next.js）、后端（FastAPI）服务前，必须完成的关键配置步骤。

---

## 1. 数据库（PostgreSQL）配置
- 确认 PostgreSQL 服务已启动并设置为自启动
- 创建项目专用数据库和用户（如 health_pose_assistant）
- 设置强密码，赋予所需权限
- 导入初始表结构（如有迁移脚本或 SQL 文件）
- 配置数据库连接参数（如 .env 文件、环境变量等）

## 2. Python 虚拟环境（venv）
- 后端（FastAPI）和 pose-video 推荐分别创建独立 venv
- 步骤：
  ```bash
  python3.11 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```
- 确认 venv 激活后再运行服务

## 3. Nginx 配置
- 配置反向代理，将 80/443 端口流量转发到前端/后端服务
- 配置静态资源路径（如 /static/、/media/）
- 配置 HTTPS（生产环境强烈建议）
- 示例配置片段：
  ```nginx
  server {
    listen 80;
    server_name your-domain.com;

    location /api/ {
      proxy_pass http://127.0.0.1:8000/;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
    }

    location / {
      proxy_pass http://127.0.0.1:3000/;
      proxy_set_header Host $host;
      proxy_set_header X-Real-IP $remote_addr;
    }
  }
  ```
- 检查并重载 Nginx 配置：
  ```bash
  sudo nginx -t
  sudo systemctl reload nginx
  ```

## 4. 环境变量与配置文件
- 配置 .env 文件（如数据库、后端、前端 API 地址、密钥等）
- 检查各服务依赖的环境变量是否齐全

## 5. 其他准备
- 确认所有依赖包已安装（pip/npm）
- 检查端口占用，确保 8000（后端）、3000（前端）、80/443（Nginx）可用
- 配置日志目录、权限等

---

请根据实际项目结构和安全要求补充细节。