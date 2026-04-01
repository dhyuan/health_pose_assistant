#!/bin/bash
set -e

# 设置默认数据库主机和端口
: ${DB_HOST:=db}
: ${DB_PORT:=5432}

# 等待数据库端口可用
echo "Waiting for db to be ready..."
until nc -z -w 2 "$DB_HOST" "$DB_PORT"; do
  echo "Waiting for PostgreSQL at $DB_HOST:$DB_PORT..."; sleep 2;
done
echo "PostgreSQL is up."

# 数据库迁移（可选）
if [ -f alembic.ini ]; then
  alembic upgrade head
fi

# 启动后端服务
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
