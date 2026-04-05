import pytest

from gitallmcp.github import normalize_repo_path


def test_normalize_repo_path_strips_leading_slash() -> None:
    assert normalize_repo_path("/foo/bar") == "foo/bar"


def test_normalize_repo_path_rejects_traversal() -> None:
    with pytest.raises(ValueError, match="traversal"):
        normalize_repo_path("../etc/passwd")
    with pytest.raises(ValueError, match="traversal"):
        normalize_repo_path("foo/../bar")


def test_normalize_repo_path_rejects_empty() -> None:
    with pytest.raises(ValueError, match="non-empty"):
        normalize_repo_path("  ")
