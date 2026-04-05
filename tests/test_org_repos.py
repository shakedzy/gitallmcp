import asyncio

import httpx
import pytest

from gitallmcp.github import (
    GitHubClient,
    _next_page_url_from_link_header,
)


def test_next_page_url_from_link_header() -> None:
    hdr = (
        '<https://api.github.com/orgs/foo/repos?page=2>; rel="prev", '
        '<https://api.github.com/orgs/foo/repos?page=4>; rel="next", '
        '<https://api.github.com/orgs/foo/repos?page=5>; rel="last"'
    )
    assert (
        _next_page_url_from_link_header(hdr)
        == "https://api.github.com/orgs/foo/repos?page=4"
    )


def test_next_page_url_missing() -> None:
    assert _next_page_url_from_link_header(None) is None
    assert _next_page_url_from_link_header("") is None
    assert (
        _next_page_url_from_link_header(
            '<https://api.github.com/orgs/foo/repos?page=1>; rel="first"'
        )
        is None
    )


def _repos_request(page: int = 1) -> httpx.Request:
    return httpx.Request(
        "GET",
        f"https://api.github.com/orgs/acme/repos?page={page}&per_page=100",
    )


def _fake_repo(name: str) -> dict:
    return {
        "name": name,
        "full_name": f"acme/{name}",
        "description": None,
        "html_url": f"https://github.com/acme/{name}",
        "default_branch": "main",
        "private": False,
        "fork": False,
        "archived": False,
        "stargazers_count": 0,
        "language": "Python",
    }


def test_list_org_repos_single_page_not_truncated() -> None:
    client = GitHubClient()
    batch = [_fake_repo("a"), _fake_repo("b")]

    async def fake_get(url: str, params: dict | None = None) -> httpx.Response:
        assert "/orgs/acme/repos" in url
        assert params["per_page"] == 100
        assert params["page"] == 1
        return httpx.Response(
            200,
            json=batch,
            headers={"link": ""},
            request=_repos_request(1),
        )

    client._get = fake_get  # type: ignore[method-assign]

    async def run() -> None:
        out = await client.list_organization_repositories("acme", max_repos=100)
        assert out["organization"] == "acme"
        assert out["count"] == 2
        assert out["truncated"] is False
        assert [r["name"] for r in out["repositories"]] == ["a", "b"]

    asyncio.run(run())


def test_list_org_repos_truncated_cap_within_batch() -> None:
    client = GitHubClient()
    batch = [_fake_repo(f"r{i}") for i in range(100)]

    async def fake_get(url: str, params: dict | None = None) -> httpx.Response:
        return httpx.Response(200, json=batch, request=_repos_request(1))

    client._get = fake_get  # type: ignore[method-assign]

    async def run() -> None:
        out = await client.list_organization_repositories("acme", max_repos=30)
        assert out["count"] == 30
        assert out["truncated"] is True

    asyncio.run(run())


def test_list_org_repos_truncated_next_link() -> None:
    client = GitHubClient()
    batch = [_fake_repo(f"r{i}") for i in range(100)]
    link = '<https://api.github.com/orgs/acme/repos?page=2>; rel="next"'

    async def fake_get(url: str, params: dict | None = None) -> httpx.Response:
        return httpx.Response(
            200, json=batch, headers={"Link": link}, request=_repos_request(1)
        )

    client._get = fake_get  # type: ignore[method-assign]

    async def run() -> None:
        out = await client.list_organization_repositories("acme", max_repos=100)
        assert out["count"] == 100
        assert out["truncated"] is True

    asyncio.run(run())


def test_list_org_repos_404() -> None:
    client = GitHubClient()

    async def fake_get(url: str, params: dict | None = None) -> httpx.Response:
        return httpx.Response(
            404,
            json={"message": "Not Found"},
            request=_repos_request(1),
        )

    client._get = fake_get  # type: ignore[method-assign]

    async def run() -> None:
        with pytest.raises(ValueError, match="Organization not found"):
            await client.list_organization_repositories("nope")

    asyncio.run(run())


def test_list_org_repos_empty_org() -> None:
    async def run() -> None:
        with pytest.raises(ValueError, match="org"):
            await GitHubClient().list_organization_repositories("   ")

    asyncio.run(run())


def test_list_org_repos_second_page() -> None:
    """When page 1 is shorter than 100 but rel=next exists, request page 2 (cap 100 total)."""
    client = GitHubClient()
    page1 = [_fake_repo(f"p1-{i}") for i in range(50)]
    page2 = [_fake_repo(f"p2-{i}") for i in range(50)]

    async def fake_get(url: str, params: dict | None = None) -> httpx.Response:
        p = params or {}
        if p.get("page") == 1:
            link = '<https://api.github.com/orgs/acme/repos?page=2>; rel="next"'
            return httpx.Response(
                200, json=page1, headers={"Link": link}, request=_repos_request(1)
            )
        if p.get("page") == 2:
            return httpx.Response(200, json=page2, request=_repos_request(2))
        raise AssertionError(f"unexpected page {p!r}")

    client._get = fake_get  # type: ignore[method-assign]

    async def run() -> None:
        out = await client.list_organization_repositories("acme", max_repos=100)
        assert out["count"] == 100
        assert out["truncated"] is False
        assert out["repositories"][0]["name"] == "p1-0"
        assert out["repositories"][-1]["name"] == "p2-49"

    asyncio.run(run())
