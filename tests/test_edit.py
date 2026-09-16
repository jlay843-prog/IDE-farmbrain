from pathlib import Path

from forge.edit import apply_diff, extract_diff, parse_unified_diff


DIFF = """--- a/hello.py
+++ b/hello.py
@@ -1,3 +1,4 @@
 def hello():
-    return "hi"
+    return "hello"
+
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
    apply_diff(tmp_path, """--- /dev/null
+++ b/new.txt
@@ -0,0 +1,2 @@
+alpha
+beta
""")
    assert (tmp_path / "new.txt").read_text(encoding="utf-8").splitlines()[:2] == ["alpha", "beta"]


def test_rejects_outside_workspace(tmp_path: Path):
    try:
        apply_diff(tmp_path, """--- a/../escape.txt
+++ b/../escape.txt
@@ -0,0 +1 @@
+nope
""")
    except ValueError:
        return
    raise AssertionError("expected path escape to fail")
