# 图表沙箱镜像：宿主机直跑（非 compose）时供 DockerSandbox 使用
#   docker build -t insight-agent-chart docker/chart-sandbox
FROM python:3.12-slim
RUN pip install --no-cache-dir matplotlib && \
    useradd -m runner
USER runner
WORKDIR /work
