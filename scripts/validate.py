#!/usr/bin/env python3
"""Validate a trust map against schema/trust-map.schema.json and the cross-reference rules.
The claim, plain-text, name and promise texts must also be strict STE (asd-ste100, scripts/ste.py).

    python3 scripts/validate.py runs/<repo>/<pr>/trust-map.json

Exit 0 when valid, 1 when invalid, 2 on a bad invocation.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tm  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        tm.fail(__doc__.strip())
    data = tm.load(argv[0])
    errors = tm.validate(data)
    if not errors:
        import ste
        try:
            errors = ste.map_problems(data)
        except ste.SteMissing as exc:
            errors = [str(exc)]
    for error in errors:
        print(f"{argv[0]}: {error}")
    if errors:
        print(f"INVALID: {len(errors)} errors")
        return 1
    print(f"VALID: {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
