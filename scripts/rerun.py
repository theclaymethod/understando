#!/usr/bin/env python3
"""Diff a new trust map against an earlier one.

    python3 scripts/rerun.py OLD.json NEW.json [--fail-on-drop]

Prints, in Markdown: the head change, claims that came or went, each verdict change, each
verifier state change, and each control whose result changed. A drop is a verdict that moves
down the order Formal > Proven > Backed > Asserted > Gap. With --fail-on-drop the exit code is 1 when a
drop exists, so CI or a hook can stop on it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402

RANK = {"Formal": 0, "Proven": 1, "Backed": 2, "Asserted": 3, "Gap": 4, None: 5}


def index(items: list[dict]) -> dict[str, dict]:
    return {i["id"]: i for i in items}


def main(argv: list[str]) -> int:
    paths = [a for a in argv if not a.startswith("--")]
    if len(paths) != 2:
        tm.fail(__doc__.strip())
    old, new = tm.load(paths[0]), tm.load(paths[1])
    for path, data in zip(paths, (old, new)):
        errors = tm.validate(data, promises=False)
        if errors:
            tm.fail(f"{path} is invalid:\n" + "\n".join(errors), 1)
    lines = [f"# Trust-map diff: {new['repo']} #{new.get('pr')}", ""]
    lines.append(f"- Head: `{old['head'][:10]}` to `{new['head'][:10]}`.")
    oc, nc = index(old["claims"]), index(new["claims"])
    drops = 0
    for cid in sorted(nc.keys() - oc.keys()):
        lines.append(f"- New claim {cid}: {nc[cid].get('verdict')}. {nc[cid]['text']}")
    for cid in sorted(oc.keys() - nc.keys()):
        lines.append(f"- Claim {cid} is not in the new map. {oc[cid]['text']}")
    for cid in sorted(oc.keys() & nc.keys()):
        a, b = oc[cid].get("verdict"), nc[cid].get("verdict")
        if a != b:
            drop = RANK[b] > RANK[a]
            drops += drop
            lines.append(f"- {'DROP' if drop else 'Rise'} {cid}: {a} to {b}. {nc[cid].get('reason', '')}")
    ov, nv = index(old["verifiers"]), index(new["verifiers"])
    for vid in sorted(ov.keys() & nv.keys()):
        a, b = ov[vid].get("state"), nv[vid].get("state")
        if a != b:
            lines.append(f"- Verifier {vid}: {a} to {b}.")
    for vid in sorted(nv.keys() - ov.keys()):
        lines.append(f"- New verifier {vid}: {nv[vid].get('state')}.")
    ok, nk = index(old["controls"]), index(new["controls"])
    for kid in sorted(ok.keys() & nk.keys()):
        a = (ok[kid].get("result") or {}).get("status")
        b = (nk[kid].get("result") or {}).get("status")
        if a != b:
            lines.append(f"- Control {kid}: {a} to {b}.")
    if len(lines) == 3:
        lines.append("- No verdict, state or control result changed.")
    lines += ["", "Summary: " + ", ".join(f"{k} {old.get('summary', {}).get(k, 0)} to {v}"
                                         for k, v in new.get("summary", {}).items())]
    print("\n".join(lines))
    return 1 if drops and "--fail-on-drop" in argv else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
