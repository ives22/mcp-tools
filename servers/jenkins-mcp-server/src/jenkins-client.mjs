const DEFAULT_TIMEOUT_MS = 30_000;
const DEFAULT_POLL_INTERVAL_MS = 3_000;
const BUILD_SELECTOR_SET = new Set([
  "lastBuild",
  "lastCompletedBuild",
  "lastFailedBuild",
  "lastSuccessfulBuild",
  "lastUnsuccessfulBuild"
]);
const FAILURE_PATTERNS = [
  /error/i,
  /exception/i,
  /fail(ed|ure)?/i,
  /fatal/i,
  /timed?\s*out/i,
  /terminated/i,
  /abort(ed)?/i,
  /cannot /i
];

export function loadConfigFromEnv(env = process.env) {
  const baseUrl = env.JENKINS_BASE_URL?.trim();
  const username = env.JENKINS_USER?.trim();
  const apiToken = env.JENKINS_API_TOKEN?.trim();

  if (!baseUrl) {
    throw new Error("Missing required environment variable: JENKINS_BASE_URL");
  }
  if (!username) {
    throw new Error("Missing required environment variable: JENKINS_USER");
  }
  if (!apiToken) {
    throw new Error("Missing required environment variable: JENKINS_API_TOKEN");
  }

  return {
    baseUrl,
    username,
    apiToken,
    timeoutMs: parsePositiveInteger(env.JENKINS_TIMEOUT_MS, DEFAULT_TIMEOUT_MS),
    pollIntervalMs: parsePositiveInteger(
      env.JENKINS_POLL_INTERVAL_MS,
      DEFAULT_POLL_INTERVAL_MS
    )
  };
}

export function buildSelectorList() {
  return Array.from(BUILD_SELECTOR_SET);
}

export class JenkinsClient {
  constructor(config) {
    this.baseUrl = normalizeBaseUrl(config.baseUrl);
    this.username = config.username;
    this.apiToken = config.apiToken;
    this.defaultTimeoutMs = config.timeoutMs ?? DEFAULT_TIMEOUT_MS;
    this.defaultPollIntervalMs = config.pollIntervalMs ?? DEFAULT_POLL_INTERVAL_MS;
    this.authorizationHeader = `Basic ${Buffer.from(
      `${this.username}:${this.apiToken}`,
      "utf8"
    ).toString("base64")}`;
    this.crumb = null;
    this.crumbDisabled = false;
    this.crumbPromise = null;
  }

  async listJobs(options = {}) {
    const recursive = options.recursive === true;
    const nameFilter = normalizeOptionalString(options.nameFilter)?.toLowerCase() ?? null;
    const includeContainers = options.includeContainers !== false;
    const seen = new Set();
    const items = [];

    const walk = async (folderPath) => {
      const data = await this.getJson(this.containerApiPath(folderPath), {
        tree: "jobs[name,fullName,url,_class,buildable,color]"
      });
      const jobs = Array.isArray(data.jobs) ? data.jobs : [];

      for (const job of jobs) {
        const item = normalizeJobListItem(job);
        if (!item.fullName || seen.has(item.fullName)) {
          continue;
        }

        seen.add(item.fullName);
        const matchesFilter =
          nameFilter === null ||
          item.name.toLowerCase().includes(nameFilter) ||
          item.fullName.toLowerCase().includes(nameFilter);

        if (matchesFilter && (includeContainers || item.isContainer === false)) {
          items.push(item);
        }

        if (recursive && item.isContainer) {
          await walk(item.fullName);
        }
      }
    };

    const folderPath = normalizeOptionalJobPath(options.folderPath);
    await walk(folderPath);

    items.sort((left, right) => left.fullName.localeCompare(right.fullName));
    return {
      scope: folderPath ?? "root",
      recursive,
      total: items.length,
      items
    };
  }

  async getJob(jobPath) {
    const normalizedPath = normalizeRequiredJobPath(jobPath, "jobPath");
    const data = await this.getJson(`${this.jobBasePath(normalizedPath)}/api/json`, {
      tree: [
        "name",
        "displayName",
        "fullName",
        "fullDisplayName",
        "description",
        "url",
        "_class",
        "buildable",
        "inQueue",
        "nextBuildNumber",
        "color",
        "healthReport[description,score,iconClassName]",
        "property[parameterDefinitions[name,description,_class,type,choices,defaultParameterValue[value]]]",
        "actions[parameterDefinitions[name,description,_class,type,choices,defaultParameterValue[value]]]",
        "lastBuild[number,url]",
        "lastCompletedBuild[number,url]",
        "lastFailedBuild[number,url]",
        "lastSuccessfulBuild[number,url]",
        "lastUnsuccessfulBuild[number,url]"
      ].join(",")
    });

    return {
      name: data.name ?? normalizedPath.split("/").at(-1),
      displayName: data.displayName ?? data.name ?? normalizedPath,
      fullName: data.fullName ?? normalizedPath,
      fullDisplayName: data.fullDisplayName ?? data.fullName ?? normalizedPath,
      description: data.description ?? "",
      url: data.url ?? null,
      className: data._class ?? null,
      buildable: data.buildable !== false,
      inQueue: data.inQueue === true,
      nextBuildNumber: typeof data.nextBuildNumber === "number" ? data.nextBuildNumber : null,
      color: data.color ?? null,
      healthReport: Array.isArray(data.healthReport) ? data.healthReport : [],
      parameters: extractParameterDefinitions(data),
      lastBuild: normalizeBuildReference(data.lastBuild),
      lastCompletedBuild: normalizeBuildReference(data.lastCompletedBuild),
      lastFailedBuild: normalizeBuildReference(data.lastFailedBuild),
      lastSuccessfulBuild: normalizeBuildReference(data.lastSuccessfulBuild),
      lastUnsuccessfulBuild: normalizeBuildReference(data.lastUnsuccessfulBuild)
    };
  }

  async triggerBuild(jobPath, options = {}) {
    const normalizedPath = normalizeRequiredJobPath(jobPath, "jobPath");
    const waitForCompletion = options.waitForCompletion === true;
    const timeoutMs = normalizePositiveInteger(options.timeoutMs, this.defaultTimeoutMs);
    const pollIntervalMs = normalizePositiveInteger(
      options.pollIntervalMs,
      this.defaultPollIntervalMs
    );
    const deadline = Date.now() + timeoutMs;
    const parameters = normalizeBuildParameters(options.parameters);
    const includeLogOnFailure = options.includeLogOnFailure === true;
    const logTailLines = normalizePositiveInteger(options.logTailLines, 200);
    const buildPath = `${this.jobBasePath(normalizedPath)}/${
      Object.keys(parameters).length > 0 ? "buildWithParameters" : "build"
    }`;
    const formBody =
      Object.keys(parameters).length > 0
        ? new URLSearchParams(
            Object.entries(parameters).map(([key, value]) => [key, stringifyBuildValue(value)])
          )
        : undefined;
    const response = await this.request("POST", buildPath, {
      body: formBody,
      redirect: "manual"
    });

    if (![200, 201, 202, 302].includes(response.status)) {
      throw await this.buildHttpError(response, "Failed to trigger Jenkins build");
    }

    const queueLocation = response.headers.get("location");
    if (!queueLocation) {
      throw new Error("Jenkins did not return a queue item location after triggering the build.");
    }

    const queueId = extractQueueId(queueLocation);
    const result = {
      jobPath: normalizedPath,
      queueId,
      queueUrl: absolutizeUrl(this.baseUrl, queueLocation),
      waitForCompletion
    };

    if (!waitForCompletion) {
      return result;
    }

    const queueState = await this.waitForQueueExecutable(queueId, {
      deadline,
      pollIntervalMs
    });

    if (queueState.status !== "started") {
      return {
        ...result,
        status: queueState.status,
        queueState
      };
    }

    const buildState = await this.waitForBuildCompletion(normalizedPath, queueState.buildNumber, {
      deadline,
      pollIntervalMs
    });
    const finalResult = {
      ...result,
      buildNumber: queueState.buildNumber,
      buildUrl: queueState.buildUrl,
      status: buildState.status,
      result: buildState.result,
      build: buildState.build
    };

    if (
      includeLogOnFailure &&
      ["failed", "unstable", "aborted", "timed_out", "unknown"].includes(buildState.status)
    ) {
      const log = await this.getBuildLog(normalizedPath, {
        buildNumber: queueState.buildNumber,
        mode: "tail",
        tailLines: logTailLines,
        maxBytes: 256_000
      });
      finalResult.logExcerpt = log.text;
    }

    return finalResult;
  }

  async getBuildStatus(jobPath, options = {}) {
    const normalizedPath = normalizeRequiredJobPath(jobPath, "jobPath");
    const buildNumber = await this.resolveBuildNumber(normalizedPath, options);
    const build = await this.getBuildApi(normalizedPath, buildNumber);
    return {
      jobPath: normalizedPath,
      buildNumber,
      status: mapBuildStatus(build),
      result: normalizeBuildResult(build.result),
      build
    };
  }

  async getBuildLog(jobPath, options = {}) {
    const normalizedPath = normalizeRequiredJobPath(jobPath, "jobPath");
    const buildNumber = await this.resolveBuildNumber(normalizedPath, options);
    const mode = normalizeLogMode(options.mode);
    const maxBytes = normalizePositiveInteger(options.maxBytes, 256_000);

    if (mode === "progressive") {
      const startByte = normalizeNonNegativeInteger(options.startByte, 0);
      const chunk = await this.getProgressiveLogChunk(normalizedPath, buildNumber, startByte);
      return {
        jobPath: normalizedPath,
        buildNumber,
        mode,
        text: chunk.text,
        startByte,
        nextStartByte: chunk.nextStartByte,
        hasMore: chunk.hasMore
      };
    }

    const logData =
      mode === "tail"
        ? await this.collectTailLog(normalizedPath, buildNumber, {
            tailLines: normalizePositiveInteger(options.tailLines, 200),
            maxBytes
          })
        : await this.collectFullLog(normalizedPath, buildNumber, { maxBytes });

    return {
      jobPath: normalizedPath,
      buildNumber,
      mode,
      ...logData
    };
  }

  async analyzeFailedBuildContext(jobPath, options = {}) {
    const normalizedPath = normalizeRequiredJobPath(jobPath, "jobPath");
    const buildNumber = await this.resolveBuildNumber(normalizedPath, options);
    const build = await this.getBuildApi(normalizedPath, buildNumber);
    const status = mapBuildStatus(build);
    const log = await this.getBuildLog(normalizedPath, {
      buildNumber,
      mode: "tail",
      tailLines: normalizePositiveInteger(options.logTailLines, 250),
      maxBytes: normalizePositiveInteger(options.maxBytes, 256_000)
    });
    const testReport = await this.getTestReport(normalizedPath, buildNumber);
    const suspectedFailureLines = extractFailureHighlights(log.text);

    return {
      jobPath: normalizedPath,
      buildNumber,
      status,
      result: normalizeBuildResult(build.result),
      build,
      testReport,
      suspectedFailureLines,
      logExcerpt: log.text,
      analysisReady:
        status === "failed" || status === "unstable" || status === "aborted" || status === "unknown"
    };
  }

  async resolveBuildNumber(jobPath, options = {}) {
    const buildNumber = options.buildNumber;
    const buildSelector = options.buildSelector ?? "lastBuild";

    if (buildNumber !== undefined && buildNumber !== null) {
      return normalizePositiveInteger(buildNumber, null, "buildNumber");
    }

    if (!BUILD_SELECTOR_SET.has(buildSelector)) {
      throw new Error(
        `buildSelector must be one of: ${Array.from(BUILD_SELECTOR_SET).join(", ")}`
      );
    }

    const selectorPath = `${this.jobBasePath(jobPath)}/${buildSelector}/api/json`;
    const data = await this.getJson(selectorPath, { tree: "number" });
    if (typeof data.number !== "number") {
      throw new Error(`Jenkins did not return a build number for selector ${buildSelector}.`);
    }
    return data.number;
  }

  async waitForQueueExecutable(queueId, options) {
    const pollIntervalMs = normalizePositiveInteger(
      options.pollIntervalMs,
      this.defaultPollIntervalMs
    );
    let lastState = null;

    while (Date.now() <= options.deadline) {
      const data = await this.getJson(`/queue/item/${queueId}/api/json`, {
        tree: "id,why,blocked,buildable,stuck,cancelled,task[name,url],executable[number,url]"
      });
      lastState = {
        queueId,
        why: data.why ?? null,
        blocked: data.blocked === true,
        buildable: data.buildable === true,
        stuck: data.stuck === true,
        cancelled: data.cancelled === true
      };

      if (data.cancelled === true) {
        return {
          status: "cancelled",
          ...lastState
        };
      }

      if (typeof data.executable?.number === "number") {
        return {
          status: "started",
          ...lastState,
          buildNumber: data.executable.number,
          buildUrl: data.executable.url ?? null
        };
      }

      await sleep(pollIntervalMs);
    }

    return {
      status: "timed_out",
      ...lastState
    };
  }

  async waitForBuildCompletion(jobPath, buildNumber, options) {
    const pollIntervalMs = normalizePositiveInteger(
      options.pollIntervalMs,
      this.defaultPollIntervalMs
    );
    let lastBuild = null;

    while (Date.now() <= options.deadline) {
      const build = await this.getBuildApi(jobPath, buildNumber);
      lastBuild = build;
      const status = mapBuildStatus(build);

      if (build.building !== true) {
        return {
          status,
          result: normalizeBuildResult(build.result),
          build
        };
      }

      await sleep(pollIntervalMs);
    }

    return {
      status: "timed_out",
      result: normalizeBuildResult(lastBuild?.result),
      build: lastBuild
    };
  }

  async getBuildApi(jobPath, buildNumber) {
    const buildPath = `${this.jobBasePath(jobPath)}/${buildNumber}/api/json`;
    const data = await this.getJson(buildPath, {
      tree: [
        "id",
        "number",
        "displayName",
        "fullDisplayName",
        "description",
        "url",
        "building",
        "result",
        "duration",
        "estimatedDuration",
        "timestamp",
        "queueId",
        "builtOn",
        "artifacts[fileName,relativePath]",
        "actions[causes[shortDescription],parameters[name,value]]"
      ].join(",")
    });
    return normalizeBuildDetails(data);
  }

  async getTestReport(jobPath, buildNumber) {
    try {
      const data = await this.getJson(
        `${this.jobBasePath(jobPath)}/${buildNumber}/testReport/api/json`,
        {
          tree: "failCount,skipCount,passCount,duration,suites[cases[name,className,status,errorDetails,age]]"
        }
      );
      const failedCases = [];

      if (Array.isArray(data.suites)) {
        for (const suite of data.suites) {
          for (const testCase of Array.isArray(suite.cases) ? suite.cases : []) {
            if (testCase.status && testCase.status !== "PASSED") {
              failedCases.push({
                name: testCase.name ?? null,
                className: testCase.className ?? null,
                status: testCase.status,
                errorDetails: truncateString(testCase.errorDetails ?? "", 2_000),
                age: typeof testCase.age === "number" ? testCase.age : null
              });
            }
          }
        }
      }

      return {
        failCount: typeof data.failCount === "number" ? data.failCount : 0,
        skipCount: typeof data.skipCount === "number" ? data.skipCount : 0,
        passCount: typeof data.passCount === "number" ? data.passCount : 0,
        durationSeconds: typeof data.duration === "number" ? data.duration : null,
        failedCases: failedCases.slice(0, 20)
      };
    } catch (error) {
      if (error instanceof JenkinsHttpError && error.statusCode === 404) {
        return null;
      }
      throw error;
    }
  }

  async collectFullLog(jobPath, buildNumber, options) {
    let startByte = 0;
    let text = "";
    let truncated = false;

    while (true) {
      const chunk = await this.getProgressiveLogChunk(jobPath, buildNumber, startByte);
      if (chunk.text) {
        text += chunk.text;
        if (Buffer.byteLength(text, "utf8") > options.maxBytes) {
          text = truncateByBytes(text, options.maxBytes, "end");
          truncated = true;
          startByte = chunk.nextStartByte;
          break;
        }
      }
      startByte = chunk.nextStartByte;
      if (!chunk.hasMore) {
        break;
      }
    }

    return {
      text,
      startByte: 0,
      nextStartByte: startByte,
      hasMore: truncated ? true : false,
      truncated
    };
  }

  async collectTailLog(jobPath, buildNumber, options) {
    let startByte = 0;
    let rolling = "";
    let hasMore = false;

    while (true) {
      const chunk = await this.getProgressiveLogChunk(jobPath, buildNumber, startByte);
      if (chunk.text) {
        rolling += chunk.text;
        if (Buffer.byteLength(rolling, "utf8") > options.maxBytes) {
          rolling = truncateByBytes(rolling, options.maxBytes, "start");
        }
      }
      startByte = chunk.nextStartByte;
      hasMore = chunk.hasMore;
      if (!chunk.hasMore) {
        break;
      }
    }

    const lines = rolling.split(/\r?\n/);
    const tail = lines.slice(-options.tailLines).join("\n");
    return {
      text: tail,
      startByte: 0,
      nextStartByte: startByte,
      hasMore,
      truncated: Buffer.byteLength(rolling, "utf8") >= options.maxBytes
    };
  }

  async getProgressiveLogChunk(jobPath, buildNumber, startByte) {
    const response = await this.request(
      "GET",
      `${this.jobBasePath(jobPath)}/${buildNumber}/logText/progressiveText`,
      {
        query: {
          start: String(startByte)
        }
      }
    );

    if (!response.ok) {
      throw await this.buildHttpError(response, "Failed to fetch Jenkins build log");
    }

    const text = await response.text();
    const nextStartByteHeader = response.headers.get("x-text-size");
    const hasMoreHeader = response.headers.get("x-more-data");
    const nextStartByte = nextStartByteHeader ? Number(nextStartByteHeader) : startByte;

    return {
      text,
      nextStartByte: Number.isFinite(nextStartByte) ? nextStartByte : startByte,
      hasMore: hasMoreHeader === "true"
    };
  }

  containerApiPath(folderPath) {
    if (!folderPath) {
      return "/api/json";
    }
    return `${this.jobBasePath(folderPath)}/api/json`;
  }

  jobBasePath(jobPath) {
    const segments = normalizeRequiredJobPath(jobPath, "jobPath")
      .split("/")
      .filter(Boolean)
      .map((segment) => `job/${encodeURIComponent(segment)}`);
    return `/${segments.join("/")}`;
  }

  async getJson(path, options = {}) {
    const response = await this.request("GET", path, {
      query: buildQuery(options)
    });
    if (!response.ok) {
      throw await this.buildHttpError(response, `Jenkins GET failed for ${path}`);
    }
    return response.json();
  }

  async request(method, path, options = {}) {
    const timeoutMs = normalizePositiveInteger(options.timeoutMs, this.defaultTimeoutMs);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const headers = new Headers(options.headers ?? {});
      headers.set("Authorization", this.authorizationHeader);

      if (options.body instanceof URLSearchParams) {
        headers.set("Content-Type", "application/x-www-form-urlencoded;charset=UTF-8");
      }

      if (!headers.has("Accept")) {
        headers.set("Accept", "application/json, text/plain;q=0.9, */*;q=0.8");
      }

      if (!["GET", "HEAD"].includes(method.toUpperCase())) {
        const crumbHeaders = await this.getCrumbHeaders();
        for (const [key, value] of Object.entries(crumbHeaders)) {
          headers.set(key, value);
        }
      }

      const url = new URL(path, this.baseUrl);
      for (const [key, value] of Object.entries(options.query ?? {})) {
        if (value !== undefined && value !== null) {
          url.searchParams.set(key, String(value));
        }
      }

      return await fetch(url, {
        method,
        headers,
        body: options.body,
        signal: controller.signal,
        redirect: options.redirect ?? "follow"
      });
    } catch (error) {
      if (error?.name === "AbortError") {
        throw new Error(`Request to Jenkins timed out after ${timeoutMs}ms.`);
      }
      throw error;
    } finally {
      clearTimeout(timer);
    }
  }

  async getCrumbHeaders() {
    if (this.crumbDisabled) {
      return {};
    }
    if (this.crumb) {
      return { [this.crumb.field]: this.crumb.value };
    }
    if (this.crumbPromise) {
      return this.crumbPromise;
    }

    this.crumbPromise = (async () => {
      const response = await this.request("GET", "/crumbIssuer/api/json", {
        headers: {
          Accept: "application/json"
        }
      }).catch((error) => {
        this.crumbPromise = null;
        throw error;
      });

      if (response.status === 404) {
        this.crumbDisabled = true;
        this.crumbPromise = null;
        return {};
      }

      if (!response.ok) {
        const error = await this.buildHttpError(response, "Failed to fetch Jenkins crumb");
        this.crumbPromise = null;
        throw error;
      }

      const data = await response.json();
      if (!data.crumbRequestField || !data.crumb) {
        this.crumbDisabled = true;
        this.crumbPromise = null;
        return {};
      }

      this.crumb = {
        field: data.crumbRequestField,
        value: data.crumb
      };
      this.crumbPromise = null;
      return { [data.crumbRequestField]: data.crumb };
    })();

    return this.crumbPromise;
  }

  async buildHttpError(response, message) {
    let body = "";
    try {
      body = await response.text();
    } catch {
      body = "";
    }

    return new JenkinsHttpError(message, response.status, truncateString(body, 2_000));
  }
}

export class JenkinsHttpError extends Error {
  constructor(message, statusCode, responseBody = "") {
    super(`${message} (HTTP ${statusCode})`);
    this.name = "JenkinsHttpError";
    this.statusCode = statusCode;
    this.responseBody = responseBody;
  }
}

function buildQuery(options) {
  const query = { ...(options.query ?? {}) };
  if (options.tree) {
    query.tree = options.tree;
  }
  return query;
}

function normalizeJobListItem(job) {
  const className = job._class ?? "";
  return {
    name: job.name ?? "",
    fullName: job.fullName ?? job.name ?? "",
    url: job.url ?? null,
    className,
    kind: inferJobKind(className),
    isContainer: isContainerJob(className),
    buildable: job.buildable !== false,
    color: job.color ?? null
  };
}

function extractParameterDefinitions(data) {
  const sources = [];
  if (Array.isArray(data.property)) {
    sources.push(...data.property);
  }
  if (Array.isArray(data.actions)) {
    sources.push(...data.actions);
  }

  const parameters = [];
  const seen = new Set();

  for (const source of sources) {
    for (const definition of Array.isArray(source?.parameterDefinitions)
      ? source.parameterDefinitions
      : []) {
      if (!definition?.name || seen.has(definition.name)) {
        continue;
      }
      seen.add(definition.name);
      parameters.push({
        name: definition.name,
        type: inferParameterType(definition),
        description: definition.description ?? "",
        defaultValue: definition.defaultParameterValue?.value ?? null,
        choices: Array.isArray(definition.choices) ? definition.choices : null
      });
    }
  }

  return parameters;
}

function inferParameterType(definition) {
  if (definition.type) {
    return definition.type;
  }
  const className = definition._class ?? "";
  const tail = className.split(".").at(-1) ?? className;
  return tail.replace(/ParameterDefinition$/, "") || "Unknown";
}

function normalizeBuildReference(buildRef) {
  if (!buildRef || typeof buildRef.number !== "number") {
    return null;
  }
  return {
    number: buildRef.number,
    url: buildRef.url ?? null
  };
}

function normalizeBuildDetails(data) {
  return {
    id: data.id ?? null,
    number: typeof data.number === "number" ? data.number : null,
    displayName: data.displayName ?? null,
    fullDisplayName: data.fullDisplayName ?? null,
    description: data.description ?? "",
    url: data.url ?? null,
    building: data.building === true,
    result: normalizeBuildResult(data.result),
    durationMs: typeof data.duration === "number" ? data.duration : null,
    estimatedDurationMs:
      typeof data.estimatedDuration === "number" ? data.estimatedDuration : null,
    timestamp: typeof data.timestamp === "number" ? data.timestamp : null,
    queueId: typeof data.queueId === "number" ? data.queueId : null,
    builtOn: data.builtOn ?? null,
    causes: extractBuildCauses(data.actions),
    parameters: extractBuildParameters(data.actions),
    artifacts: Array.isArray(data.artifacts) ? data.artifacts : []
  };
}

function extractBuildCauses(actions) {
  const causes = [];
  for (const action of Array.isArray(actions) ? actions : []) {
    for (const cause of Array.isArray(action?.causes) ? action.causes : []) {
      if (cause?.shortDescription) {
        causes.push(cause.shortDescription);
      }
    }
  }
  return causes;
}

function extractBuildParameters(actions) {
  const parameters = {};
  for (const action of Array.isArray(actions) ? actions : []) {
    for (const parameter of Array.isArray(action?.parameters) ? action.parameters : []) {
      if (parameter?.name) {
        parameters[parameter.name] = parameter.value ?? null;
      }
    }
  }
  return parameters;
}

function mapBuildStatus(build) {
  if (!build) {
    return "unknown";
  }
  if (build.building) {
    return "running";
  }
  switch (build.result) {
    case "SUCCESS":
      return "success";
    case "FAILURE":
      return "failed";
    case "UNSTABLE":
      return "unstable";
    case "ABORTED":
      return "aborted";
    case "NOT_BUILT":
      return "not_built";
    default:
      return "unknown";
  }
}

function normalizeBuildResult(result) {
  return typeof result === "string" ? result : null;
}

function inferJobKind(className) {
  if (isContainerJob(className)) {
    return "container";
  }
  if (className.includes("WorkflowJob") || className.includes("FreeStyleProject")) {
    return "job";
  }
  return "item";
}

function isContainerJob(className = "") {
  return (
    className.includes("Folder") ||
    className.includes("MultiBranchProject") ||
    className.includes("OrganizationFolder")
  );
}

function normalizeBaseUrl(baseUrl) {
  return baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
}

function normalizeRequiredJobPath(value, fieldName) {
  const normalized = normalizeOptionalJobPath(value);
  if (!normalized) {
    throw new Error(`${fieldName} must be a non-empty string like "folder/job-name".`);
  }
  return normalized;
}

function normalizeOptionalJobPath(value) {
  if (typeof value !== "string") {
    return null;
  }
  const normalized = value
    .split("/")
    .map((segment) => segment.trim())
    .filter(Boolean)
    .join("/");
  return normalized.length > 0 ? normalized : null;
}

function normalizeOptionalString(value) {
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : null;
}

function normalizePositiveInteger(value, fallback, fieldName = "value") {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isInteger(parsed) || parsed <= 0) {
    throw new Error(`${fieldName} must be a positive integer.`);
  }
  return parsed;
}

function normalizeNonNegativeInteger(value, fallback) {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isInteger(parsed) || parsed < 0) {
    throw new Error("startByte must be a non-negative integer.");
  }
  return parsed;
}

function normalizeLogMode(value) {
  const mode = value ?? "tail";
  if (!["tail", "full", "progressive"].includes(mode)) {
    throw new Error('mode must be one of "tail", "full", or "progressive".');
  }
  return mode;
}

function normalizeBuildParameters(parameters) {
  if (parameters === undefined || parameters === null) {
    return {};
  }
  if (typeof parameters !== "object" || Array.isArray(parameters)) {
    throw new Error("parameters must be an object of key/value pairs.");
  }
  return parameters;
}

function stringifyBuildValue(value) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

function extractQueueId(queueLocation) {
  const match = queueLocation.match(/\/queue\/item\/(\d+)\/?/);
  if (!match) {
    throw new Error(`Unable to parse Jenkins queue id from location: ${queueLocation}`);
  }
  return Number.parseInt(match[1], 10);
}

function absolutizeUrl(baseUrl, maybeRelativeUrl) {
  return new URL(maybeRelativeUrl, baseUrl).toString();
}

function extractFailureHighlights(logText) {
  const lines = logText.split(/\r?\n/).filter(Boolean);
  const highlights = [];
  const seen = new Set();

  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index];
    if (FAILURE_PATTERNS.some((pattern) => pattern.test(line))) {
      const trimmed = line.trim();
      if (trimmed && !seen.has(trimmed)) {
        seen.add(trimmed);
        highlights.push(trimmed);
      }
      if (highlights.length >= 20) {
        break;
      }
    }
  }

  return highlights.reverse();
}

function truncateString(value, limit) {
  if (value.length <= limit) {
    return value;
  }
  return `${value.slice(0, limit)}\n...[truncated]`;
}

function truncateByBytes(text, maxBytes, keep) {
  const buffer = Buffer.from(text, "utf8");
  if (buffer.byteLength <= maxBytes) {
    return text;
  }
  if (keep === "start") {
    return buffer.subarray(buffer.byteLength - maxBytes).toString("utf8");
  }
  return buffer.subarray(0, maxBytes).toString("utf8");
}

function parsePositiveInteger(value, fallback) {
  if (value === undefined || value === null || value === "") {
    return fallback;
  }
  const parsed = Number.parseInt(String(value), 10);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : fallback;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
