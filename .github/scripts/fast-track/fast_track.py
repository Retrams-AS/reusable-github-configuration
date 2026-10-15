# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml==6.0.2"]
# ///
"""Fast-track classifier: decides whether a PR may be approved by the bot."""
import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import PurePosixPath

import yaml

TRIGGERS = {"hardware", "data", "contract", "auth", "reviewer"}
MAX_DIFF = 300_000
MAX_COMMENT = 60_000
MARKER = "<!-- fast-track -->"


def strip_frontmatter(text):
    return text.split("\n---\n", 1)[1] if text.startswith("---\n") else text


def check_map(m):
    if not isinstance(m, dict):
        raise ValueError("risk-paths.yaml is not a mapping")
    for k in ("fast", "critical"):
        v = m.get(k, [])
        if not isinstance(v, list) or not all(isinstance(g, str) for g in v):
            raise ValueError(f"risk-paths.yaml: {k} must be a list of strings")
    r = m.get("audit-rate", 5)
    if not isinstance(r, int) or isinstance(r, bool) or r < 1:
        raise ValueError("risk-paths.yaml: audit-rate must be a positive int")


def on_fast_lane(path, risk_map):
    check_map(risk_map)
    p = PurePosixPath(path)
    # .github/ is critical whatever the map says: it holds the map and the workflows.
    if p.parts[:1] == (".github",):
        return False
    return (any(p.full_match(g) for g in risk_map.get("fast", []))
            and not any(p.full_match(g) for g in risk_map.get("critical", [])))


def floor(paths, risk_map):
    return [p for p in paths if not on_fast_lane(p, risk_map)]


def parse_verdict(text):
    try:
        v = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"not JSON: {e}")
    if not isinstance(v, dict) or set(v) != {"verdict", "flags"}:
        raise ValueError("object must have exactly verdict and flags")
    if v["verdict"] not in ("fast", "critical", "denied"):
        raise ValueError("bad verdict")
    if not isinstance(v["flags"], list):
        raise ValueError("flags is not a list")
    for f in v["flags"]:
        if (not isinstance(f, dict) or set(f) != {"file", "line", "trigger", "why"}
                or not isinstance(f["file"], str) or not isinstance(f["why"], str)
                or not isinstance(f["line"], int) or isinstance(f["line"], bool)
                or f["trigger"] not in TRIGGERS):
            raise ValueError(f"bad flag: {f!r}")
    if (v["verdict"] == "critical") != bool(v["flags"]) and v["verdict"] != "denied":
        raise ValueError("critical needs flags; fast has none")
    if v["verdict"] == "denied" and v["flags"]:
        raise ValueError("denied has no flags")
    return v


def decide(off_lane, model):
    return "fast" if not off_lane and model["verdict"] == "fast" else "critical"


def sampled(key, repo, pr, rate):
    d = hmac.new(key, f"{repo}#{pr}".encode(), hashlib.sha256).digest()
    return int.from_bytes(d, "big") % rate == 0


def hunk_at(diff, file, line):
    cur = old = None
    header = False  # ---/+++ are file headers only between `diff --git` and the first @@
    hunks = []  # (file, old_lo, old_hi, new_lo, new_hi, text)
    for l in diff.split("\n"):
        if l.startswith("diff --git "):
            header = True
        elif header and l.startswith("--- "):
            old = l[6:] if l.startswith("--- a/") else None
        elif header and l.startswith("+++ "):
            cur = l[6:] if l.startswith("+++ b/") else old  # deleted file: /dev/null
        elif m := re.match(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", l):
            header = False
            o, oc, n, nc = (int(x) if x is not None else 1 for x in m.groups())
            hunks.append([cur, o, o + oc, n, n + nc, l])
        elif hunks and not header and l[:1] in (" ", "+", "-", "\\"):
            hunks[-1][5] += "\n" + l
    mine = [h for h in hunks if h[0] == file]
    for h in mine:
        if h[3] <= line < h[4]:
            return h[5]
    for h in mine:
        if h[1] <= line < h[2]:
            return h[5]
    return None


def fence(text):
    run = max((len(m) for m in re.findall(r"`+", text)), default=0)
    t = "`" * max(3, run + 1)
    return f"{t}diff\n{text}\n{t}"


def call_haiku(diff, system, api_key, url="https://api.anthropic.com/v1/messages", timeout=90):
    body = json.dumps({"model": "claude-haiku-5-5", "max_tokens": 2048, "temperature": 0,
                       "system": system,
                       "messages": [{"role": "user", "content": diff}]}).encode()
    req = urllib.request.Request(url, body, {
        "x-api-key": api_key, "anthropic-version": "2023-06-01",
        "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)["content"][0]["text"]


def critical_input(why):
    return {"verdict": "critical",
            "flags": [{"file": "(input)", "line": 0, "trigger": "contract", "why": why}]}


def classify(diff, system, api_key, url="https://api.anthropic.com/v1/messages"):
    if not diff.strip():
        return {"verdict": "fast", "flags": []}
    if len(diff) > MAX_DIFF:
        return critical_input(f"diff is {len(diff)} characters, over the {MAX_DIFF} limit")
    try:
        return parse_verdict(call_haiku(diff, system, api_key, url))
    except Exception as e:
        return critical_input(f"classifier error: {type(e).__name__}: {e}")


def sh(*args, cwd=None):
    return subprocess.run(args, check=True, capture_output=True, text=True, cwd=cwd).stdout


def build_diff(base, head, cwd=None):
    # --no-textconv --text: a PR's .gitattributes (`-diff`, `diff=` drivers) must not hide code from the model.
    return sh("git", "diff", "--no-ext-diff", "--no-textconv", "--text", "--no-color",
              "--no-renames", f"{base}...{head}", cwd=cwd)


def gh(method, path, body=None):
    req = urllib.request.Request(
        os.environ.get("GITHUB_API_URL", "https://api.github.com") + path,
        None if body is None else json.dumps(body).encode(), method=method,
        headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def run():
    e = os.environ
    repo, sha = e["GITHUB_REPOSITORY"], e["GITHUB_SHA"]
    st = {"repo": repo, "sha": sha, "pr": None}
    try:
        q = urllib.parse.quote(f"{repo.split('/')[0]}:{e['GITHUB_REF_NAME']}")
        prs = gh("GET", f"/repos/{repo}/pulls?head={q}&state=open")
        if len(prs) != 1 or prs[0]["head"]["sha"] != sha:
            raise RuntimeError(f"need exactly one open PR with head {sha}, found {len(prs)}")
        b = prs[0]["base"]
        # A PR on an author-controlled branch would read that branch's map and carry its unreviewed commits on retarget.
        if b["ref"] != b["repo"]["default_branch"]:
            raise RuntimeError(f"PR base {b['ref']} is not the default branch")
        pr, base = prs[0]["number"], b["sha"]
        st["pr"] = pr

        statuses = []
        for page in range(1, 11):
            got = gh("GET", f"/repos/{repo}/commits/{sha}/statuses?per_page=100&page={page}")
            statuses += got
            if len(got) < 100:
                break
        sticky = any(s["context"] == "fast-track" and s["state"] == "failure"
                     and (s.get("creator") or {}).get("login") == f"{e['APP_SLUG']}[bot]"
                     for s in statuses)

        rng = f"{base}...{sha}"
        paths = [p for p in sh("git", "diff", "--no-renames", "--name-only", "-z", rng).split("\0") if p]
        try:
            risk_map = yaml.safe_load(sh("git", "show", f"{base}:.github/risk-paths.yaml")) or {}
        except subprocess.CalledProcessError:
            risk_map = {}  # absent at base: every path is critical
        check_map(risk_map)
        off = floor(paths, risk_map)
        diff = build_diff(base, sha)

        if sticky:
            model = critical_input("an earlier run already failed this sha; push a new commit")
        else:
            with open(e["PROMPT_FILE"]) as f:
                system = strip_frontmatter(f.read())
            model = classify(diff, system, e["ANTHROPIC_API_KEY"])
        verdict = decide(off, model)
        audit = sampled(e["AUDIT_KEY"].encode(), repo, pr, risk_map.get("audit-rate", 5))

        desc = f"{verdict}: {len(off)} path(s) off the fast lane, model {model['verdict']}"
        gh("POST", f"/repos/{repo}/statuses/{sha}",
           {"state": "success" if verdict == "fast" else "failure",
            "context": "fast-track", "description": desc[:139]})
        if verdict == "fast" and not audit:
            if gh("GET", f"/repos/{repo}/pulls/{pr}")["head"]["sha"] != sha:
                raise RuntimeError("PR head moved before approval")
            gh("POST", f"/repos/{repo}/pulls/{pr}/reviews",
               {"commit_id": sha, "event": "APPROVE", "body": "fast-track: approved by the classifier."})
        else:
            lines = [MARKER, f"fast-track verdict: **{verdict}** (model said `{model['verdict']}`)."]
            if audit:
                lines.append("This PR is in the audit sample and is never auto-approved. Please review it in full.")
            if off:
                lines += ["", "Paths off the fast lane:"] + [f"- `{p}`" for p in off]
            for f in model["flags"]:
                lines += ["", f"`{f['file']}:{f['line']}` ({f['trigger']}): {f['why']}"]
                h = hunk_at(diff, f["file"], f["line"])
                if h:
                    lines.append(fence(h))
            gh("POST", f"/repos/{repo}/issues/{pr}/comments", {"body": "\n".join(lines)[:MAX_COMMENT]})
        if audit:
            gh("POST", f"/repos/{repo}/issues/{pr}/labels", {"labels": ["fast-track-audit"]})
    except Exception as ex:
        print(f"fast-track failed: {ex!r}", file=sys.stderr)
        for path, body in (
            (f"/repos/{repo}/statuses/{sha}", {"state": "failure", "context": "fast-track",
                                              "description": "classifier errored; critical"}),
            (st["pr"] and f"/repos/{repo}/issues/{st['pr']}/comments", {"body": f"{MARKER}\nThe fast-track classifier errored, so this PR is critical."}),
        ):
            try:
                if path is not None:
                    gh("POST", path, body)
            except Exception as ex2:
                print(f"best-effort call failed: {ex2!r}", file=sys.stderr)
        sys.exit(1)


def main():
    if sys.argv[1:] != ["run"]:
        sys.exit("usage: fast_track.py run")
    run()


if __name__ == "__main__":
    main()
