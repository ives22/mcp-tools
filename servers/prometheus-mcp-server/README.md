# Prometheus MCP Server

一个独立的 MCP Server，提供 Prometheus 监控指标的查询能力，支持通过自然语言与 AI 助手交互。

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
- 🔐 **多环境支持** - 同时管理多个 Prometheus 实例
- 🔒 **认证兼容** - 支持无认证、Basic Auth、Bearer Token

## 🏗️ 架构

### stdio 模式（推荐）

```
┌─────────────┐     stdio (stdin/stdout)     ┌─────────────────────┐
│  Hermes     │ ◄──────────────────────────► │  Prometheus         │
│  Agent      │                              │  MCP Server (子进程)  │
│             │                              └────────┬────────────┘
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
│  Hermes     │ ◄────────────────────────► │  Prometheus         │
│  Agent      │   MCP Protocol             │  MCP Server (独立服务)│
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

```bash
cd /root/prometheus-mcp-server
pip install -e .
# 或者使用 uv
uv pip install -e .
```

### 2. 配置

```bash
mkdir -p ~/.prometheus-mcp
cp config/config.yaml.example ~/.prometheus-mcp/config.yaml
# 编辑配置文件，添加你的 Prometheus 地址
vim ~/.prometheus-mcp/config.yaml
```

### 3. 启动服务

#### 方式一：uvx 直接运行（推荐，免安装）

```bash
# stdio 模式（用于 Hermes Agent 本地集成，推荐）
uvx prometheus-mcp-server --transport stdio

# HTTP 模式（独立服务，用于远程或调试）
uvx prometheus-mcp-server --host 0.0.0.0 --port 8000
```

> 首次运行 `uvx` 会自动从 PyPI 下载并执行，无需手动 `pip install`。

#### 方式二：本地安装后运行

```bash
cd /root/prometheus-mcp-server
pip install -e .

# HTTP 模式（默认，独立服务）
prometheus-mcp-server --host 0.0.0.0 --port 8000

# stdio 模式（本地集成）
prometheus-mcp-server --transport stdio

# 详细日志
prometheus-mcp-server -v
```

### 4. 配置 Hermes Agent

#### stdio 模式（推荐，无需启动独立服务）

在 `~/.hermes/config.yaml` 中添加：

```yaml
mcp_servers:
  prometheus:
    command: "uvx"
    args: ["prometheus-mcp-server", "--transport", "stdio"]
    timeout: 60
    connect_timeout: 30
```

重启 Hermes Agent 后，工具会自动注册为 `mcp_prometheus_*`。

#### HTTP 模式（独立服务）

先启动 HTTP 服务（见上方启动服务），然后在 `~/.hermes/config.yaml` 中添加：

```yaml
mcp_servers:
  prometheus:
    url: "http://localhost:8000"  # MCP Server 地址
    timeout: 60
    connect_timeout: 30
```

重启 Hermes Agent 后，工具会自动注册为 `mcp_prometheus_*`。

## 📋 可用工具

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

## 💬 使用示例

配置完成后，可以通过自然语言向机器人提问：

```
用户: "帮我查一下 production 环境当前有多少服务是 up 的"
→ Agent 调用 mcp_prometheus_query(query="up", env="production")

用户: "过去 1 小时 production 的 CPU 使用率趋势如何？"
→ Agent 调用 mcp_prometheus_query_range(
      query="100 - (avg by(instance) (rate(node_cpu_seconds_total{mode='idle'}[5m])) * 100)",
      env="production",
      start="1h ago",
      step="5m"
    )

用户: "production 环境有哪些告警正在触发？"
→ Agent 调用 mcp_prometheus_list_alerts(env="production")

用户: "staging 环境的 node_exporter targets 状态正常吗？"
→ Agent 调用 mcp_prometheus_list_targets(env="staging")
```

## ⚙️ 配置说明

### 环境配置

```yaml
environments:
  production:
    url: "http://prometheus.prod:9090"
    auth:
      type: "none"  # none | basic | bearer
      # basic 认证:
      # type: "basic"
      # username: "admin"
      # password: "secret"
      # bearer 认证:
      # type: "bearer"
      # token: "your-token"
    timeout: 30        # 请求超时（秒）
    verify_ssl: true   # SSL 证书验证
```

### 启动参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | `~/.prometheus-mcp/config.yaml` | 配置文件路径 |
| `--host` | `0.0.0.0` | HTTP 监听地址 |
| `--port` | `8000` | HTTP 监听端口 |
| `--transport` | `http` | 传输模式（http/stdio） |
| `--verbose`, `-v` | `false` | 详细日志 |

## 🔧 开发

```bash
# 安装开发依赖
pip install -e ".[dev]"

# 运行测试
pytest

# 代码检查
ruff check src/
mypy src/
```

## 📁 项目结构

```
prometheus-mcp-server/
├── pyproject.toml                 # 项目配置
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
