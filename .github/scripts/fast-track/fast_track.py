# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml==6.0.2", "tree-sitter-language-pack==1.22.1"]
# ///
"""Fast-track classifier: decides whether a PR may be approved by the bot."""
import fnmatch
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

from symbols import function_at, spans

TRIGGERS = {"hardware", "data", "contract", "auth", "reviewer"}
API = "https://api.anthropic.com"
MODEL = "claude-haiku-5-5"
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
MAX_COMMENT = 60_000
MARKER = "<!-- fast-track -->"
CHECK = "fast-track"
# A critical PR is not broken, it needs a human, so it is neutral; failure is for a run that errored.
CONCLUSION = {"fast": "success", "critical": "neutral"}


def strip_frontmatter(text):
    return text.split("\n---\n", 1)[1] if text.startswith("---\n") else text


def prompt_effort(text):
    """The `effort:` line of the agent file's frontmatter, the way agent-plugins' check.sh reads it."""
    head = text.split("\n---\n", 1)[0] if text.startswith("---\n") else ""
    m = re.search(r"^effort: *(\S+) *$", head, re.M)
    if not m or m[1] not in EFFORTS:
        raise ValueError(f"prompt frontmatter has no valid effort: {m and m[1]!r}")
    return m[1]


MAP_KEYS = {"fast", "critical", "critical-symbols", "audit-rate"}


def check_map(m):
    if not isinstance(m, dict):
        raise ValueError("risk-paths.yaml is not a mapping")
    # An unknown key would look like a rule while enforcing nothing.
    unknown = set(m) - MAP_KEYS
    if unknown:
        raise ValueError(f"risk-paths.yaml: unknown keys {sorted(unknown)}")
    cs = m.get("critical-symbols", [])
    if not isinstance(cs, list) or not all(isinstance(g, str) and "::" in g for g in cs):
        raise ValueError("risk-paths.yaml: critical-symbols must be a list of '<path glob>::<name glob>'")
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


def changed_lines(base, head, path):
    """(old lines, new lines) a zero-context diff changes in path; a pure insertion also marks the
    old line it lands after, so code inserted into a function counts for that function."""
    old, new = set(), set()
    out = sh("git", "diff", "-U0", "--no-ext-diff", "--no-textconv", "--no-renames", base, head, "--", path)
    for m in re.finditer(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", out, re.M):
        a, b, c, d = int(m[1]), int(m[2] or 1), int(m[3]), int(m[4] or 1)
        old |= set(range(a, a + b)) | ({a} if b == 0 else set())
        new |= set(range(c, c + d))
    return old, new


def held(path, risk_map, base=None, landed=None):
    """Why the floor holds this changed path, or None when it is on the fast lane.

    A path named by `critical-symbols` is held only where the innermost function around a changed
    line is named, on either side of the change. A file the parser cannot read is held whole.
    """
    if not on_fast_lane(path, risk_map):
        return "off the fast lane"
    names = [pat.partition("::")[2] for pat in risk_map.get("critical-symbols", [])
             if PurePosixPath(path).full_match(pat.partition("::")[0])]
    if not names or base is None:
        return None
    for rev, lines in zip((base, landed), changed_lines(base, landed, path)):
        if not lines:
            continue
        try:
            source = sh("git", "show", f"{rev}:{path}")
        except subprocess.CalledProcessError:
            continue  # added or deleted: the other side has it
        try:
            found = spans(path, source)
        except ValueError as e:
            return f"named functions, but {e}"
        for line in sorted(lines):
            # The innermost function decides: an outer wrapper is labelled by its own code, and
            # each function nested in it has its own entry.
            inside = [s for s in found if s[0] <= line <= s[1]]
            if not inside:
                continue
            name = max(inside, key=lambda s: s[0])[2]
            if any(fnmatch.fnmatchcase(name, n) for n in names):
                return f"critical function `{name}`"
    return None


def floor(paths, risk_map, base=None, landed=None):
    """{path: reason} for every changed path the floor holds."""
    return {p: why for p in paths if (why := held(p, risk_map, base, landed))}


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


def anthropic(path, body, token, api=API, timeout=90):
    req = urllib.request.Request(api + path, json.dumps(body).encode(), {
        "authorization": f"Bearer {token}", "anthropic-version": "2023-06-01",
        "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def call_haiku(diff, system, effort, token, api=API):
    # No temperature: Haiku 5.5 rejects non-default sampling. It thinks by default, so the answer
    # is the first text block, not content[0]; a refusal has none and raises.
    r = anthropic("/v1/messages", {
        "model": MODEL, "max_tokens": 16000, "output_config": {"effort": effort},
        "system": system, "messages": [{"role": "user", "content": diff}]}, token, api, timeout=300)
    text = next((b["text"] for b in r["content"] if b["type"] == "text"), None)
    if text is None:
        raise ValueError(f"no text in the reply, stop_reason {r.get('stop_reason')}")
    return text


def critical_input(why):
    return {"verdict": "critical",
            "flags": [{"file": "(input)", "line": 0, "trigger": "contract", "why": why}]}


def classify(diff, system, effort, token, api=API):
    if not diff.strip():
        return {"verdict": "fast", "flags": []}
    # No size cap: a diff too big for the model fails the call, and a failure is critical.
    try:
        return parse_verdict(call_haiku(diff, system, effort, token, api))
    except Exception as e:
        return critical_input(f"classifier error: {type(e).__name__}: {e}")


def landed_text(landed, path):
    try:
        return sh("git", "show", f"{landed}:{path}")
    except subprocess.CalledProcessError:
        return ""  # deleted in the PR


def sh(*args, cwd=None):
    return subprocess.run(args, check=True, capture_output=True, text=True, cwd=cwd).stdout


def build_diff(base, head, cwd=None):
    # --no-textconv --text: a PR's .gitattributes (`-diff`, `diff=` drivers) must not hide code from the model.
    return sh("git", "diff", "--no-ext-diff", "--no-textconv", "--text", "--no-color",
              "--no-renames", base, head, cwd=cwd)


def gh(method, path, body=None):
    req = urllib.request.Request(
        os.environ.get("GITHUB_API_URL", "https://api.github.com") + path,
        None if body is None else json.dumps(body).encode(), method=method,
        headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def check_body(sha, conclusion, title):
    return {"name": CHECK, "head_sha": sha, "status": "completed", "conclusion": conclusion,
            "output": {"title": title[:139], "summary": title}}


def run():
    e = os.environ
    repo = e["FT_REPO"]
    st = {"repo": repo, "sha": None, "pr": None}
    try:
        # The inputs are untrusted: anyone who can dispatch picks them. They only choose what to judge.
        if not re.fullmatch(re.escape(e["GITHUB_REPOSITORY_OWNER"]) + r"/[A-Za-z0-9._-]+", repo):
            raise RuntimeError(f"repo {repo!r} is not a repository in {e['GITHUB_REPOSITORY_OWNER']}")
        pr = int(e["FT_PR"])
        p = gh("GET", f"/repos/{repo}/pulls/{pr}")
        if p["state"] != "open":
            raise RuntimeError(f"PR {pr} is {p['state']}")
        sha = p["head"]["sha"]
        st.update(sha=sha, pr=pr)
        b = p["base"]
        # A PR on an author-controlled branch would read that branch's map and carry its unreviewed commits on retarget.
        if b["ref"] != b["repo"]["default_branch"]:
            raise RuntimeError(f"PR base {b['ref']} is not the default branch")
        base = b["sha"]

        runs = []
        for page in range(1, 11):
            got = gh("GET", f"/repos/{repo}/commits/{sha}/check-runs"
                            f"?check_name={CHECK}&filter=all&per_page=100&page={page}")["check_runs"]
            runs += got
            if len(got) < 100:
                break
        sticky = any(r["conclusion"] in ("neutral", "failure")
                     and (r.get("app") or {}).get("slug") == e["APP_SLUG"]
                     for r in runs)

        # Judge the tree that would land, not base...sha: with two merge bases git picks one, and
        # a revert of the other side's change vanishes from that diff. A conflict exits non-zero.
        landed = sh("git", "merge-tree", "--write-tree", base, sha).split("\n")[0]
        paths = [p for p in sh("git", "diff", "--no-renames", "--name-only", "-z", base, landed).split("\0") if p]
        try:
            risk_map = yaml.safe_load(sh("git", "show", f"{base}:.github/risk-paths.yaml")) or {}
        except subprocess.CalledProcessError:
            risk_map = {}  # absent at base: every path is critical
        check_map(risk_map)
        off = floor(paths, risk_map, base, landed)
        diff = build_diff(base, landed)

        if sticky:
            model = critical_input("an earlier run already judged this sha critical; push a new commit")
        else:
            # Asked even when the floor is critical: its flags tell the reviewer where to look.
            with open(e["PROMPT_FILE"]) as f:
                agent = f.read()
            model = classify(diff, strip_frontmatter(agent), prompt_effort(agent), e["ANTHROPIC_ACCESS_TOKEN"])
        verdict = decide(off, model)
        audit = sampled(e["AUDIT_KEY"].encode(), repo, pr, risk_map.get("audit-rate", 5))

        desc = f"{verdict}: {len(off)} path(s) off the fast lane, model {model['verdict']}"
        gh("POST", f"/repos/{repo}/check-runs", check_body(sha, CONCLUSION[verdict], desc))
        if verdict == "fast" and not audit:
            if gh("GET", f"/repos/{repo}/pulls/{pr}")["head"]["sha"] != sha:
                raise RuntimeError("PR head moved before approval")
            gh("POST", f"/repos/{repo}/pulls/{pr}/reviews",
               {"commit_id": sha, "event": "APPROVE", "body": "fast-track: approved by the classifier."})
        else:
            lines = [MARKER, f"fast-track verdict: **{verdict}** (model said `{model['verdict']}`)."]
            if audit:
                lines.append("This PR is in the audit sample and is never auto-approved. Please review it in full.")
            if model["flags"]:
                lines += ["", "**Read these first.** The model judged the rest of the diff fast."]
            for f in model["flags"]:
                where = f"`{f['file']}:{f['line']}`"
                fn = function_at(f["file"], landed_text(landed, f["file"]), f["line"])
                if fn:
                    where = f"`{f['file']}` › `{fn}` (line {f['line']})"
                lines += ["", f"{where} ({f['trigger']}): {f['why']}"]
                h = hunk_at(diff, f["file"], f["line"])
                if h:
                    lines.append(fence(h))
            flagged = {f["file"] for f in model["flags"]}
            quiet = [p for p in off if p not in flagged]
            if quiet:
                lines += ["", "Held by the path map, nothing flagged by the model:"] + [
                    f"- `{p}`: {off[p]}" for p in quiet]
            gh("POST", f"/repos/{repo}/issues/{pr}/comments", {"body": "\n".join(lines)[:MAX_COMMENT]})
        if audit:
            gh("POST", f"/repos/{repo}/issues/{pr}/labels", {"labels": ["fast-track-audit"]})
    except Exception as ex:
        print(f"fast-track failed: {ex!r}", file=sys.stderr)
        for path, body in (
            (st["sha"] and f"/repos/{repo}/check-runs", check_body(st["sha"], "failure", "classifier errored; critical")),
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
