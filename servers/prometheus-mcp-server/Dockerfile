# Prometheus MCP Server Dockerfile
# 支持 HTTP 和 stdio 两种模式

FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# 复制项目文件
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY config/config.yaml.example ./config/config.yaml.example

# 安装 Python 依赖
RUN pip install --no-cache-dir -e .

# 创建配置目录
RUN mkdir -p /root/.prometheus-mcp

# 暴露 HTTP 端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/mcp/health || exit 1

# 默认启动命令（HTTP 模式）
ENTRYPOINT ["prometheus-mcp-server"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
