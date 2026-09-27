# 可选：云托管 / Railway / Fly.io / 任意容器平台都能用
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# 不预建 data 目录：线上用 Supabase，SQLite 只作为本地兜底

EXPOSE 8000

# 多数容器平台会注入 PORT，必须跟随，否则反向代理找不到服务
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
