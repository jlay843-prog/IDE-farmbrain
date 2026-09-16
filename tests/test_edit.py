from pathlib import Path

from forge.edit import apply_diff, change_list, extract_diff, format_change_list, parse_unified_diff


DIFF = """--- a/hello.py
+++ b/hello.py
@@ -1,3 +1,4 @@
 def hello():
-    return "hi"
+    return "hello"
+
"""

MULTI = """--- a/hello.py
+++ b/hello.py
@@ -1,3 +1,4 @@
 def hello():
-    return "hi"
+    return "hello"
+
--- /dev/null
+++ b/new.txt
@@ -0,0 +1,2 @@
+alpha
+beta
--- a/gone.txt
+++ /dev/null
@@ -1 +0,0 @@
-bye
"""


def test_extract_diff_from_fence():
    text = "Sure.\n```diff\n" + DIFF + "```\n"
    assert "--- a/hello.py" in extract_diff(text)


def test_parse_and_apply(tmp_path: Path):
    target = tmp_path / "hello.py"
    target.write_text('def hello():\n    return "hi"\n', encoding="utf-8")
    changed = apply_diff(tmp_path, DIFF)
    assert changed == ["hello.py"]
    assert 'return "hello"' in target.read_text(encoding="utf-8")


def test_new_file(tmp_path: Path):
    diff = """--- a/dev/null
+++ b/new.txt
@@ -0,0 +1,2 @@
+alpha
+beta
"""
    # parser uses +++ path
    patches = parse_unified_diff(diff.replace("a/dev/null", "/dev/null"))
    assert patches
    apply_diff(
        tmp_path,
        """--- /dev/null
+++ b/new.txt
@@ -0,0 +1,2 @@
+alpha
+beta
""",
    )
    assert (tmp_path / "new.txt").read_text(encoding="utf-8").splitlines()[:2] == ["alpha", "beta"]


def test_rejects_outside_workspace(tmp_path: Path):
    try:
        apply_diff(
            tmp_path,
            """--- a/../escape.txt
+++ b/../escape.txt
@@ -0,0 +1 @@
+nope
""",
        )
    except ValueError:
        return
    raise AssertionError("expected path escape to fail")


def test_change_list_one_file():
    rows = change_list(DIFF)
    assert len(rows) == 1
    assert rows[0]["path"] == "hello.py"
    assert rows[0]["kind"] == "modified"
    assert rows[0]["added"] == 2
    assert rows[0]["deleted"] == 1
    assert rows[0]["hunks"] == 1


def test_change_list_multiple_files():
    rows = change_list(MULTI)
    paths = [row["path"] for row in rows]
    assert paths == ["hello.py", "new.txt", "gone.txt"]
    kinds = {row["path"]: row["kind"] for row in rows}
    assert kinds["hello.py"] == "modified"
    assert kinds["new.txt"] == "added"
    assert kinds["gone.txt"] == "deleted"
    assert change_list("Sure, I can help with that.") == []
    text = format_change_list(rows)
    assert "changes (3 files):" in text
    assert "A new.txt" in text
    assert "D gone.txt" in text


def test_apply_multi_file(tmp_path: Path):
    (tmp_path / "hello.py").write_text('def hello():\n    return "hi"\n', encoding="utf-8")
    (tmp_path / "gone.txt").write_text("bye\n", encoding="utf-8")
    changed = apply_diff(tmp_path, MULTI)
    assert changed == ["hello.py", "new.txt", "gone.txt"]
    assert 'return "hello"' in (tmp_path / "hello.py").read_text(encoding="utf-8")
    assert (tmp_path / "new.txt").read_text(encoding="utf-8").splitlines()[:2] == ["alpha", "beta"]
    assert not (tmp_path / "gone.txt").exists()


TWO_HUNKS = """--- a/hello.py
+++ b/hello.py
@@ -1,2 +1,2 @@
 def hello():
-    return "hi"
+    return "hello"
@@ -4,2 +4,2 @@
 def other():
-    return 1
+    return 2
"""


def test_parse_and_apply_one_hunk(tmp_path: Path):
    from forge.edit import format_hunk_list, hunk_list

    target = tmp_path / "hello.py"
    target.write_text('def hello():\n    return "hi"\n\ndef other():\n    return 1\n', encoding="utf-8")
    rows = hunk_list(TWO_HUNKS)
    assert [row["id"] for row in rows] == [0, 1]
    assert rows[0]["path"] == "hello.py"
    assert "hunks (2):" in format_hunk_list(rows)
    apply_diff(tmp_path, TWO_HUNKS, [1])
    text = target.read_text(encoding="utf-8")
    assert 'return "hi"' in text
    assert "return 2" in text
    assert "return 1" not in text
    apply_diff(tmp_path, TWO_HUNKS, [0])
    text = target.read_text(encoding="utf-8")
    assert 'return "hello"' in text
    assert "return 2" in text
