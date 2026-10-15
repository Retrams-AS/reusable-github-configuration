import http.server
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fast_track as ft


def raises(fn, *a):
    try:
        fn(*a)
    except ValueError:
        return True
    return False


assert ft.strip_frontmatter("---\na: 1\n---\nbody\n") == "body\n"

m = {"fast": ["src/**", "docs/*.md"], "critical": ["src/arm/**"]}
assert ft.on_fast_lane("src/a/b.py", m)
assert not ft.on_fast_lane("src/arm/x.py", m)
assert ft.on_fast_lane("docs/a.md", m) and not ft.on_fast_lane("docs/a/b.md", m)
assert not ft.on_fast_lane(".github/x", {"fast": ["**"]})
assert not ft.on_fast_lane("src/a", {})
assert ft.floor(["src/a", "x", "src/arm/y"], m) == ["x", "src/arm/y"]
for bad in ([], {"fast": "x"}, {"critical": [1]}, {"audit-rate": 0}, {"audit-rate": "5"}):
    assert raises(ft.on_fast_lane, "a", bad), bad

flag = '{"file":"a","line":1,"trigger":"auth","why":"w"}'
assert ft.parse_verdict('{"verdict":"fast","flags":[]}')["verdict"] == "fast"
assert ft.parse_verdict('{"verdict":"denied","flags":[]}')["verdict"] == "denied"
assert ft.parse_verdict('{"verdict":"critical","flags":[%s]}' % flag)
for bad in ["nope", "[]", '{"verdict":"fast"}', '{"verdict":"maybe","flags":[]}',
            '{"verdict":"fast","flags":[%s]}' % flag, '{"verdict":"critical","flags":[]}',
            '{"verdict":"denied","flags":[%s]}' % flag,
            '{"verdict":"critical","flags":[{"file":"a","line":"1","trigger":"auth","why":"w"}]}',
            '{"verdict":"critical","flags":[{"file":"a","line":1,"trigger":"x","why":"w"}]}',
            '{"verdict":"critical","flags":[{"file":"a","line":1,"trigger":"auth"}]}',
            '{"verdict":"fast","flags":[],"extra":1}']:
    assert raises(ft.parse_verdict, bad), bad

F, C, D = {"verdict": "fast"}, {"verdict": "critical"}, {"verdict": "denied"}
assert ft.decide([], F) == "fast"
assert ft.decide(["x"], F) == "critical" and ft.decide([], C) == "critical" and ft.decide([], D) == "critical"

assert ft.sampled(b"k", "o/r", 7, 5) == ft.sampled(b"k", "o/r", 7, 5)
n = sum(ft.sampled(b"k", "o/r", i, 5) for i in range(2000))
assert 300 < n < 500, n
assert all(ft.sampled(b"k", "o/r", i, 1) for i in range(10))

diff = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,2 +1,3 @@
 x
+y
 z
@@ -20,2 +21,2 @@
-old
+new
 k
diff --git a/gone.py b/gone.py
deleted file mode 100644
--- a/gone.py
+++ /dev/null
@@ -1,2 +0,0 @@
-a
-b
"""
assert ft.hunk_at(diff, "a.py", 2).endswith("+y\n z")
assert "+new" in ft.hunk_at(diff, "a.py", 21)
assert ft.hunk_at(diff, "a.py", 10) is None
assert "-b" in ft.hunk_at(diff, "gone.py", 2)
assert ft.hunk_at(diff, "nope", 1) is None
d2 = """diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1,3 +1,2 @@
 a
--- comment
 c
@@ -10,1 +9,2 @@
 q
+w
diff --git a/c.py b/c.py
--- a/c.py
+++ b/c.py
@@ -1,1 +1,2 @@
 e
+f
"""
assert "--- comment" in ft.hunk_at(d2, "b.py", 2)
assert ft.hunk_at(d2, "b.py", 10).endswith("+w")
assert ft.hunk_at(d2, "c.py", 2).endswith("+f") and ft.hunk_at(d2, "c.py", 10) is None

f = ft.fence("a\n`````\nb")
assert f.startswith("``````diff\n") and f.endswith("\n``````")
assert ft.fence("x").startswith("```diff\n")


class Drop(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers["Content-Length"]))
        self.send_response(200)
        self.send_header("Content-Length", "500")
        self.end_headers()
        self.wfile.write(b'{"content":[')
        self.wfile.flush()
        self.close_connection = True

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), Drop)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f"http://127.0.0.1:{srv.server_port}/v1/messages"
r = ft.classify("diff --git a b\n+x\n", "sys", "k", url)
assert r["verdict"] == "critical" and r["flags"][0]["file"] == "(input)", r
srv.shutdown()
assert ft.classify("", "s", "k") == {"verdict": "fast", "flags": []}
assert ft.classify("x" * 300_001, "s", "k")["verdict"] == "critical"
import subprocess
import tempfile

with tempfile.TemporaryDirectory() as d:
    def g(*a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=d, check=True, capture_output=True)
    g("init", "-q")
    Path(d, "a.py").write_text("x = 1\n")
    g("add", "."); g("commit", "-qm", "base")
    base = ft.sh("git", "rev-parse", "HEAD", cwd=d).strip()
    Path(d, ".gitattributes").write_text("* -diff\n")
    Path(d, "a.py").write_text("x = 1\nos.system(evil)\n")
    g("add", "."); g("commit", "-qm", "head")
    out = ft.build_diff(base, "HEAD", cwd=d)
    assert "+os.system(evil)" in out, out
print("ok")
