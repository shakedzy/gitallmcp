# Git-All-MCP

Local [Model Context Protocol](https://modelcontextprotocol.io) server for **any public GitHub repository**. Each tool takes `owner` and `repo` (and other parameters as needed). There is no hosted UI and no per-repo MCP URL: one process serves all repos.

## Install

assuming `uv` in installed:

```bash
cd /path/to/gitallmcp
uv sync
```

## Adding `GITHUB_TOKEN`

A [GitHub personal access token (PAT)](https://github.com/settings/tokens) is Required for `search_code` and `search_documentation`, as GitHub’s [code search API](https://docs.github.com/en/rest/search/search#search-code) returns `401` without authentication. Other tools (`get_repo_stats`, `list_org_repos`, `fetch_repo_file`, `fetch_documentation`, etc.) work for **public** data without a token; use a token for private repos or when listing private org repositories, and for higher rate limits.

You can put the token in a `.env` file at the repository root (next to `src/`) or in the **current working directory** when the server starts. Example:

```bash
GITHUB_TOKEN=ghp_...
```

The cwd `.env` overrides the repo-root `.env` for duplicate keys. Real environment variables still take precedence over both files for keys that are already set.

You can also set the token as a header when adding this MCP to your `mcp.json` file (see below).

## Run

**stdio (default)** — typical for Cursor and Claude Desktop:

```bash
uv run gitallmcp --transport stdio
```

**Streamable HTTP** — binds to `127.0.0.1:9001` by default; MCP endpoint path is **`/mcp`** (FastMCP default):

```bash
uv run gitallmcp --transport streamable-http --host 127.0.0.1 --port 9001
```

Point your client at `http://127.0.0.1:9001/mcp` (see your client’s docs for streamable HTTP / MCP over HTTP).

The streamable HTTP server is wrapped with permissive CORS (including `OPTIONS` preflight) so browser-based MCP clients do not get `405 Method Not Allowed` on `/mcp`.

Streamable HTTP runs in **stateless** mode (`stateless_http=True`): each request is handled without requiring the `mcp-session-id` header on follow-up POSTs. That avoids `Bad Request: Missing session ID` from clients that do not persist that header (the default FastMCP stateful mode expects it after the first response).

## Adding to Cursor (`~/.cursor/mcp.json`)

stdio example:

```json
{
  "mcpServers": {
    "git-all-mcp": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/gitallmcp", "gitallmcp", "--transport", "stdio"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"  // Optional
      }
    }
  }
}
```

For streamable HTTP (if your Cursor version supports URL-based MCP for this transport), use the URL your server prints or `http://127.0.0.1:9001/mcp` after starting with `--transport streamable-http`.

## Tools

| Tool | Parameters | Purpose |
|------|------------|---------|
| `get_repo_stats` | `owner`, `repo` | Stars, forks, `open_issues` (see caveat below), `default_branch`, description |
| `list_org_repos` | `org`, `max_repos` (optional, default 100, max 100) | List repositories for a GitHub **organization** (org login); paginates via the API; JSON includes `truncated` if more repos exist than returned |
| `fetch_repo_file` | `owner`, `repo`, `filepath` | Raw file from default branch (`refs/heads/<default>`) |
| `fetch_documentation` | `owner`, `repo` | `llms.txt` then `README.md` at repo root |
| `search_documentation` | `owner`, `repo`, `query`, `per_page` | GitHub code search scoped to Markdown and `docs/` |
| `search_code` | `owner`, `repo`, `query`, `per_page` | GitHub code search in the repo |
| `fetch_url_content` | `url` | Fetch http(s) content (size-capped; localhost blocked) |

Notes:
* For every **repo-scoped** tool, `owner` and `repo` are **required**: use two arguments (e.g. `owner=vitejs`, `repo=vite`), not a combined `org/repo`, not a URL, and not blank strings. 
* `list_org_repos` takes **`org`** only (organization login from `github.com/<org>`, not a user account). 
* `get_repo_stats` uses GitHub’s `open_issues_count`. That field **includes open pull requests**, not only issues. This is standard GitHub API behavior.

## Development

```bash
uv sync --extra dev
pytest
```
