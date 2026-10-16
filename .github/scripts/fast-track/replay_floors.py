# /// script
# requires-python = ">=3.13"
# dependencies = ["pyyaml==6.0.2", "tree-sitter-language-pack==1.22.1"]
# ///
"""Replays a repo's merged PRs through several floors and counts how many each sends to the model.

usage: replay_floors.py <checkout> <owner/repo> <name>=<map.yaml> ...
A map named `master` is read from the checkout's default branch instead of a file.
"""
import json
import subprocess
import sys

import yaml

import symbol_floor as sf


def main():
    checkout, repo, *specs = sys.argv[1:]
    maps = {}
    for spec in specs:
        name, _, path = spec.partition("=")
        if path == "master":
            branch = sf.sh("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=checkout).strip()
            maps[name] = yaml.safe_load(sf.sh("git", "show", f"{branch}:.github/risk-paths.yaml", cwd=checkout))
        else:
            maps[name] = yaml.safe_load(open(path))
    prs = json.loads(subprocess.run(
        ["gh", "pr", "list", "-R", repo, "--state", "merged", "-L", "500",
         "--json", "number,title,mergeCommit"], check=True, capture_output=True, text=True).stdout)
    rows, reach = [], {n: 0 for n in maps}
    for pr in sorted(prs, key=lambda p: p["number"]):
        head = pr["mergeCommit"]["oid"]
        try:
            base = sf.sh("git", "rev-parse", f"{head}^1", cwd=checkout).strip()
        except subprocess.CalledProcessError:
            continue  # merge commit not in the local clone
        paths = [p for p in sf.sh("git", "diff", "--no-renames", "--name-only", base, head, cwd=checkout).split("\n") if p]
        row = {"pr": pr["number"], "title": pr["title"][:60], "files": len(paths)}
        for name, m in maps.items():
            why = {p: r for p in paths if (r := sf.held(p, base, head, m, cwd=checkout))}
            row[name] = why
            reach[name] += not why
        rows.append(row)
    print(json.dumps({"repo": repo, "prs": len(rows), "reach_model": reach, "rows": rows}, indent=1))


if __name__ == "__main__":
    main()
