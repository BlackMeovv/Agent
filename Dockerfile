# deepquery 服务镜像
# 阶段一：构建 Vue 前端（web/dist 不入库，镜像内自行构建）
FROM node:20-alpine AS webbuild
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# 阶段二：Python 服务
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# 先装依赖层（利用缓存），再拷代码
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

COPY . .
COPY --from=webbuild /web/dist ./web/dist
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev && \
    # matplotlib 供容器内 subprocess 图表执行（容器本身即隔离边界）
    uv pip install matplotlib

EXPOSE 8000
# 启动前确保演示库存在
CMD ["sh", "-c", "test -f \"${DB_PATH:-data/demo/ecommerce.sqlite}\" || uv run python -m deepquery.demo_data; uv run deepquery serve"]
