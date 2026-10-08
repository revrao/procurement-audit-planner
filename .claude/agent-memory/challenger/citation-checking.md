---
name: citation-checking
description: How to verify challenge citations resolve before sending (pack paths, metric paths, trace check)
metadata:
  type: reference
---

- `$.pack.…` citations resolve against pack-figures.json with the root renamed `pack`: e.g. `$.pack.tests.T-07.after_filter`, `$.pack.pbc[0].tests` (PBC list is an array, so index it).
- Resolve paths with `br.resolve` from `scripts/checks/_qa.py` (load it via importlib, as check_trace.py does) instead of guessing jq paths.
- Quick end-to-end check: `.venv/bin/python scripts/checks/check_trace.py | grep -i challenge`; only "status is open" failures are expected mid-round.
- Per-test sample counts (population_items, after_filter, target_size, sampled_transactions) are under `.tests` in pack-figures.json; PBC-to-test links under `.pbc`.
- risk-register.md starts with a large `register-meta` JSON comment; read the body with `awk '/^-->/{f=1;next} f'`.
