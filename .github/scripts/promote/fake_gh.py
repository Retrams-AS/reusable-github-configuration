"""`gh api` over a local bare repo ($FAKE_REPO), for the promote endpoints only.

Commits are authored as $FAKE_LOGIN; compare reports that name as author.login.
"""

import base64
import json
import os
import re
import subprocess
import sys

REPO = os.environ["FAKE_REPO"]


def git(*a, inp=None, env=None):
    return subprocess.run(
        ["git", "-C", REPO, *a], input=inp, env={**os.environ, **(env or {})},
        capture_output=True, text=True, check=True,
    ).stdout.strip()


def handle(method, path, fields, body):
    path, _, query = path.partition("?")
    p = re.sub(r"^repos/[^/]+/[^/]+/", "", path)
    if m := re.fullmatch(r"contents/(.+)", p):
        ref = query.removeprefix("ref=")
        try:
            data = git("show", f"{ref}:{m[1]}")
        except subprocess.CalledProcessError:
            return None
        return {"content": base64.b64encode((data + "\n").encode()).decode()}
    if p == "git/blobs":
        data = base64.b64decode(fields["content"]).decode()
        return {"sha": git("hash-object", "-w", "--stdin", inp=data)}
    if m := re.fullmatch(r"commits/(\w+)", p):
        return {"commit": {"tree": {"sha": git("rev-parse", f"{m[1]}^{{tree}}")}}}
    if p == "git/trees":
        idx = {"GIT_INDEX_FILE": f"{REPO}/fake-index"}
        git("read-tree", body["base_tree"], env=idx)
        for e in body["tree"]:
            git("update-index", "--add", "--cacheinfo", f"{e['mode']},{e['sha']},{e['path']}", env=idx)
        return {"sha": git("write-tree", env=idx)}
    if p == "git/commits":
        who = {"GIT_AUTHOR_NAME": os.environ["FAKE_LOGIN"], "GIT_AUTHOR_EMAIL": "a@a",
               "GIT_COMMITTER_NAME": "c", "GIT_COMMITTER_EMAIL": "c@c"}
        args = [x for par in body["parents"] for x in ("-p", par)]
        return {"sha": git("commit-tree", body["tree"], *args, "-m", body["message"], env=who)}
    if m := re.fullmatch(r"git/refs?/heads/(.+)", p):
        ref = f"refs/heads/{m[1]}"
        if method == "PATCH":
            old = git("rev-parse", ref)
            if subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor", old, fields["sha"]]).returncode:
                print("Update is not a fast forward (HTTP 422)", file=sys.stderr)
                return None
            git("update-ref", ref, fields["sha"], old)
        return {"object": {"sha": git("rev-parse", ref)}}
    if m := re.fullmatch(r"compare/(\w+)\.\.\.(\w+)", p):
        a, b = m[1], m[2]
        ahead = subprocess.run(["git", "-C", REPO, "merge-base", "--is-ancestor", a, b]).returncode == 0
        shas = git("rev-list", "--reverse", f"{a}..{b}").split()
        commits = [{"sha": s, "author": {"login": git("log", "-1", "--format=%an", s)},
                    "commit": {"message": git("log", "-1", "--format=%B", s)}} for s in shas]
        files = [{"filename": f} for f in git("diff", "--name-only", a, b).split()]
        return {"status": "ahead" if ahead else "diverged", "total_commits": len(shas),
                "commits": commits, "files": files}
    raise SystemExit(f"fake_gh: unhandled {method} {path}")


def main(argv):
    assert argv[0] == "api", argv
    method, path, fields, body, jq = "GET", None, {}, None, None
    it = iter(argv[1:])
    for a in it:
        if a == "--method":
            method = next(it)
        elif a == "-f":
            k, _, v = next(it).partition("=")
            fields[k] = v
        elif a == "--input":
            next(it)
            body = json.load(sys.stdin)
        elif a == "--jq":
            jq = next(it)
        else:
            path = a
    if body is not None or (fields and method == "GET"):
        method = "POST" if method == "GET" else method
    out = handle(method, path, fields, body)
    if out is None:
        sys.exit(1)
    out = json.dumps(out)
    if jq:
        out = subprocess.run(["jq", "-r", jq], input=out, capture_output=True, text=True, check=True).stdout.strip()
    print(out)


main(sys.argv[1:])
