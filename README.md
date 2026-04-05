# Git-All-MCP

Local [Model Context Protocol](https://modelcontextprotocol.io) server for **any public GitHub repository**. Each tool takes `owner` and `repo` (and other parameters as needed). There is no hosted UI and no per-repo MCP URL: one process serves all repos.

## Install

```bash
cd /path/to/gitallmcp
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

Set `GITHUB_TOKEN` or `GH_TOKEN` for the MCP process (and restart). **Required** for `search_code` and `search_documentation`: GitHub’s [code search API](https://docs.github.com/en/rest/search/search#search-code) returns **401** without authentication. Other tools (`get_repo_stats`, `fetch_repo_file`, `fetch_documentation`, etc.) work for public repos without a token but benefit from higher rate limits when a token is set.

You can put the token in a **`.env`** file at the repository root (next to `src/`) or in the **current working directory** when the server starts. Example:

```bash
GITHUB_TOKEN=ghp_...
```

The cwd `.env` overrides the repo-root `.env` for duplicate keys. Real environment variables still take precedence over both files for keys that are already set.

## Run

**stdio (default)** — typical for Cursor and Claude Desktop:

```bash
gitallmcp --transport stdio
# or
python -m gitallmcp --transport stdio
```

**Streamable HTTP** — binds to `127.0.0.1:9001` by default; MCP endpoint path is **`/mcp`** (FastMCP default):

```bash
gitallmcp --transport streamable-http --host 127.0.0.1 --port 9001
```

Point your client at `http://127.0.0.1:9001/mcp` (see your client’s docs for streamable HTTP / MCP over HTTP).

The streamable HTTP server is wrapped with permissive CORS (including `OPTIONS` preflight) so browser-based MCP clients do not get `405 Method Not Allowed` on `/mcp`.

Streamable HTTP runs in **stateless** mode (`stateless_http=True`): each request is handled without requiring the `mcp-session-id` header on follow-up POSTs. That avoids `Bad Request: Missing session ID` from clients that do not persist that header (the default FastMCP stateful mode expects it after the first response).

## Cursor (`~/.cursor/mcp.json`)

stdio example:

```json
{
  "mcpServers": {
    "git-all-mcp": {
      "command": "gitallmcp",
      "args": ["--transport", "stdio"],
      "env": {
        "GITHUB_TOKEN": "ghp_your_token_here"
      }
    }
  }
}
```

Use a [personal access token](https://github.com/settings/tokens); omit `env` only if you avoid the search tools.

If `gitallmcp` is not on `PATH`, use the full path to the interpreter and module:

```json
{
  "mcpServers": {
    "git-all-mcp": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "gitallmcp", "--transport", "stdio"]
    }
  }
}
```

For streamable HTTP (if your Cursor version supports URL-based MCP for this transport), use the URL your server prints or `http://127.0.0.1:9001/mcp` after starting with `--transport streamable-http`.

## Tools

| Tool | Parameters | Purpose |
|------|------------|---------|
| `get_repo_stats` | `owner`, `repo` | Stars, forks, `open_issues` (see caveat below), `default_branch`, description |
| `fetch_repo_file` | `owner`, `repo`, `filepath` | Raw file from default branch (`refs/heads/<default>`) |
| `fetch_documentation` | `owner`, `repo` | `llms.txt` then `README.md` at repo root |
| `search_documentation` | `owner`, `repo`, `query`, `per_page` | GitHub code search scoped to Markdown and `docs/` |
| `search_code` | `owner`, `repo`, `query`, `per_page` | GitHub code search in the repo |
| `fetch_url_content` | `url` | Fetch http(s) content (size-capped; localhost blocked) |

`owner` and `repo` are **required** for every repo-scoped tool: use two arguments (e.g. `owner=vitejs`, `repo=vite`), not a combined `org/repo`, not a URL, and not blank strings. Search tools also require a non-empty `query`.

### GitHub API caveat: `open_issues`

`get_repo_stats` uses GitHub’s `open_issues_count`. That field **includes open pull requests**, not only issues. This is standard GitHub API behavior.

## Development

```bash
pip install -e ".[dev]"
pytest
```
