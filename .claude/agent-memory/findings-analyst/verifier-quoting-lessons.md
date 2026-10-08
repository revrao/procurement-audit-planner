---
name: verifier-quoting-lessons
description: How verify_history.py matches quotes/rows and the pitfalls hit (cross-page table cells, tall rows, minimal row_window)
metadata:
  type: feedback
---

How-to lessons for passing scripts/verify_history.py (no findings here).

- Quotes are matched after whitespace collapse and dash/quote normalisation (– to -, ’ to '), against plain OR layout text of the stated page(s). A wrapped cell that is contiguous in the plain text can be quoted whole; use layout fragments only where plain drops a hyphen ("£17.5k -" / "£175k").
- Row coherence (`incoherent_row`) uses the first 3/2/1 words of each cell to find layout lines; short cells like "5" or "High" match many lines, so the check is lenient. A row label printed several lines below/above its cells (e.g. a score digit on top of a two-line label) can push a row past the default 3.
- A table cell that continues onto the next PDF page lies more than 12 layout lines away (page footer and header sit in between), so a pdf_page_end row fails. Record the page-1 part in the row and the continuation as its own nested sourced item on the next page.
- "Smallest row_window" is required. Compute it by importing verify_history (sys.path.insert(0, "scripts")) and applying line_hits to each table_row item for windows 0..12, rather than guessing.
- Build history.json from a scratchpad Python builder script. Joined-fragment values then stay consistent with their quote lists automatically.

**Why:** the first run failed on exactly these two cases (a tall likelihood row; a Table 3 cell spanning pages).
**How to apply:** use this whenever you write or repair history.json items.
