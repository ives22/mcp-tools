import {
  JenkinsClient,
  JenkinsHttpError,
  buildSelectorList,
  loadConfigFromEnv
} from "./jenkins-client.mjs";
import fs from "node:fs";
import path from "node:path";

const SERVER_NAME = "jenkins-local";
const SERVER_VERSION = "0.1.0";
const JSON_RPC_ERROR = {
  METHOD_NOT_FOUND: -32601,
  INVALID_PARAMS: -32602,
  INTERNAL_ERROR: -32603
};

loadDotEnvFile(path.resolve(process.cwd(), ".env"));
const client = new JenkinsClient(loadConfigFromEnv());
const BUILD_SELECTORS = buildSelectorList();

const TOOL_DEFINITIONS = [
  {
    name: "jenkins_list_jobs",
    title: "List Jenkins Jobs",
    description:
      "List Jenkins items from the root or a specific folder. Supports recursive traversal across nested folders.",
    inputSchema: {
      type: "object",
      properties: {
        folderPath: {
          type: "string",
          description: 'Optional folder path like "team-a/services". Omit to list from Jenkins root.'
        },
        recursive: {
          type: "boolean",
          description: "When true, recursively traverse nested folders.",
          default: false
        },
        nameFilter: {
          type: "string",
          description: "Optional case-insensitive filter applied to name and fullName."
        },
        includeContainers: {
          type: "boolean",
          description:
            "When true, include folder-like container items in the result alongside runnable jobs.",
          default: true
        }
      },
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true
    }
  },
  {
    name: "jenkins_get_job",
    title: "Get Jenkins Job",
    description:
      "Get a Jenkins job detail record, including parameter definitions and last build references.",
    inputSchema: {
      type: "object",
      properties: {
        jobPath: {
          type: "string",
          description: 'Slash-separated Jenkins job path like "folder/service-deploy".'
        }
      },
      required: ["jobPath"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true
    }
  },
  {
    name: "jenkins_trigger_build",
    title: "Trigger Jenkins Build",
    description:
      "Trigger a Jenkins build, optionally with parameters, and optionally wait until the build finishes.",
    inputSchema: {
      type: "object",
      properties: {
        jobPath: {
          type: "string",
          description: 'Slash-separated Jenkins job path like "folder/service-deploy".'
        },
        parameters: {
          type: "object",
          description: "Optional build parameters as key/value pairs."
        },
        waitForCompletion: {
          type: "boolean",
          description: "When true, wait for queueing, build start, and build completion.",
          default: false
        },
        timeoutMs: {
          type: "integer",
          minimum: 1,
          description: "Maximum wait time when waitForCompletion is true."
        },
        pollIntervalMs: {
          type: "integer",
          minimum: 1,
          description: "Polling interval for queue/build status while waiting."
        },
        includeLogOnFailure: {
          type: "boolean",
          description: "When waiting and the build fails, attach the tail of the build log.",
          default: false
        },
        logTailLines: {
          type: "integer",
          minimum: 1,
          description: "Number of log tail lines to return when includeLogOnFailure is true."
        }
      },
      required: ["jobPath"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: false,
      destructiveHint: false,
      idempotentHint: false,
      openWorldHint: true
    }
  },
  {
    name: "jenkins_get_build_status",
    title: "Get Jenkins Build Status",
    description:
      "Fetch normalized Jenkins build status for a specific build number or a selector like lastBuild.",
    inputSchema: {
      type: "object",
      properties: {
        jobPath: {
          type: "string",
          description: 'Slash-separated Jenkins job path like "folder/service-deploy".'
        },
        buildNumber: {
          type: "integer",
          minimum: 1,
          description: "Specific Jenkins build number."
        },
        buildSelector: {
          type: "string",
          enum: BUILD_SELECTORS,
          description: 'Build selector to resolve when buildNumber is omitted. Defaults to "lastBuild".'
        }
      },
      required: ["jobPath"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true
    }
  },
  {
    name: "jenkins_get_build_log",
    title: "Get Jenkins Build Log",
    description:
      "Read Jenkins build logs in tail, full, or progressive mode to support failure investigation.",
    inputSchema: {
      type: "object",
      properties: {
        jobPath: {
          type: "string",
          description: 'Slash-separated Jenkins job path like "folder/service-deploy".'
        },
        buildNumber: {
          type: "integer",
          minimum: 1,
          description: "Specific Jenkins build number."
        },
        buildSelector: {
          type: "string",
          enum: BUILD_SELECTORS,
          description: 'Build selector to resolve when buildNumber is omitted. Defaults to "lastBuild".'
        },
        mode: {
          type: "string",
          enum: ["tail", "full", "progressive"],
          description:
            'Log read mode. "tail" returns the last N lines, "full" returns the full log up to maxBytes, and "progressive" returns a chunk from startByte.',
          default: "tail"
        },
        tailLines: {
          type: "integer",
          minimum: 1,
          description: 'Number of lines returned in "tail" mode.'
        },
        startByte: {
          type: "integer",
          minimum: 0,
          description: 'Byte offset used in "progressive" mode.'
        },
        maxBytes: {
          type: "integer",
          minimum: 1,
          description: 'Maximum in-memory log size for "tail" and "full" modes.'
        }
      },
      required: ["jobPath"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true
    }
  },
  {
    name: "jenkins_analyze_failed_build_context",
    title: "Analyze Failed Jenkins Build Context",
    description:
      "Aggregate build metadata, test report data, failure highlights, and a log excerpt for failed-build analysis.",
    inputSchema: {
      type: "object",
      properties: {
        jobPath: {
          type: "string",
          description: 'Slash-separated Jenkins job path like "folder/service-deploy".'
        },
        buildNumber: {
          type: "integer",
          minimum: 1,
          description: "Specific Jenkins build number."
        },
        buildSelector: {
          type: "string",
          enum: BUILD_SELECTORS,
          description: 'Build selector to resolve when buildNumber is omitted. Defaults to "lastBuild".'
        },
        logTailLines: {
          type: "integer",
          minimum: 1,
          description: "Number of log tail lines included in the returned context."
        },
        maxBytes: {
          type: "integer",
          minimum: 1,
          description: "Maximum number of log bytes retained while collecting the excerpt."
        }
      },
      required: ["jobPath"],
      additionalProperties: false
    },
    annotations: {
      readOnlyHint: true,
      destructiveHint: false,
      idempotentHint: true,
      openWorldHint: true
    }
  }
];

function send(message) {
  process.stdout.write(`${JSON.stringify(message)}\n`);
}

function sendResult(id, result) {
  send({ jsonrpc: "2.0", id, result });
}

function sendError(id, code, message, data) {
  const error = { code, message };
  if (data !== undefined) {
    error.data = data;
  }
  send({ jsonrpc: "2.0", id, error });
}

function buildToolResult(toolName, payload) {
  return {
    content: [
      {
        type: "text",
        text: summarizeToolPayload(toolName, payload)
      }
    ],
    structuredContent: payload
  };
}

function summarizeToolPayload(toolName, payload) {
  switch (toolName) {
    case "jenkins_list_jobs":
      return `Listed ${payload.total} Jenkins items from ${payload.scope} (recursive=${payload.recursive}).`;
    case "jenkins_get_job":
      return `Loaded job ${payload.fullName} with ${payload.parameters.length} parameter definitions.`;
    case "jenkins_trigger_build":
      if (payload.buildNumber) {
        return `Triggered ${payload.jobPath} queue=${payload.queueId} build=${payload.buildNumber} status=${payload.status}.`;
      }
      return `Triggered ${payload.jobPath} queue=${payload.queueId}.`;
    case "jenkins_get_build_status":
      return `Build ${payload.jobPath} #${payload.buildNumber} is ${payload.status} (${payload.result ?? "no-result"}).`;
    case "jenkins_get_build_log":
      return `Fetched ${payload.mode} log for ${payload.jobPath} #${payload.buildNumber}.`;
    case "jenkins_analyze_failed_build_context":
      return `Collected failure context for ${payload.jobPath} #${payload.buildNumber} with status ${payload.status}.`;
    default:
      return JSON.stringify(payload, null, 2);
  }
}

async function handleToolCall(id, params) {
  const name = params?.name;
  const args = asObject(params?.arguments);

  switch (name) {
    case "jenkins_list_jobs":
      sendResult(id, buildToolResult(name, await client.listJobs(args)));
      return;
    case "jenkins_get_job":
      sendResult(id, buildToolResult(name, await client.getJob(args.jobPath)));
      return;
    case "jenkins_trigger_build":
      sendResult(id, buildToolResult(name, await client.triggerBuild(args.jobPath, args)));
      return;
    case "jenkins_get_build_status":
      sendResult(id, buildToolResult(name, await client.getBuildStatus(args.jobPath, args)));
      return;
    case "jenkins_get_build_log":
      sendResult(id, buildToolResult(name, await client.getBuildLog(args.jobPath, args)));
      return;
    case "jenkins_analyze_failed_build_context":
      sendResult(
        id,
        buildToolResult(name, await client.analyzeFailedBuildContext(args.jobPath, args))
      );
      return;
    default:
      sendError(id, JSON_RPC_ERROR.INVALID_PARAMS, `Unknown tool: ${name ?? ""}`);
  }
}

async function handleRequest(message) {
  const { id, method, params } = message;

  if (method === "initialize") {
    sendResult(id, {
      protocolVersion: params?.protocolVersion ?? "2025-11-25",
      capabilities: { tools: {} },
      serverInfo: {
        name: SERVER_NAME,
        version: SERVER_VERSION
      },
      instructions:
        "This MCP server exposes Jenkins tools for listing jobs, triggering parameterized builds, reading logs, tracking build status, and collecting failed-build context."
    });
    return;
  }

  if (method === "ping") {
    sendResult(id, {});
    return;
  }

  if (method === "tools/list") {
    sendResult(id, { tools: TOOL_DEFINITIONS });
    return;
  }

  if (method === "tools/call") {
    try {
      await handleToolCall(id, params);
    } catch (error) {
      handleToolError(id, error);
    }
    return;
  }

  if (id !== undefined) {
    sendError(id, JSON_RPC_ERROR.METHOD_NOT_FOUND, `Method not found: ${method}`);
  }
}

function handleToolError(id, error) {
  if (error instanceof JenkinsHttpError) {
    sendError(id, JSON_RPC_ERROR.INTERNAL_ERROR, error.message, {
      statusCode: error.statusCode,
      responseBody: error.responseBody
    });
    return;
  }

  sendError(
    id,
    JSON_RPC_ERROR.INVALID_PARAMS,
    error instanceof Error ? error.message : String(error)
  );
}

function asObject(value) {
  if (value === undefined || value === null) {
    return {};
  }
  if (typeof value !== "object" || Array.isArray(value)) {
    throw new Error("Tool arguments must be an object.");
  }
  return value;
}

function safeParseJson(line) {
  try {
    return JSON.parse(line);
  } catch {
    return null;
  }
}

process.stdin.setEncoding("utf8");
let buffer = "";

process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let newlineIndex = buffer.indexOf("\n");
  while (newlineIndex >= 0) {
    const line = buffer.slice(0, newlineIndex).trim();
    buffer = buffer.slice(newlineIndex + 1);
    if (line.length > 0) {
      const message = safeParseJson(line);
      if (message) {
        void handleRequest(message);
      }
    }
    newlineIndex = buffer.indexOf("\n");
  }
});

function loadDotEnvFile(filePath) {
  if (!fs.existsSync(filePath)) {
    return;
  }

  const lines = fs.readFileSync(filePath, "utf8").split(/\r?\n/);
  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) {
      continue;
    }

    const separatorIndex = line.indexOf("=");
    if (separatorIndex <= 0) {
      continue;
    }

    const key = line.slice(0, separatorIndex).trim();
    if (!key || process.env[key] !== undefined) {
      continue;
    }

    let value = line.slice(separatorIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    process.env[key] = value;
  }
}
