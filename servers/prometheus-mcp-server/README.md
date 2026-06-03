# Prometheus MCP Server

一个独立的 MCP Server，提供 Prometheus 监控指标的查询能力，支持通过自然语言与 AI 助手交互。

PyPI: https://pypi.org/project/prom-mcp-server/

## ✨ 功能特性

- 📊 **即时查询** - 查询当前指标值（`/api/v1/query`）
- 📈 **范围查询** - 查询历史数据趋势（`/api/v1/query_range`）
- 🔍 **序列发现** - 查找匹配的时间序列，无需计算值（`/api/v1/series`）
- 🚨 **告警管理** - 查看告警规则和当前活动告警
- 📡 **Alertmanager** - 查看 Alertmanager 实例及连接状态
- 🎯 **目标状态** - 查看 scrape targets 的健康状态
- 📖 **指标元数据** - 了解指标类型、帮助文本和单位
- 🏷️ **标签查询** - 发现标签的可能值
- ⚙️ **运行时配置** - 查看 Prometheus 运行时 YAML 配置
- 🚩 **启动参数** - 查看 Prometheus 命令行启动参数
- 💻 **运行时信息** - 查看 goroutine、GOMAXPROCS、内存分配等内部状态
- 🗄️ **TSDB 统计** - 查看 head series、WAL、compaction 等存储状态
- 🎯 **目标元数据** - 查看特定 target 暴露的指标信息
- 🔐 **多环境支持** - 同时管理多个 Prometheus 实例
- 🔒 **认证兼容** - 支持无认证、Basic Auth、Bearer Token

## 🏗️ 架构

### stdio 模式（推荐）

```
┌─────────────┐     stdio (stdin/stdout)     ┌─────────────────────┐
│  AI Agent   │ ◄──────────────────────────► │  prom-mcp-server    │
│  (Hermes,   │                              │  (子进程)            │
│   Claude..) │                              └────────┬────────────┘
└─────────────┘                                       │
                                            ┌─────────┴─────────┐
                                            │  Config File       │
                                            │  (~/.prometheus-   │
                                            │   mcp/config.yaml) │
                                            └────────────────────┘
```

### HTTP 模式（独立服务）

```
┌─────────────┐    HTTP/StreamableHTTP     ┌─────────────────────┐
│  AI Agent   │ ◄────────────────────────► │  prom-mcp-server    │
│             │   MCP Protocol             │  (独立服务)          │
└─────────────┘                            └────────┬────────────┘
                                                    │
                                          ┌─────────┴─────────┐
                                          │  Config File       │
                                          │  (~/.prometheus-   │
                                          │   mcp/config.yaml) │
                                          └────────────────────┘
```

## 🚀 快速开始

### 1. 安装

#### 从 PyPI 安装

```bash
pip install prom-mcp-server
```

#### 从 Git 仓库安装

```bash
pip install git+https://github.com/ives22/mcp-tools.git#subdirectory=servers/prometheus-mcp-server
```

#### 从源码安装

```bash
git clone https://github.com/ives22/mcp-tools.git
cd mcp-tools/servers/prometheus-mcp-server
pip install .
```

#### 使用 Docker（HTTP 模式，无需 Python 环境）

```bash
git clone https://github.com/ives22/mcp-tools.git
cd mcp-tools/servers/prometheus-mcp-server
docker build -t prom-mcp-server .
docker run -d --name prom-mcp \
  -p 8000:8000 \
  -v ~/.prometheus-mcp/config.yaml:/root/.prometheus-mcp/config.yaml \
  prom-mcp-server
```

### 2. 配置

```bash
mkdir -p ~/.prometheus-mcp
cp config/config.yaml.example ~/.prometheus-mcp/config.yaml
vim ~/.prometheus-mcp/config.yaml
```

配置示例：

```yaml
environments:
  production:
    url: "http://prometheus.prod:9090"
    auth:
      type: "none"  # none | basic | bearer
    timeout: 30
    verify_ssl: true

  staging:
    url: "http://prometheus.staging:9090"
    auth:
      type: "bearer"
      token: "your-token-here"
    timeout: 30
    verify_ssl: true

defaults:
  timeout: 30
  max_results: 200
  default_step: "1m"
```

### 3. 启动服务

#### 方式一：pip 安装后运行

```bash
# stdio 模式（本地集成，推荐）
prom-mcp-server --transport stdio

# HTTP 模式（独立服务）
prom-mcp-server --host 0.0.0.0 --port 8000

# 详细日志
prom-mcp-server -v
```

#### 方式二：uvx 免安装运行

```bash
# stdio 模式
uvx prom-mcp-server --transport stdio

# HTTP 模式
uvx prom-mcp-server --host 0.0.0.0 --port 8000
```

#### 方式三：Docker 运行

```bash
# HTTP 模式（默认）
docker run -d -p 8000:8000 \
  -v ~/.prometheus-mcp/config.yaml:/root/.prometheus-mcp/config.yaml \
  prom-mcp-server

# stdio 模式
docker run -i --rm \
  -v ~/.prometheus-mcp/config.yaml:/root/.prometheus-mcp/config.yaml \
  prom-mcp-server --transport stdio
```

### 4. 配置 MCP 客户端

本 MCP Server 兼容所有支持 MCP 协议的客户端（Hermes Agent、Claude Desktop、Cursor、Continue 等）。

#### stdio 模式（推荐）

**Hermes Agent** (`~/.hermes/config.yaml`)：

```yaml
mcp_servers:
  prometheus:
    command: "prom-mcp-server"
    args: ["--transport", "stdio"]
    timeout: 60
    connect_timeout: 30
```

**Claude Desktop** (`claude_desktop_config.json`)：

```json
{
  "mcpServers": {
    "prometheus": {
      "command": "prom-mcp-server",
      "args": ["--transport", "stdio"]
    }
  }
}
```

#### HTTP 模式

```yaml
mcp_servers:
  prometheus:
    url: "http://localhost:8000/mcp"
    timeout: 60
    connect_timeout: 30
```

### 5. Docker Compose（可选）

适合长期运行的 HTTP 服务模式：

```yaml
# docker-compose.yml
services:
  prom-mcp:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./config.yaml:/root/.prometheus-mcp/config.yaml:ro
    restart: unless-stopped
```

```bash
docker-compose up -d
```

## 📋 可用工具（18 个）

| 工具名称 | 描述 | 对应 API |
|---------|------|----------|
| `prometheus_query` | 即时 PromQL 查询（当前值） | `/api/v1/query` |
| `prometheus_query_range` | 范围查询（历史数据） | `/api/v1/query_range` |
| `prometheus_query_series` | 查找匹配的时间序列（不计算值） | `/api/v1/series` |
| `prometheus_list_rules` | 查看告警/记录规则 | `/api/v1/rules` |
| `prometheus_list_alerts` | 查看当前活动告警 | `/api/v1/alerts` |
| `prometheus_list_targets` | 查看 scrape 目标状态 | `/api/v1/targets` |
| `prometheus_get_metadata` | 获取指标元数据（类型、帮助文本） | `/api/v1/metadata` |
| `prometheus_get_label_values` | 获取标签的所有可能值 | `/api/v1/label/<name>/values` |
| `prometheus_list_metrics` | 列出所有可用指标名称 | `/api/v1/label/__name__/values` |
| `prometheus_list_labels` | 列出所有标签名称 | `/api/v1/labels` |
| `prometheus_list_environments` | 列出所有配置的环境 | — |
| `prometheus_health` | 检查 Prometheus 健康状态和版本信息 | `/api/v1/status/buildinfo` |
| `prometheus_get_config` | 获取 Prometheus 运行时配置（YAML） | `/api/v1/status/config` |
| `prometheus_get_flags` | 获取 Prometheus 启动参数 | `/api/v1/status/flags` |
| `prometheus_list_alertmanagers` | 列出 Alertmanager 实例及连接状态 | `/api/v1/alertmanagers` |
| `prometheus_get_runtime_info` | 获取运行时信息（goroutine、内存等） | `/api/v1/status/runtimeinfo` |
| `prometheus_get_tsdb_stats` | 获取 TSDB 统计（head series、WAL） | `/api/v1/status/tsdb` |
| `prometheus_get_target_metadata` | 获取目标元数据 | `/api/v1/targets/metadata` |

## 💬 使用示例

配置完成后，可以通过自然语言向 AI 助手提问：

```
用户: "帮我查一下 production 环境当前有多少服务是 up 的"
→ Agent 调用 prometheus_query(query="up", environment="production")

用户: "过去 1 小时 production 的 CPU 使用率趋势如何？"
→ Agent 调用 prometheus_query_range(
      query="100 - (avg by(instance) (rate(node_cpu_seconds_total{mode='idle'}[5m])) * 100)",
      environment="production",
      start="1h ago",
      step="5m"
    )

用户: "production 环境有哪些告警正在触发？"
→ Agent 调用 prometheus_list_alerts(environment="production")

用户: "线上游戏 5318 当前有多少个 Pod？"
→ Agent 调用 prometheus_query(
      query="kube_pod_info{namespace=\"api-games\", pod=~\"5318.*\"}",
      environment="production"
    )
```

## ⚙️ 启动参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | `~/.prometheus-mcp/config.yaml` | 配置文件路径 |
| `--host` | `0.0.0.0` | HTTP 监听地址 |
| `--port` | `8000` | HTTP 监听端口 |
| `--transport` | `http` | 传输模式（http/stdio） |
| `--verbose`, `-v` | `false` | 详细日志 |

## 🔧 开发

```bash
pip install -e ".[dev]"
pytest
ruff check src/
mypy src/
```

## 📁 项目结构

```
prometheus-mcp-server/
├── pyproject.toml                 # 项目配置
├── Dockerfile                     # Docker 构建
├── docker-compose.yml             # Docker Compose 编排
├── README.md                      # 文档
├── config/
│   └── config.yaml.example        # 配置示例
└── src/prometheus_mcp_server/
    ├── __init__.py
    ├── __main__.py                # 入口点
    ├── config.py                  # 配置模型和加载
    ├── client.py                  # Prometheus HTTP 客户端
    ├── server.py                  # MCP Server 主逻辑
    └── tools/
        └── __init__.py            # MCP 工具定义和处理
```

## 📝 License

MIT
