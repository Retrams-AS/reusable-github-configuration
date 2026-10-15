import json
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
assert ft.prompt_effort("---\nmodel: haiku\neffort: high\n---\neffort: low\n") == "high"
for bad in ("---\nmodel: haiku\n---\neffort: high\n", "---\neffort: extreme\n---\nx\n", "effort: high\n"):
    try:
        ft.prompt_effort(bad)
        raise AssertionError(bad)
    except ValueError:
        pass

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
r = ft.classify("diff --git a b\n+x\n", "sys", "high", "k", f"http://127.0.0.1:{srv.server_port}")
assert r["verdict"] == "critical" and r["flags"][0]["file"] == "(input)", r
srv.shutdown()
assert ft.classify("", "s", "high", "k") == {"verdict": "fast", "flags": []}
assert ft.classify("x" * 1_000_001, "s", "high", "k")["verdict"] == "critical"

# A well-behaved fake API: counts tokens, answers with a thinking block before the text.
A = {}


class Claude(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        A.setdefault("calls", []).append((self.path, body))
        A["auth"] = (self.headers.get("authorization"), self.headers.get("x-api-key"))
        out = ({"input_tokens": A["tokens"]} if self.path.endswith("/count_tokens") else
               {"content": [{"type": "thinking", "thinking": ""}], "stop_reason": "refusal"} if A.get("refuse") else
               {"content": [{"type": "thinking", "thinking": ""},
                            {"type": "text", "text": '{"verdict": "fast", "flags": []}'}]})
        b = json.dumps(out).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers()
        self.wfile.write(b)

    def log_message(self, *a):
        pass


srv = http.server.HTTPServer(("127.0.0.1", 0), Claude)
threading.Thread(target=srv.serve_forever, daemon=True).start()
api_url = f"http://127.0.0.1:{srv.server_port}"
A.update(tokens=100_000, calls=[])
assert ft.classify("+x\n", "sys", "high", "k", api_url) == {"verdict": "fast", "flags": []}
(p1, b1), (p2, b2) = A["calls"]
assert p1 == "/v1/messages/count_tokens" and p2 == "/v1/messages", A["calls"]
assert A["auth"] == ("Bearer k", None), A["auth"]
assert b2["output_config"] == {"effort": "high"} and "temperature" not in b2 and b2["model"] == ft.MODEL, b2
A.update(tokens=100_001, calls=[])
r = ft.classify("+x\n", "sys", "high", "k", api_url)
assert r["verdict"] == "critical" and "100001" in r["flags"][0]["why"] and len(A["calls"]) == 1, (r, A)
A.update(tokens=10, calls=[], refuse=True)
r = ft.classify("+x\n", "sys", "high", "k", api_url)
assert r["verdict"] == "critical" and "refusal" in r["flags"][0]["why"], r
srv.shutdown()
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

# --- run() end to end: real git, fake GitHub API, canned model ---
import os

KEY = "k"
PR_OK = next(i for i in range(1, 99) if not ft.sampled(KEY.encode(), "o/r", i, 5))
PR_AUDIT = next(i for i in range(1, 99) if ft.sampled(KEY.encode(), "o/r", i, 5))
S = {}


class Fake(http.server.BaseHTTPRequestHandler):
    def reply(self, obj):
        b = json.dumps(obj).encode()
        self.send_response(200); self.send_header("content-length", str(len(b))); self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if "/pulls?head=" in self.path:
            self.reply([S["pr"]])
        elif "/pulls/" in self.path:
            self.reply({"head": {"sha": S["head2"]}})
        elif "/statuses" in self.path:
            self.reply(S["statuses"])
        else:
            self.send_error(404)

    def do_POST(self):
        S["posts"].append((self.path, json.loads(self.rfile.read(int(self.headers["content-length"])))))
        self.reply({})

    def log_message(self, *a):
        pass


api = http.server.HTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=api.serve_forever, daemon=True).start()

with tempfile.TemporaryDirectory() as d:
    def g(*a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=d, check=True, capture_output=True)

    def put(name, text):
        Path(d, name).parent.mkdir(parents=True, exist_ok=True)
        Path(d, name).write_text(text)
    g("init", "-q", "-b", "main")
    put(".github/risk-paths.yaml", 'fast: ["docs/**"]\n')
    put("docs/x.md", "one\ntwo\n")
    g("add", "."); g("commit", "-qm", "base")
    base = ft.sh("git", "rev-parse", "HEAD", cwd=d).strip()
    pf = Path(d + ".prompt.md"); pf.write_text("---\nname: x\neffort: high\n---\nsystem\n")

    def case(files, model, statuses=(), pr=PR_OK, base_ref="main", head2=None, start=None):
        g("checkout", "-q", "-B", "feat", start or base)
        for k, v in files.items():
            put(k, v)
        g("add", "."); g("commit", "-qm", "head")
        sha = ft.sh("git", "rev-parse", "HEAD", cwd=d).strip()
        S.update(posts=[], head2=head2 or sha, statuses=list(statuses), called=False, pr={
            "number": pr, "head": {"sha": sha},
            "base": {"ref": base_ref, "sha": base, "repo": {"default_branch": "main"}}})

        def haiku(*a):
            S["called"] = True
            return json.dumps(model)
        ft.call_haiku = haiku
        ft.count_tokens = lambda *a: 10
        os.environ.update(GITHUB_REPOSITORY="o/r", GITHUB_REF_NAME="feat", GITHUB_SHA=sha,
                          GITHUB_API_URL=f"http://127.0.0.1:{api.server_port}", GH_TOKEN="t",
                          APP_SLUG="app", ANTHROPIC_ACCESS_TOKEN="a", AUDIT_KEY=KEY,
                          PROMPT_FILE=str(pf))
        cwd = os.getcwd(); os.chdir(d)
        try:
            ft.run(); code = 0
        except SystemExit as e:
            code = e.code
        finally:
            os.chdir(cwd)
        P = S["posts"]
        status = [b["state"] for p, b in P if "/statuses/" in p]
        assert all(p.endswith(f"/statuses/{sha}") for p, b in P if "/statuses/" in p)
        reviews = [b for p, b in P if p.endswith("/reviews")]
        comments = [b["body"] for p, b in P if p.endswith("/comments")]
        labels = [b for p, b in P if p.endswith("/labels")]
        return sha, code, status, reviews, comments, labels

    FAST = {"verdict": "fast", "flags": []}
    DOC = {"docs/x.md": "one\nTWO\n"}

    # 1
    sha, code, st, rv, cm, lb = case(DOC, FAST)
    assert code == 0 and st == ["success"] and not cm and not lb, (code, st, cm)
    assert len(rv) == 1 and rv[0]["event"] == "APPROVE" and rv[0]["commit_id"] == sha, rv
    # 2
    sha, code, st, rv, cm, lb = case({**DOC, "src/y.py": "x\n"}, FAST)
    assert code == 0 and st == ["failure"] and not rv and len(cm) == 1 and "src/y.py" in cm[0], (st, cm)
    assert not S["called"], "the floor is already critical; the model must not be asked"
    # 3
    sha, code, st, rv, cm, lb = case({".github/risk-paths.yaml": 'fast: ["**"]\n', "src/y.py": "x\n"}, FAST)
    assert st == ["failure"] and not rv and "src/y.py" in cm[0] and ".github/risk-paths.yaml" in cm[0], (st, cm)
    # 4
    crit = {"verdict": "critical", "flags": [{"file": "docs/x.md", "line": 1, "trigger": "auth", "why": "because"}]}
    sha, code, st, rv, cm, lb = case(DOC, crit)
    assert st == ["failure"] and not rv and len(cm) == 1, (st, cm)
    assert "docs/x.md:1" in cm[0] and "because" in cm[0] and "+TWO" in cm[0] and "@@" in cm[0], cm
    # 5
    sticky = [{"context": "fast-track", "state": "failure", "creator": {"login": "app[bot]"}}]
    sha, code, st, rv, cm, lb = case(DOC, FAST, statuses=sticky)
    assert not S["called"] and st == ["failure"] and not rv and len(cm) == 1, (S["called"], st, cm)
    # 5b: same status by someone else is not sticky
    sha, code, st, rv, cm, lb = case(DOC, FAST, statuses=[{**sticky[0], "creator": {"login": "mallory"}}])
    assert S["called"] and st == ["success"] and len(rv) == 1, (st, rv)
    # 6
    sha, code, st, rv, cm, lb = case(DOC, FAST, base_ref="other")
    assert code == 1 and st == ["failure"] and not rv, (code, st, rv)
    # 7
    sha, code, st, rv, cm, lb = case(DOC, FAST, head2="0" * 40)
    assert code == 1 and not rv and st[-1] == "failure", (code, st, rv)
    # 8
    sha, code, st, rv, cm, lb = case(DOC, FAST, pr=PR_AUDIT)
    assert code == 0 and not rv and lb == [{"labels": ["fast-track-audit"]}], (rv, lb)
    assert len(cm) == 1 and "audit sample" in cm[0], cm
    # 9: criss-cross. main and the head both merge X and Y, so base...head has two merge bases and
    # git diffs against whichever it picks, which can hide the head's revert of Y. Only the tree
    # that would land gives the exact answer: y.py changes, x.py does not.
    g("checkout", "-q", "main"); put("src/arm/x.py", "unsafe\n"); put("src/arm/y.py", "unsafe\n")
    g("add", "."); g("commit", "-qm", "r2")
    for b in ("x", "y"):
        g("checkout", "-q", "-B", b, "main"); put(f"src/arm/{b}.py", "safe\n"); g("add", "."); g("commit", "-qm", b)
    g("checkout", "-q", "-B", "atk", "x"); g("merge", "-q", "--no-ff", "-m", "a", "y")
    g("checkout", "-q", "main"); g("merge", "-q", "--no-ff", "-m", "m", "y"); g("merge", "-q", "--no-ff", "-m", "m", "x")
    base = ft.sh("git", "rev-parse", "main", cwd=d).strip()
    assert len(ft.sh("git", "merge-base", "--all", base, "atk", cwd=d).split()) == 2
    sha, code, st, rv, cm, lb = case({"src/arm/y.py": "unsafe\n"}, FAST, start="atk")
    assert st == ["failure"] and not rv and "src/arm/y.py" in cm[0] and "x.py" not in cm[0], (st, rv, cm)
api.shutdown()
pf.unlink()
print("ok")
