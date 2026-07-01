"""ACR API client with call_api workaround for SDK response model bug."""

from __future__ import annotations

import json
import logging
from typing import Any

from alibabacloud_cr20160607.client import Client as ACRSDKClient
from alibabacloud_openapi_util.client import Client as OpenApiUtilClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_tea_util import models as util_models

from .config import ACRConfig

logger = logging.getLogger(__name__)


class ACRError(Exception):
    """Base exception for ACR API errors."""
    pass


class ACRNotFoundError(ACRError):
    """Resource not found (404)."""
    pass


class ACRClient:
    """Client for Alibaba Cloud Container Registry (ACR) Personal Edition.

    Uses the low-level call_api() to bypass the SDK's incomplete Response models
    (GetRepoTagsResponse.from_map() only maps headers, discarding body data).
    """

    def __init__(self, config: ACRConfig) -> None:
        self.config = config
        sdk_config = open_api_models.Config(
            access_key_id=config.access_key_id,
            access_key_secret=config.access_key_secret,
            endpoint=config.endpoint,
        )
        self._client = ACRSDKClient(sdk_config)

    def _call_api(
        self,
        action: str,
        pathname: str,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call ACR API and return parsed JSON body.

        This is the core workaround: instead of using the SDK's high-level methods
        (whose Response models lose the body), we call call_api() directly and
        parse the raw JSON body ourselves.

        Args:
            action: API action name (e.g., 'GetRepoTags')
            pathname: URL path (e.g., '/repos/ns/repo/tags')
            query: Query parameters dict

        Returns:
            Parsed JSON body as dict

        Raises:
            ACRNotFoundError: If the resource is not found (404)
            ACRError: For other API errors
        """
        runtime = util_models.RuntimeOptions()

        query_params = {k: v for k, v in (query or {}).items() if v is not None}
        req = open_api_models.OpenApiRequest(
            headers={},
            query=OpenApiUtilClient.query(query_params),
        )
        params = open_api_models.Params(
            action=action,
            version="2016-06-07",
            protocol="HTTPS",
            pathname=pathname,
            method="GET",
            auth_type="AK",
            style="ROA",
            req_body_type="json",
            body_type="none",
        )

        logger.debug(f"API call: {action} {pathname} query={query_params}")

        try:
            raw = self._client.call_api(params, req, runtime)
        except Exception as e:
            error_msg = str(e)
            # Check for 404 / not found in the exception
            if "404" in error_msg or "NOT_FOUND" in error_msg.upper():
                raise ACRNotFoundError(f"Resource not found: {pathname}") from e
            raise ACRError(f"API call failed: {action} {pathname}: {e}") from e

        status_code = raw.get("statusCode", 0)
        body_str = raw.get("body", "{}")

        if isinstance(body_str, str):
            try:
                body = json.loads(body_str)
            except json.JSONDecodeError:
                body = {"raw": body_str}
        else:
            body = body_str

        if status_code == 404:
            raise ACRNotFoundError(f"Resource not found: {pathname}")
        if status_code >= 400:
            error_code = body.get("code", "UnknownError")
            error_msg = body.get("message", str(body))
            raise ACRError(f"API error [{status_code}] {error_code}: {error_msg}")

        logger.debug(f"API response: {action} status={status_code}")
        return body

    # --- Namespace APIs ---

    def list_namespaces(self) -> dict[str, Any]:
        """List all namespaces.

        API: GET /namespace (Action: GetNamespaceList)
        """
        return self._call_api("GetNamespaceList", "/namespace")

    # --- Repository APIs ---

    def list_repos(
        self,
        namespace: str | None = None,
        page: int = 1,
        page_size: int = 30,
    ) -> dict[str, Any]:
        """List repositories, optionally filtered by namespace.

        Without namespace: GET /repos (Action: GetRepoList)
        With namespace:    GET /repos/{namespace} (Action: GetRepoListByNamespace)
        """
        query: dict[str, Any] = {"Page": page, "PageSize": page_size}

        if namespace:
            return self._call_api(
                "GetRepoListByNamespace",
                f"/repos/{namespace}",
                query=query,
            )
        return self._call_api("GetRepoList", "/repos", query=query)

    def get_repo(self, namespace: str, repo_name: str) -> dict[str, Any]:
        """Get repository details.

        API: GET /repos/{namespace}/{repo_name} (Action: GetRepo)
        """
        return self._call_api("GetRepo", f"/repos/{namespace}/{repo_name}")

    # --- Tag APIs ---

    def list_tags(
        self,
        namespace: str,
        repo_name: str,
        page: int = 1,
        page_size: int = 30,
    ) -> dict[str, Any]:
        """List all tags for a repository.

        API: GET /repos/{namespace}/{repo_name}/tags (Action: GetRepoTags)
        """
        return self._call_api(
            "GetRepoTags",
            f"/repos/{namespace}/{repo_name}/tags",
            query={"Page": page, "PageSize": page_size},
        )

    def get_tag(self, namespace: str, repo_name: str, tag: str) -> dict[str, Any]:
        """Get a specific tag's details.

        API: GET /repos/{namespace}/{repo_name}/tags/{tag} (Action: GetRepoTag)
        """
        return self._call_api(
            "GetRepoTag",
            f"/repos/{namespace}/{repo_name}/tags/{tag}",
        )
