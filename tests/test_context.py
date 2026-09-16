from pathlib import Path

from forge.context import list_tree, search_paths, tree_listing


def _workspace(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "src" / "pkg" / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "docs" / "notes.md").parent.mkdir(parents=True, exist_ok=True)
    (root / "docs" / "notes.md").write_text("# notes\n", encoding="utf-8")
    (root / "README.md").write_text("proj\n", encoding="utf-8")
    skipped = root / "node_modules" / "left-pad"
    skipped.mkdir(parents=True)
    (skipped / "index.js").write_text("module.exports = 1\n", encoding="utf-8")
    return root


def test_list_tree_is_one_directory(tmp_path: Path):
    root = _workspace(tmp_path)
    names = {row["name"] for row in list_tree(root, "")}
    assert "src" in names
    assert "docs" in names
    assert "README.md" in names
    assert "hello.py" not in names
    assert "node_modules" not in names
    nested = {row["name"] for row in list_tree(root, "src")}
    assert nested == {"pkg"}


def test_tree_listing_crumbs_and_parent(tmp_path: Path):
    root = _workspace(tmp_path)
    top = tree_listing(root, "")
    assert top["cwd"] == ""
    assert top["parent"] is None
    assert top["crumbs"][0]["path"] == ""
    nested = tree_listing(root, "src/pkg")
    assert nested["cwd"] == "src/pkg"
    assert nested["parent"] == "src"
    assert [c["path"] for c in nested["crumbs"]] == ["", "src", "src/pkg"]
    assert {row["name"] for row in nested["entries"]} == {"hello.py"}


def test_search_paths_are_relative_and_skip_vendor(tmp_path: Path):
    root = _workspace(tmp_path)
    found = search_paths(root, "hello")
    assert found["truncated"] is False
    paths = [row["path"] for row in found["entries"]]
    assert "src/pkg/hello.py" in paths
    assert all("text" not in row for row in found["entries"])
    assert all("node_modules" not in row["path"] for row in found["entries"])
    miss = search_paths(root, "left-pad")
    assert miss["entries"] == []


def test_search_empty_query_is_empty(tmp_path: Path):
    root = _workspace(tmp_path)
    found = search_paths(root, "  ")
    assert found["entries"] == []
    assert found["truncated"] is False
