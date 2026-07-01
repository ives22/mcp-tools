# ACR MCP Server

一个基于本地 `stdio` 的阿里云容器镜像服务（ACR 个人版）MCP Server，通过 ACR OpenAPI 提供命名空间、镜像仓库、镜像 Tag 的查询能力，适合在 Codex 或 Claude Code 中作为本地 MCP 工具使用。

## 功能概览

- 查询所有命名空间
- 查询镜像仓库列表（支持按命名空间过滤）
- 查询单个仓库的详细信息（类型、状态、拉取域名等）
- 查询镜像仓库下的所有 Tag（支持分页）
- **检查指定 Tag 是否存在**（CI/CD 场景核心能力）
- 查询单个 Tag 的详细信息（imageId、digest、大小、时间戳等）

## 环境要求

- Python >= 3.10
- 拥有 ACR 读取权限的阿里云 AccessKey

## 安装

```bash
cd servers/acr-mcp-server
pip install -e .
```

安装完成后，可通过命令行验证：

```bash
acr-mcp-server --help
```

## 配置

通过环境变量配置阿里云凭证：

```bash
# 必需
export ALIBABA_CLOUD_ACCESS_KEY_ID="your_access_key_id"
export ALIBABA_CLOUD_ACCESS_KEY_SECRET="your_access_key_secret"

# 可选（默认 ap-southeast-1）
export ACR_REGION_ID="ap-southeast-1"
```

也可以复制 `.env.example` 为 `.env`，填入凭证后 `source .env`。

## 工具列表

| 工具名 | 说明 | 必填参数 |
|--------|------|----------|
| `acr_list_namespaces` | 列出所有命名空间 | — |
| `acr_list_repos` | 列出镜像仓库（可按命名空间过滤） | — |
| `acr_get_repo_info` | 获取仓库详情 | `namespace`, `repo_name` |
| `acr_list_tags` | 列出镜像所有 Tag（分页） | `namespace`, `repo_name` |
| `acr_check_tag_exists` | 检查指定 Tag 是否存在 | `namespace`, `repo_name`, `tag` |
| `acr_get_tag_info` | 获取单个 Tag 的详细信息 | `namespace`, `repo_name`, `tag` |

### acr_list_namespaces

列出 ACR 实例下的所有命名空间。

**参数：** 无

### acr_list_repos

列出镜像仓库，支持按命名空间过滤和分页。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `namespace` | string | 否 | 按命名空间名称过滤，不填则列出所有 |
| `page` | int | 否 | 页码（默认 1） |
| `page_size` | int | 否 | 每页数量（默认 30，最大 100） |

### acr_get_repo_info

获取指定镜像仓库的详细信息，包括仓库类型、状态、拉取域名、创建时间等。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `namespace` | string | 是 | 命名空间名称 |
| `repo_name` | string | 是 | 仓库名称 |

### acr_list_tags

列出指定仓库下的所有镜像 Tag，支持分页查询。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `namespace` | string | 是 | 命名空间名称 |
| `repo_name` | string | 是 | 仓库名称 |
| `page` | int | 否 | 页码（默认 1） |
| `page_size` | int | 否 | 每页数量（默认 30，最大 100） |

### acr_check_tag_exists

检查指定镜像 Tag 是否存在。存在时返回 `exists: true` 及 Tag 详情（imageId、digest、大小等），不存在时返回 `exists: false`。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `namespace` | string | 是 | 命名空间名称 |
| `repo_name` | string | 是 | 仓库名称 |
| `tag` | string | 是 | 要检查的 Tag 名称（如 `v1.2.3`、`latest`） |

### acr_get_tag_info

获取指定 Tag 的详细信息，包括 imageId、digest、镜像大小、创建和更新时间。

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `namespace` | string | 是 | 命名空间名称 |
| `repo_name` | string | 是 | 仓库名称 |
| `tag` | string | 是 | Tag 名称 |

## 在 Codex 中使用

### 方式一：项目级 `.mcp.json`（推荐）

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "acr": {
      "command": "acr-mcp-server",
      "env": {
        "ALIBABA_CLOUD_ACCESS_KEY_ID": "your_access_key_id",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your_access_key_secret",
        "ACR_REGION_ID": "ap-southeast-1"
      }
    }
  }
}
```

如果你不想安装到全局，也可以通过 `uvx` 直接运行（无需 `pip install`）：

```json
{
  "mcpServers": {
    "acr": {
      "command": "uvx",
      "args": ["acr-mcp-server"],
      "env": {
        "ALIBABA_CLOUD_ACCESS_KEY_ID": "your_access_key_id",
        "ALIBABA_CLOUD_ACCESS_KEY_SECRET": "your_access_key_secret",
        "ACR_REGION_ID": "ap-southeast-1"
      }
    }
  }
}
```

### 方式二：全局配置 `~/.codex/config.toml`

如果希望所有项目都能使用，写入全局配置：

```toml
[mcp_servers.acr]
type = "stdio"
command = "acr-mcp-server"
env_vars = [
  "ALIBABA_CLOUD_ACCESS_KEY_ID",
  "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
  "ACR_REGION_ID"
]
startup_timeout_sec = 30
```

使用前需确保环境变量已导出（如写在 `~/.zshrc` 中）。

### Codex 中的典型用法

配置完成后重启 Codex，新开线程即可使用：

- "列出 ACR 下所有命名空间"
- "查看 relax_many_game 命名空间下有哪些镜像仓库"
- "查看 relax_many_game/5117 仓库的详细信息"
- "列出 relax_many_game/5117 最近 10 个镜像 Tag"
- "检查 relax_many_game/5117 的 tag `v1.2.3` 是否存在"
- "查看 relax_many_game/5117:v1.2.3 的镜像 digest 和大小"

## 在 Claude Code 中使用

### 方式一：按项目作用域添加

```bash
claude mcp add -s project \
  -e ALIBABA_CLOUD_ACCESS_KEY_ID=your_access_key_id \
  -e ALIBABA_CLOUD_ACCESS_KEY_SECRET=your_access_key_secret \
  -e ACR_REGION_ID=ap-southeast-1 \
  acr -- acr-mcp-server
```

### 方式二：按用户全局作用域添加

```bash
claude mcp add -s user \
  -e ALIBABA_CLOUD_ACCESS_KEY_ID=your_access_key_id \
  -e ALIBABA_CLOUD_ACCESS_KEY_SECRET=your_access_key_secret \
  -e ACR_REGION_ID=ap-southeast-1 \
  acr -- acr-mcp-server
```

添加完成后可以检查：

```bash
claude mcp list
claude mcp get acr
```

### Claude Code 中的典型用法

配置完成后在 Claude Code 中直接对话：

- "帮我查下 ACR 上有哪些命名空间"
- "看下 relax_many_game 下 5117 这个仓库的 tag `abc123` 是否存在"
- "列出 5117 仓库最新的 5 个 tag"

## 在 Hermes Agent 中使用

编辑 Hermes Agent 配置文件 `~/.hermes/config.yaml`，在 `mcp_servers` 下添加 ACR 配置：

```yaml
mcp_servers:
  acr:
    command: "acr-mcp-server"
    env:
      ALIBABA_CLOUD_ACCESS_KEY_ID: "your_access_key_id"
      ALIBABA_CLOUD_ACCESS_KEY_SECRET: "your_access_key_secret"
      ACR_REGION_ID: "ap-southeast-1"
    timeout: 60
    connect_timeout: 30
```

如果环境变量已在 `~/.zshrc` 中导出，可以省略 `env` 块，Hermes Agent 会自动继承：

```yaml
mcp_servers:
  acr:
    command: "acr-mcp-server"
    timeout: 60
    connect_timeout: 30
```

配置完成后重启 Hermes Agent 即可使用。

## 命令行参数

```bash
acr-mcp-server [OPTIONS]
```

| 参数 | 说明 |
|------|------|
| `--verbose` / `-v` | 开启调试日志 |
| `--region REGION` | 覆盖 ACR 地域（默认读 `ACR_REGION_ID` 环境变量） |
| `--access-key-id KEY` | 覆盖 Access Key ID |
| `--access-key-secret SECRET` | 覆盖 Access Key Secret |

## 技术说明

本 Server 使用阿里云 SDK `alibabacloud_cr20160607` 的底层 `call_api()` 方法发起请求，而非 SDK 的高层封装方法。这是因为该 SDK 的 Response 模型（如 `GetRepoTagsResponse`）存在已知缺陷 —— `from_map()` 仅映射 `headers`，丢弃了 `body` 中的实际数据。通过 `call_api()` 直接获取原始响应并手动解析 JSON body 来规避此问题。
