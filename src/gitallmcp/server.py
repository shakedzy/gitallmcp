"""FastMCP server: GitHub tools with owner/repo parameters."""

from __future__ import annotations

import json

import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.middleware.cors import CORSMiddleware

from gitallmcp.github import MAX_GITHUB_FILE_BYTES, GitHubClient

_gh: GitHubClient | None = None


def get_github() -> GitHubClient:
    global _gh
    if _gh is None:
        _gh = GitHubClient()
    return _gh


def _normalize_owner_repo(owner: str, repo: str) -> tuple[str, str]:
    """Require non-empty GitHub `owner` and `repo`; return stripped strings."""
    o = (owner or "").strip()
    r = (repo or "").strip()
    if not o:
        raise ValueError(
            "`owner` is required and must not be empty: the GitHub organization or username "
            "(e.g. 'microsoft' for github.com/microsoft/typescript)."
        )
    if not r:
        raise ValueError(
            "`repo` is required and must not be empty: the repository name only, with no '/' "
            "(e.g. 'typescript' for github.com/microsoft/typescript). Do not pass a full path or URL."
        )
    return o, r


def _normalize_nonempty(query: str, param_name: str) -> str:
    q = (query or "").strip()
    if not q:
        raise ValueError(
            f"`{param_name}` is required and must not be empty: provide a non-blank search string."
        )
    return q


def _normalize_filepath_arg(filepath: str) -> str:
    fp = (filepath or "").strip()
    if not fp:
        raise ValueError(
            "`filepath` is required: path to the file relative to the repo root (e.g. 'README.md')."
        )
    return fp


def _format_code_search_results(data: dict) -> str:
    items = data.get("items") or []
    lines: list[str] = []
    lines.append(f"Total matches (capped by per_page): {data.get('total_count', 0)}")
    for item in items:
        path = item.get("path", "")
        html_url = item.get("html_url", "")
        repo = item.get("repository", {})
        full_name = repo.get("full_name", "")
        snippet = ""
        for tm in item.get("text_matches") or []:
            frag = tm.get("fragment")
            if frag:
                snippet = (frag or "")[:500]
                break
        lines.append(f"- **{path}** ({full_name})")
        if html_url:
            lines.append(f"  - {html_url}")
        if snippet:
            lines.append(f"  ```\n  {snippet}\n  ```")
    return "\n".join(lines) if lines else "(no results)"


def create_mcp(*, host: str = "127.0.0.1", port: int = 9001) -> FastMCP:
    # Stateless streamable HTTP: no mcp-session-id header required between POSTs.
    # Stateful mode rejects non-initialize requests without the session ID returned
    # from the first response, which breaks many MCP HTTP clients.
    mcp = FastMCP(
        "Git-All-MCP",
        host=host,
        port=port,
        stateless_http=True,
        instructions=(
            "Tools access arbitrary public GitHub repositories. "
            "For every repo-scoped tool you MUST pass two separate string parameters: "
            "`owner` (GitHub org or username) and `repo` (short repository name only, never empty, "
            "never a URL, never 'org/repo' in one field — e.g. owner='microsoft', repo='typescript'). "
            "list_org_repos takes `org` (organization login only). "
            "Set GITHUB_TOKEN or GH_TOKEN: required for search_code and search_documentation "
            "(GitHub code search API); optional but recommended for rate limits on other calls."
        ),
    )

    @mcp.tool()
    async def get_repo_stats(owner: str, repo: str) -> str:
        """Return stars, forks, open issues count, default branch, and description.

        Required: `owner` — GitHub org or username. Required: `repo` — repository name only (no slashes).

        Example: owner='microsoft', repo='typescript' for https://github.com/microsoft/typescript

        GitHub's open_issues_count includes pull requests.
        """
        owner, repo = _normalize_owner_repo(owner, repo)
        gh = get_github()
        data = await gh.get_repository(owner, repo)
        payload = {
            "owner": owner,
            "repo": repo,
            "full_name": data.get("full_name"),
            "description": data.get("description"),
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "open_issues": data.get("open_issues_count"),
            "default_branch": data.get("default_branch"),
            "note": "open_issues includes pull requests (GitHub API behavior).",
        }
        return json.dumps(payload, indent=2)

    @mcp.tool()
    async def list_org_repos(org: str, max_repos: int = 100) -> str:
        """List repositories for a GitHub organization (org login from github.com/<org>).

        Paginates via the org repos API (100 items per page). Returns at most ``max_repos`` repos
        (default 100, clamped to 1–100). Response JSON includes ``truncated``: true if more repos
        exist on GitHub than returned. Private repos require a token with appropriate access.
        """
        gh = get_github()
        data = await gh.list_organization_repositories(org, max_repos=max_repos)
        return json.dumps(data, indent=2)

    @mcp.tool()
    async def fetch_repo_file(owner: str, repo: str, filepath: str) -> str:
        """Fetch a file from the repo's default branch via raw.githubusercontent.com.

        Required: `owner`, `repo` (same rules as other tools). Required: `filepath` relative to repo root.

        Example: owner='microsoft', repo='typescript', filepath='README.md'
        """
        owner, repo = _normalize_owner_repo(owner, repo)
        filepath = _normalize_filepath_arg(filepath)
        gh = get_github()
        return await gh.fetch_raw_file(owner, repo, filepath, max_bytes=MAX_GITHUB_FILE_BYTES)

    @mcp.tool()
    async def fetch_documentation(owner: str, repo: str) -> str:
        """Load primary documentation: try llms.txt at repo root, then README.md.

        Required: `owner` (GitHub org or user). Required: `repo` (short repo name only, non-empty).
        """
        owner, repo = _normalize_owner_repo(owner, repo)
        gh = get_github()
        last_err: str | None = None
        for name in ("llms.txt", "README.md"):
            try:
                return await gh.fetch_raw_file(owner, repo, name, max_bytes=MAX_GITHUB_FILE_BYTES)
            except ValueError as e:
                last_err = str(e)
                if "not found" in last_err.lower():
                    continue
                raise
        raise ValueError(
            f"No llms.txt or README.md at repo root for {owner}/{repo}. Last error: {last_err}"
        )

    @mcp.tool()
    async def search_documentation(
        owner: str,
        repo: str,
        query: str,
        per_page: int = 20,
    ) -> str:
        """Search Markdown and docs/ paths in the repository via GitHub code search.

        Required: `owner`, `repo` (non-empty; `repo` is the name only, e.g. 'vite' not 'org/vite').
        Required: `query` — non-empty search keywords.

        Requires GITHUB_TOKEN or GH_TOKEN (GitHub does not allow anonymous code search).
        Scoped to the default branch only (GitHub limitation). per_page is 1–100.
        """
        owner, repo = _normalize_owner_repo(owner, repo)
        query = _normalize_nonempty(query, "query")
        gh = get_github()
        data = await gh.search_documentation(owner, repo, query, per_page=per_page)
        return _format_code_search_results(data)

    @mcp.tool()
    async def search_code(
        owner: str,
        repo: str,
        query: str,
        per_page: int = 20,
    ) -> str:
        """Search source code in the repository via GitHub code search (default branch).

        Required: `owner` — GitHub org or username. Required: `repo` — repository name only,
        non-empty string (e.g. 'vite' for github.com/vitejs/vite; do not omit or pass '').

        Required: `query` — non-empty code search keywords.

        Requires GITHUB_TOKEN or GH_TOKEN (GitHub does not allow anonymous code search).
        """
        owner, repo = _normalize_owner_repo(owner, repo)
        query = _normalize_nonempty(query, "query")
        gh = get_github()
        data = await gh.search_code(owner, repo, query, per_page=per_page)
        return _format_code_search_results(data)

    return mcp


async def run_streamable_http_with_cors(mcp: FastMCP) -> None:
    """Serve streamable HTTP with CORS so OPTIONS preflight succeeds (e.g. browser-based MCP clients)."""
    inner = mcp.streamable_http_app()
    app = CORSMiddleware(
        inner,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    config = uvicorn.Config(
        app,
        host=mcp.settings.host,
        port=mcp.settings.port,
        log_level=mcp.settings.log_level.lower(),
    )
    server = uvicorn.Server(config)
    await server.serve()
