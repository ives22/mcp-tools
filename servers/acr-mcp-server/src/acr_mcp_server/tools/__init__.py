"""MCP tool definitions and handlers for ACR operations."""

from __future__ import annotations

import logging
from typing import Any

from ..client import ACRClient, ACRError, ACRNotFoundError

logger = logging.getLogger(__name__)


# ===== Tool Definitions =====

def get_tool_definitions() -> list[dict[str, Any]]:
    """Return all ACR tool definitions for MCP registration."""
    return [
        {
            "name": "acr_list_namespaces",
            "description": (
                "List all namespaces in Alibaba Cloud Container Registry (ACR). "
                "Returns namespace names and their status. "
                "Use to discover which namespaces are available."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
        {
            "name": "acr_list_repos",
            "description": (
                "List image repositories in ACR. "
                "Can filter by namespace. Returns repo names, descriptions, "
                "visibility, and creation time. "
                "Use to discover which repos exist in a namespace."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": (
                            "Optional: filter by namespace name. "
                            "If omitted, lists repos across all namespaces."
                        ),
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (default: 1)",
                        "minimum": 1,
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "Results per page (default: 30, max: 100)",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": [],
            },
        },
        {
            "name": "acr_get_repo_info",
            "description": (
                "Get detailed information about a specific image repository. "
                "Returns repo type, description, creation time, download count, etc. "
                "Use to inspect a repo's metadata."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Namespace name (e.g., 'my_namespace')",
                    },
                    "repo_name": {
                        "type": "string",
                        "description": "Repository name (e.g., 'my_app')",
                    },
                },
                "required": ["namespace", "repo_name"],
            },
        },
        {
            "name": "acr_list_tags",
            "description": (
                "List all image tags for a repository in ACR. "
                "Returns tag names, image IDs, sizes, digests, and timestamps. "
                "Supports pagination for repos with many tags. "
                "Use to see what versions/images are available."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Namespace name (e.g., 'my_namespace')",
                    },
                    "repo_name": {
                        "type": "string",
                        "description": "Repository name (e.g., 'my_app')",
                    },
                    "page": {
                        "type": "integer",
                        "description": "Page number (default: 1)",
                        "minimum": 1,
                    },
                    "page_size": {
                        "type": "integer",
                        "description": "Results per page (default: 30, max: 100)",
                        "minimum": 1,
                        "maximum": 100,
                    },
                },
                "required": ["namespace", "repo_name"],
            },
        },
        {
            "name": "acr_check_tag_exists",
            "description": (
                "Check whether a specific image tag exists in a repository. "
                "Returns exists=true with tag details (image ID, size, digest, timestamps) "
                "if found, or exists=false if not. "
                "Use to verify if a build/deploy image tag has been pushed."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Namespace name (e.g., 'my_namespace')",
                    },
                    "repo_name": {
                        "type": "string",
                        "description": "Repository name (e.g., 'my_app')",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Image tag to check (e.g., 'v1.2.3', 'latest')",
                    },
                },
                "required": ["namespace", "repo_name", "tag"],
            },
        },
        {
            "name": "acr_get_tag_info",
            "description": (
                "Get detailed information about a specific image tag. "
                "Returns image ID, size, digest, creation and update timestamps. "
                "Use to inspect a tag's metadata in detail."
            ),
            "inputSchema": {
                "type": "object",
                "properties": {
                    "namespace": {
                        "type": "string",
                        "description": "Namespace name (e.g., 'my_namespace')",
                    },
                    "repo_name": {
                        "type": "string",
                        "description": "Repository name (e.g., 'my_app')",
                    },
                    "tag": {
                        "type": "string",
                        "description": "Image tag name (e.g., 'v1.2.3')",
                    },
                },
                "required": ["namespace", "repo_name", "tag"],
            },
        },
    ]


# ===== Tool Handlers =====

async def handle_list_namespaces(client: ACRClient, arguments: dict) -> dict:
    """Handle acr_list_namespaces tool call."""
    logger.info("List namespaces")
    try:
        data = client.list_namespaces()
        namespaces = data.get("data", {}).get("namespaces", [])
        return {
            "count": len(namespaces),
            "namespaces": [
                {
                    "name": ns.get("namespace", ""),
                    "status": ns.get("namespaceStatus", "UNKNOWN"),
                }
                for ns in namespaces
            ],
        }
    except ACRError as e:
        return {"error": str(e)}


async def handle_list_repos(client: ACRClient, arguments: dict) -> dict:
    """Handle acr_list_repos tool call."""
    namespace = arguments.get("namespace")
    page = arguments.get("page", 1)
    page_size = arguments.get("page_size", 30)

    logger.info(f"List repos (namespace={namespace}, page={page})")
    try:
        data = client.list_repos(namespace=namespace, page=page, page_size=page_size)
        repo_data = data.get("data", {})
        repos = repo_data.get("repos", [])
        return {
            "namespace": namespace or "(all)",
            "page": page,
            "page_size": page_size,
            "total": repo_data.get("total", len(repos)),
            "repos": [
                {
                    "namespace": r.get("repoNamespace", ""),
                    "name": r.get("repoName", ""),
                    "description": r.get("summary", ""),
                    "type": r.get("repoType", ""),
                    "downloads": r.get("downloads", 0),
                }
                for r in repos
            ],
        }
    except ACRError as e:
        return {"error": str(e), "namespace": namespace}


async def handle_get_repo_info(client: ACRClient, arguments: dict) -> dict:
    """Handle acr_get_repo_info tool call."""
    namespace = arguments["namespace"]
    repo_name = arguments["repo_name"]

    logger.info(f"Get repo info: {namespace}/{repo_name}")
    try:
        data = client.get_repo(namespace, repo_name)
        repo_data = data.get("data", {}).get("repo", {})
        return {
            "namespace": namespace,
            "repo_name": repo_name,
            "repo_id": repo_data.get("repoId", ""),
            "biz_id": repo_data.get("repoBizId", ""),
            "description": repo_data.get("summary", ""),
            "type": repo_data.get("repoType", ""),
            "status": repo_data.get("repoStatus", ""),
            "build_type": repo_data.get("repoBuildType", ""),
            "region": repo_data.get("regionId", ""),
            "downloads": repo_data.get("downloads", 0),
            "stars": repo_data.get("stars", 0),
            "domains": repo_data.get("repoDomainList", {}),
            "created": repo_data.get("gmtCreate", ""),
            "modified": repo_data.get("gmtModified", ""),
        }
    except ACRError as e:
        return {"error": str(e), "namespace": namespace, "repo_name": repo_name}


async def handle_list_tags(client: ACRClient, arguments: dict) -> dict:
    """Handle acr_list_tags tool call."""
    namespace = arguments["namespace"]
    repo_name = arguments["repo_name"]
    page = arguments.get("page", 1)
    page_size = arguments.get("page_size", 30)

    logger.info(f"List tags: {namespace}/{repo_name} (page={page})")
    try:
        data = client.list_tags(namespace, repo_name, page=page, page_size=page_size)
        tag_data = data.get("data", {})
        tags = tag_data.get("tags", [])
        return {
            "namespace": namespace,
            "repo_name": repo_name,
            "page": page,
            "page_size": page_size,
            "total": tag_data.get("total", len(tags)),
            "tags": [
                {
                    "tag": t.get("tag", ""),
                    "image_id": t.get("imageId", ""),
                    "digest": t.get("digest", ""),
                    "size": t.get("imageSize", 0),
                    "status": t.get("status", ""),
                    "created": t.get("imageCreate", ""),
                    "updated": t.get("imageUpdate", ""),
                }
                for t in tags
            ],
        }
    except ACRError as e:
        return {"error": str(e), "namespace": namespace, "repo_name": repo_name}


async def handle_check_tag_exists(client: ACRClient, arguments: dict) -> dict:
    """Handle acr_check_tag_exists tool call."""
    namespace = arguments["namespace"]
    repo_name = arguments["repo_name"]
    tag = arguments["tag"]

    logger.info(f"Check tag exists: {namespace}/{repo_name}:{tag}")
    try:
        data = client.get_tag(namespace, repo_name, tag)
        tag_data = data.get("data", {})
        return {
            "exists": True,
            "namespace": namespace,
            "repo_name": repo_name,
            "tag": tag,
            "image_id": tag_data.get("imageId", ""),
            "digest": tag_data.get("digest", ""),
            "size": tag_data.get("imageSize", 0),
            "status": tag_data.get("status", ""),
            "created": tag_data.get("imageCreate", ""),
            "updated": tag_data.get("imageUpdate", ""),
        }
    except ACRNotFoundError:
        return {
            "exists": False,
            "namespace": namespace,
            "repo_name": repo_name,
            "tag": tag,
            "message": f"Tag '{tag}' not found in {namespace}/{repo_name}",
        }
    except ACRError as e:
        return {"error": str(e), "namespace": namespace, "repo_name": repo_name, "tag": tag}


async def handle_get_tag_info(client: ACRClient, arguments: dict) -> dict:
    """Handle acr_get_tag_info tool call."""
    namespace = arguments["namespace"]
    repo_name = arguments["repo_name"]
    tag = arguments["tag"]

    logger.info(f"Get tag info: {namespace}/{repo_name}:{tag}")
    try:
        data = client.get_tag(namespace, repo_name, tag)
        tag_data = data.get("data", {})
        return {
            "namespace": namespace,
            "repo_name": repo_name,
            "tag": tag,
            "image_id": tag_data.get("imageId", ""),
            "digest": tag_data.get("digest", ""),
            "size": tag_data.get("imageSize", 0),
            "status": tag_data.get("status", ""),
            "created": tag_data.get("imageCreate", ""),
            "updated": tag_data.get("imageUpdate", ""),
        }
    except ACRError as e:
        return {"error": str(e), "namespace": namespace, "repo_name": repo_name, "tag": tag}


# Handler dispatch table
HANDLERS = {
    "acr_list_namespaces": handle_list_namespaces,
    "acr_list_repos": handle_list_repos,
    "acr_get_repo_info": handle_get_repo_info,
    "acr_list_tags": handle_list_tags,
    "acr_check_tag_exists": handle_check_tag_exists,
    "acr_get_tag_info": handle_get_tag_info,
}
