"""GitHub REST API and raw content helpers."""

from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import quote

import httpx

GITHUB_API = "https://api.github.com"
RAW_BASE = "https://raw.githubusercontent.com"
DEFAULT_UA = "gitallmcp/0.1.0"
MAX_GITHUB_FILE_BYTES = 2 * 1024 * 1024
TIMEOUT_SECONDS = 30.0


def _auth_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def normalize_repo_path(filepath: str) -> str:
    p = filepath.strip().lstrip("/")
    if not p:
        raise ValueError("filepath must be non-empty")
    parts = p.split("/")
    for part in parts:
        if part == "..":
            raise ValueError("invalid path: path traversal is not allowed")
    return "/".join(parts)


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


CODE_SEARCH_NEEDS_AUTH = (
    "GitHub code search (/search/code) requires authentication: anonymous requests get 401. "
    "Create a token at https://github.com/settings/tokens (public-repo search works with a "
    "fine-grained token read-only on metadata, or a classic PAT with default scopes). "
    "Set GITHUB_TOKEN or GH_TOKEN for the gitallmcp process and restart the server."
)


def _rate_limit_message(response: httpx.Response) -> str | None:
    if response.status_code != 403:
        return None
    remaining = response.headers.get("x-ratelimit-remaining")
    if remaining == "0":
        return (
            "GitHub API rate limit exceeded. Set GITHUB_TOKEN or GH_TOKEN for higher limits."
        )
    text = (response.text or "").lower()
    if "rate limit" in text or "api rate limit" in text:
        return (
            "GitHub API rate limit exceeded. Set GITHUB_TOKEN or GH_TOKEN for higher limits."
        )
    return None


def _next_page_url_from_link_header(link_header: str | None) -> str | None:
    """Parse GitHub's Link header and return the URL for rel="next", if present."""
    if not link_header:
        return None
    for part in link_header.split(","):
        part = part.strip()
        if 'rel="next"' not in part and "rel='next'" not in part:
            continue
        m = re.search(r"<([^>]+)>", part)
        if m:
            return m.group(1).strip()
    return None


def _summarize_listed_repo(repo: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": repo.get("name"),
        "full_name": repo.get("full_name"),
        "description": repo.get("description"),
        "html_url": repo.get("html_url"),
        "default_branch": repo.get("default_branch"),
        "private": repo.get("private"),
        "fork": repo.get("fork"),
        "archived": repo.get("archived"),
        "stargazers_count": repo.get("stargazers_count"),
        "language": repo.get("language"),
    }


def _raise_if_search_unauthorized(response: httpx.Response) -> None:
    if response.status_code != 401:
        return
    hint = CODE_SEARCH_NEEDS_AUTH
    if _auth_token():
        hint += " Your token may be invalid, expired, or rejected by GitHub."
    raise ValueError(hint)


class GitHubClient:
    """Async GitHub API client with in-process default_branch cache."""

    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        self._branch_cache: dict[tuple[str, str], str] = {}

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "User-Agent": DEFAULT_UA,
            "X-GitHub-Api-Version": "2022-11-28",
        }
        token = _auth_token()
        if token:
            h["Authorization"] = f"Bearer {token}"
        return h

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=TIMEOUT_SECONDS,
                headers=self._headers(),
                follow_redirects=True,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    async def _get(self, url: str, params: dict[str, Any] | None = None) -> httpx.Response:
        client = await self._client()
        response = await client.get(url, params=params)
        msg = _rate_limit_message(response)
        if msg:
            raise ValueError(msg)
        return response

    async def get_repository(self, owner: str, repo: str) -> dict[str, Any]:
        url = f"{GITHUB_API}/repos/{owner}/{repo}"
        response = await self._get(url)
        if response.status_code == 404:
            raise ValueError(f"Repository not found: {owner}/{repo}")
        response.raise_for_status()
        return response.json()

    async def get_default_branch(self, owner: str, repo: str) -> str:
        key = (owner.lower(), repo.lower())
        if key in self._branch_cache:
            return self._branch_cache[key]
        data = await self.get_repository(owner, repo)
        branch = data.get("default_branch") or "main"
        self._branch_cache[key] = branch
        return branch

    async def fetch_raw_file(
        self,
        owner: str,
        repo: str,
        filepath: str,
        *,
        max_bytes: int = MAX_GITHUB_FILE_BYTES,
    ) -> str:
        path = normalize_repo_path(filepath)
        branch = await self.get_default_branch(owner, repo)
        url = f"{RAW_BASE}/{owner}/{repo}/refs/heads/{branch}/{path}"
        response = await self._get(url)
        if response.status_code == 404:
            raise ValueError(f"File not found: {path} in {owner}/{repo} (ref {branch})")
        msg = _rate_limit_message(response)
        if msg:
            raise ValueError(msg)
        response.raise_for_status()
        cl = response.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > max_bytes:
                    raise ValueError(f"File exceeds max size ({max_bytes} bytes)")
            except ValueError as e:
                if "max size" in str(e):
                    raise
        data = await response.aread()
        if len(data) > max_bytes:
            raise ValueError(f"File exceeds max size ({max_bytes} bytes)")
        return _decode_text(data)

    async def list_organization_repositories(
        self,
        org: str,
        *,
        max_repos: int = 100,
    ) -> dict[str, Any]:
        """List repositories for a GitHub organization (login), up to ``max_repos`` (1–100).

        Uses ``GET /orgs/{org}/repos`` with pagination (``per_page`` up to 100 per request).
        """
        o = (org or "").strip()
        if not o:
            raise ValueError(
                "`org` is required: the GitHub organization login (e.g. 'microsoft')."
            )
        max_repos = max(1, min(int(max_repos), 100))

        summarized: list[dict[str, Any]] = []
        page = 1
        truncated = False

        # GitHub pages are only aligned if per_page is fixed; always request 100 per page
        # and stop after accumulating max_repos (≤ 100).
        while len(summarized) < max_repos:
            url = f"{GITHUB_API}/orgs/{quote(o, safe='')}/repos"
            response = await self._get(
                url,
                params={
                    "page": page,
                    "per_page": 100,
                    "sort": "full_name",
                    "direction": "asc",
                },
            )
            if response.status_code == 404:
                raise ValueError(
                    f"Organization not found: {o} (use the org login from github.com/{o})."
                )
            msg = _rate_limit_message(response)
            if msg:
                raise ValueError(msg)
            response.raise_for_status()
            batch = response.json()
            if not isinstance(batch, list):
                raise ValueError("Unexpected GitHub API response for org repositories.")
            if not batch:
                break
            processed_all = True
            for repo in batch:
                if len(summarized) >= max_repos:
                    processed_all = False
                    break
                if isinstance(repo, dict):
                    summarized.append(_summarize_listed_repo(repo))
            next_url = _next_page_url_from_link_header(response.headers.get("link"))
            if len(summarized) >= max_repos:
                truncated = (not processed_all) or (next_url is not None)
                break
            if not next_url:
                break
            page += 1

        return {
            "organization": o,
            "repositories": summarized,
            "count": len(summarized),
            "truncated": truncated,
        }

    async def search_code(
        self,
        owner: str,
        repo: str,
        query: str,
        *,
        per_page: int = 20,
    ) -> dict[str, Any]:
        per_page = max(1, min(per_page, 100))
        q = f"repo:{owner}/{repo} {query}".strip()
        url = f"{GITHUB_API}/search/code"
        if not _auth_token():
            raise ValueError(CODE_SEARCH_NEEDS_AUTH)
        response = await self._get(url, params={"q": q, "per_page": per_page})
        _raise_if_search_unauthorized(response)
        if response.status_code == 422:
            raise ValueError(
                "GitHub code search rejected the query (422). "
                "Try simpler keywords; code search only indexes the default branch."
            )
        msg = _rate_limit_message(response)
        if msg:
            raise ValueError(msg)
        response.raise_for_status()
        return response.json()

    async def search_documentation(
        self,
        owner: str,
        repo: str,
        query: str,
        *,
        per_page: int = 20,
    ) -> dict[str, Any]:
        per_page = max(1, min(per_page, 100))
        q = f"repo:{owner}/{repo} (extension:md OR path:docs/) {query}".strip()
        url = f"{GITHUB_API}/search/code"
        if not _auth_token():
            raise ValueError(CODE_SEARCH_NEEDS_AUTH)
        response = await self._get(url, params={"q": q, "per_page": per_page})
        _raise_if_search_unauthorized(response)
        if response.status_code == 422:
            raise ValueError(
                "GitHub code search rejected the query (422). "
                "Try simpler keywords; search is scoped to Markdown and docs/ paths."
            )
        msg = _rate_limit_message(response)
        if msg:
            raise ValueError(msg)
        response.raise_for_status()
        return response.json()
