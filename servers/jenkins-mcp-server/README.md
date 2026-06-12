# Jenkins MCP Server

一个基于本地 `stdio` 的 Jenkins MCP Server，通过 Jenkins HTTP API 提供常用操作能力，适合在 `Codex` 或 `Claude Code` 中直接作为本地 MCP 工具使用。

## 功能概览

- 查询 Jenkins 根目录或指定 folder 下的项目
- 递归列出所有 folder / job
- 查询单个 job 的详情、参数定义、最近构建信息
- 触发普通构建或参数化构建
- 可选等待构建进入执行、等待构建完成
- 查询构建状态
- 读取构建日志，支持尾部日志、全量日志、增量日志
- 聚合失败构建上下文，便于大模型直接分析失败原因

## 环境要求

- Node.js 22 及以上
- 一个可访问目标 Jenkins 的账号和 API Token

当前机器上的 `node` 路径是:

```bash
/usr/local/bin/node
```

## 配置说明

服务启动时会先读取仓库根目录下的 `.env` 文件；如果系统环境变量里已经有同名配置，则系统环境变量优先。

可用环境变量如下：

- `JENKINS_BASE_URL`：Jenkins 地址，例如 `https://jenkins.example.com`
- `JENKINS_USER`：Jenkins 用户名
- `JENKINS_API_TOKEN`：Jenkins API Token
- `JENKINS_TIMEOUT_MS`：单次请求超时时间，默认 `30000`
- `JENKINS_POLL_INTERVAL_MS`：等待队列/构建时的轮询间隔，默认 `3000`

建议先复制一份示例配置：

```bash
cp .env.example .env
```

然后把 [.env.example](/Users/liyj/MCP/jenkins-mcp-server/.env.example) 里的占位值替换成真实 Jenkins 配置。

## 本地启动

```bash
npm run start
```

这个服务使用基于换行的 JSON-RPC over stdio，适合被本地 MCP 客户端以子进程方式拉起。

## 工具列表

### `jenkins_list_jobs`

用途：

- 列出 Jenkins 根目录下的项目
- 列出指定 folder 下的项目
- 递归列出所有子 folder / job

输入参数：

- `folderPath?`：folder 路径，例如 `team-a/services`
- `recursive?`：是否递归列出子 folder，默认 `false`
- `nameFilter?`：按名称模糊过滤
- `includeContainers?`：是否把 folder / multibranch 这类容器节点也返回，默认 `true`

### `jenkins_get_job`

用途：

- 查询单个 job 的详情
- 获取参数定义
- 获取最近一次构建、最近成功构建、最近失败构建等引用信息

输入参数：

- `jobPath`：job 路径，例如 `team-a/service-deploy`

### `jenkins_trigger_build`

用途：

- 触发普通构建
- 触发参数化构建
- 可选等待构建完成

输入参数：

- `jobPath`：job 路径
- `parameters?`：构建参数对象
- `waitForCompletion?`：是否等待构建完成，默认 `false`
- `timeoutMs?`：等待超时时间
- `pollIntervalMs?`：轮询间隔
- `includeLogOnFailure?`：等待构建完成且失败时，是否自动带回尾部日志
- `logTailLines?`：失败时附带的日志行数

### `jenkins_get_build_status`

用途：

- 查询某次构建状态
- 或按 `lastBuild`、`lastSuccessfulBuild` 之类的选择器查询

输入参数：

- `jobPath`：job 路径
- `buildNumber?`：构建号
- `buildSelector?`：可选值：
  - `lastBuild`
  - `lastCompletedBuild`
  - `lastFailedBuild`
  - `lastSuccessfulBuild`
  - `lastUnsuccessfulBuild`

如果未传 `buildNumber`，默认按 `lastBuild` 查询。

### `jenkins_get_build_log`

用途：

- 读取构建尾部日志
- 读取全量日志
- 读取增量日志

输入参数：

- `jobPath`：job 路径
- `buildNumber?`：构建号
- `buildSelector?`：未传构建号时使用的选择器
- `mode?`：`tail`、`full`、`progressive`
- `tailLines?`：`tail` 模式返回的日志行数
- `startByte?`：`progressive` 模式的起始字节偏移
- `maxBytes?`：内存中允许保留的最大日志字节数

### `jenkins_analyze_failed_build_context`

用途：

- 聚合失败构建分析所需上下文
- 返回构建元数据、测试报告摘要、疑似失败关键行、日志片段

输入参数：

- `jobPath`：job 路径
- `buildNumber?`：构建号
- `buildSelector?`：未传构建号时使用的选择器
- `logTailLines?`：附带日志行数
- `maxBytes?`：日志抓取的内存上限

## 在 Codex 中使用

这个仓库已经带了项目级 [.mcp.json](/Users/liyj/MCP/jenkins-mcp-server/.mcp.json)：

```json
{
  "mcpServers": {
    "jenkins-local": {
      "cwd": ".",
      "command": "node",
      "args": [
        "./src/server.mjs"
      ]
    }
  }
}
```

如果你是在这个仓库目录中打开 Codex，并且仓库已被信任，通常可以直接基于这个 `.mcp.json` 使用。

如果你希望全局固定配置，也可以手动写入 `~/.codex/config.toml`：

```toml
[mcp_servers.jenkins-local]
type = "stdio"
command = "/usr/local/bin/node"
args = ["/Users/liyj/MCP/jenkins-mcp-server/src/server.mjs"]
env_vars = [
  "JENKINS_BASE_URL",
  "JENKINS_USER",
  "JENKINS_API_TOKEN",
  "JENKINS_TIMEOUT_MS",
  "JENKINS_POLL_INTERVAL_MS"
]
startup_timeout_sec = 120

[mcp_servers.jenkins-local.env]
JENKINS_BASE_URL = "https://your-jenkins.example.com"
JENKINS_USER = "your-user"
JENKINS_API_TOKEN = "your-api-token"
JENKINS_TIMEOUT_MS = "30000"
JENKINS_POLL_INTERVAL_MS = "3000"
```

说明：

- `command`：本机 `node` 路径，当前机器可用的是 `/usr/local/bin/node`
- `args`：MCP server 启动入口
- `env_vars`：声明这个 MCP server 会用到哪些环境变量
- `[mcp_servers.jenkins-local.env]`：可以直接把变量写在这里

配置完成后建议：

1. 重启 Codex
2. 新开一个线程
3. 先调用 `jenkins_list_jobs`
4. 再根据需要调用 `jenkins_get_job`、`jenkins_trigger_build` 等工具

Codex 中的典型使用方式：

- “列出 Jenkins 根目录下所有 job”
- “列出 folder `team-a/services` 下的所有 job，并递归”
- “触发 `team-a/service-deploy`，参数 `ENV=prod`，并等待构建完成”
- “读取 `team-a/service-deploy` 最近一次失败构建的尾部日志”
- “分析 `team-a/service-deploy` 最近一次失败构建原因”

## 在 Claude Code 中使用

推荐直接用 `claude mcp add` 配置，这也是 `Claude Code` 当前 CLI 暴露的标准方式。

先确认本机命令存在：

```bash
which claude
```

当前机器上的 `claude` 路径是：

```bash
/usr/local/bin/claude
```

### 方式一：按项目作用域添加

在当前仓库目录执行：

```bash
claude mcp add -s project \
  -e JENKINS_BASE_URL=https://your-jenkins.example.com \
  -e JENKINS_USER=your-user \
  -e JENKINS_API_TOKEN=your-api-token \
  -e JENKINS_TIMEOUT_MS=30000 \
  -e JENKINS_POLL_INTERVAL_MS=3000 \
  jenkins-local -- \
  /usr/local/bin/node /Users/liyj/MCP/jenkins-mcp-server/src/server.mjs
```

说明：

- `-s project`：表示只在当前项目下生效
- `-e`：把 Jenkins 相关环境变量一并配置给这个 MCP server
- `jenkins-local`：MCP server 名称，可自定义
- `--` 后面是实际启动命令

### 方式二：按用户全局作用域添加

如果希望所有项目都能用：

```bash
claude mcp add -s user \
  -e JENKINS_BASE_URL=https://your-jenkins.example.com \
  -e JENKINS_USER=your-user \
  -e JENKINS_API_TOKEN=your-api-token \
  -e JENKINS_TIMEOUT_MS=30000 \
  -e JENKINS_POLL_INTERVAL_MS=3000 \
  jenkins-local -- \
  /usr/local/bin/node /Users/liyj/MCP/jenkins-mcp-server/src/server.mjs
```

添加完成后可以检查：

```bash
claude mcp list
claude mcp get jenkins-local
```

然后重启 Claude Code，或者新开一个会话再使用。

Claude Code 中的典型使用方式：

- “列出 Jenkins 所有 folder 和 job”
- “查看 `folder-a/deploy-prod` 的参数定义”
- “触发 `folder-a/deploy-prod`，参数 `branch=main`，等待完成”
- “读取刚才失败构建的日志尾部”
- “分析这次 Jenkins 构建失败原因”

## 使用建议

- 如果日志很大，优先用 `jenkins_get_build_log` 的 `tail` 或 `progressive` 模式
- 如果只是想一把拿到失败分析上下文，优先用 `jenkins_analyze_failed_build_context`
- 如果你希望一次调用就完成触发和等待，使用 `jenkins_trigger_build` 并设置 `waitForCompletion=true`
- 参数化构建时，`parameters` 直接传对象即可，例如：

```json
{
  "jobPath": "team-a/service-deploy",
  "parameters": {
    "ENV": "prod",
    "BRANCH": "main"
  },
  "waitForCompletion": true,
  "includeLogOnFailure": true
}
```

## 说明

- job 路径统一使用斜杠分隔，例如 `folder-a/folder-b/deploy-prod`
- 目前服务只对接单个 Jenkins 实例
- 已自动处理 Jenkins crumb / CSRF
- 日志可能很大，不建议默认拉全量日志
- 当前实现更适合作为本地 MCP server 使用，不依赖外部 npm 包安装
