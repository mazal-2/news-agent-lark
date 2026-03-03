# -------------------------------
# 阶段 0 - 依赖安装（可缓存）
# -------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# 复制 lock 文件和项目清单（优先复制这两个，最大化缓存命中） 拷贝到镜像文件里面
COPY pyproject.toml uv.lock* ./

# 安装依赖（--frozen 保证和 lock 文件完全一致） 根据这些文件安装依赖，生成虚拟环境
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# -------------------------------
# 阶段 1 - 运行时镜像（更小）
# -------------------------------
FROM docker.m.daocloud.io/library/python:3.12-slim-bookworm

WORKDIR /app

# 从 builder 阶段拷贝已安装好的虚拟环境
COPY --from=builder /app/.venv /app/.venv  

# 确保使用虚拟环境的 python 和 pip
ENV PATH="/app/.venv/bin:$PATH"

# 复制源代码（代码变动频繁，放在最后）
COPY src/ ./src/
# 如果有其他文件，例如 config.toml .env.example 等，也可以在这里 COPY

# 默认命令（根据你的项目调整）
CMD ["python", "src/news/main.py"]
# 或 CMD ["uv", "run", "main.py"] 也可以，但多了一层 uv 开销