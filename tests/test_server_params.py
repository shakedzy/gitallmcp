import pytest

from gitallmcp.server import _normalize_nonempty, _normalize_owner_repo


def test_normalize_owner_repo_ok() -> None:
    assert _normalize_owner_repo("  microsoft ", " typescript\n") == ("microsoft", "typescript")


@pytest.mark.parametrize(
    ("owner", "repo"),
    [
        ("", "r"),
        ("o", ""),
        ("  ", "repo"),
        ("org", "   "),
    ],
)
def test_normalize_owner_repo_rejects_empty(owner: str, repo: str) -> None:
    with pytest.raises(ValueError, match="required"):
        _normalize_owner_repo(owner, repo)


def test_normalize_nonempty() -> None:
    assert _normalize_nonempty("  x  ", "query") == "x"
    with pytest.raises(ValueError, match="query"):
        _normalize_nonempty("", "query")
    with pytest.raises(ValueError, match="query"):
        _normalize_nonempty("   ", "query")
