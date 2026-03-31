# 环境依赖安装说明（env_setup_readme.md）

## 当前部署环境信息

操作系统：
Linux iZ2ze5lh4fnt5nbfua1559Z 5.15.0-173-generic #183-Ubuntu SMP Fri Mar 6 13:29:34 UTC 2026 x86_64 x86_64 x86_64 GNU/Linux



本说明适用于 Aliyun ECS 2核4G 部署环境，假设代码和前端/后端包已本地打包好，无需 git。
所有软件版本已明确指定，请严格按照下述版本安装。

## 1. 依赖软件列表

- Python 3.11（建议使用官方包或 deadsnakes 源）
- Node.js 20.x LTS（建议使用官方源安装）
- npm（随 Node.js 20.x 安装）
- PostgreSQL 15.x
- Nginx 1.24.x（建议使用官方源安装）
- 其他基础依赖：pip, venv, build-essential, gcc, make

sudo apt install -y nodejs
## 2. 安装脚本（Ubuntu/Debian 系统为例）

```bash
# 1. 更新系统
sudo apt update && sudo apt upgrade -y

# 2. 安装 Python 3.11 及 venv
sudo apt install -y python3.11 python3.11-venv python3.11-dev python3-pip

# 3. 安装 Node.js 20.x（官方源）
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs

# 4. 安装 PostgreSQL 15.x
# 添加 PostgreSQL 官方源
sudo apt install -y wget ca-certificates
wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | sudo apt-key add -
echo "deb http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" | sudo tee /etc/apt/sources.list.d/pgdg.list
sudo apt update

# 安装 PostgreSQL 15
sudo apt install -y postgresql-15 postgresql-client-15 postgresql-contrib

# 5. 安装 Nginx 1.24.x（官方源）
sudo apt install -y curl gnupg2 ca-certificates lsb-release
echo "deb http://nginx.org/packages/ubuntu `lsb_release -cs` nginx" | sudo tee /etc/apt/sources.list.d/nginx.list
curl -fsSL https://nginx.org/keys/nginx_signing.key | sudo apt-key add -
sudo apt update
sudo apt install -y nginx=1.24.*

# 6. 安装构建工具
sudo apt install -y build-essential gcc make

# 7. 检查版本，确保输出如下：
python3.11 --version   # 期望输出 Python 3.11.x
node -v               # 期望输出 v20.x.x
npm -v                # 期望输出 10.x.x 或随 Node 20.x 的版本
psql --version        # 期望输出 15.x
nginx -v              # 期望输出 1.24.x
```

## 3. 说明
- Python 用于后端（FastAPI/Uvicorn）和 AI 相关脚本。
- Node.js 用于运行 Next.js 前端。
- PostgreSQL 作为主数据库。
- Nginx 作为反向代理和静态资源服务器。
- 所有代码和依赖建议提前打包好，通过 scp/rsync 上传到服务器。
- 数据库初始化、服务启动、Nginx 配置等请参考后续详细文档。

---
如需 CentOS/RHEL 或其他系统脚本，请补充说明。
