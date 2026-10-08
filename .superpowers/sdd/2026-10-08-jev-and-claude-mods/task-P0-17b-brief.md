# P0-17b — Jev floor question: Choice, not a 16-level Score (follow-up to P0-17)

**Base:** `feat/repair-p0` at b1c66a2 (P0-17 merged). Branch `claude/P0-17b`, worktree `.claude/worktrees/P0-17b`.

**Root cause (measured 2026-10-08 with the real API):** the first real pilot sent 17 group-name batches and every
one failed with HTTP 400. The materials batches all passed. Sending one group's four questions one at a time:
building (Choice) OK, type (Choice) OK, duplicate (Noul) OK, floor (Score with 16 levels: "no floor / ground
level", "floor 1" … "floor 15") FAILED:
`400 Too many score levels. Must have at most 10 levels.` (body `{'detail': 'Too many score levels. Must have at most 10 levels.'}`).

**Items, test first, commit after each:**
1. `classify_group_names`: ask the floor as a **Choice**, not a Score. Use the same 16 options keyed so the answer
   maps back to an int: `"0"` → "no floor / ground level", `"1"`…`"15"` → "floor N", each with a short description.
   The returned `floor` Decision's `answer` becomes that int (0-15), and `probabilities` are keyed by int too, so
   `engine/decide/pilot.py` floor accuracy keeps working unchanged. Adjust it only if a test shows it must change,
   and say why.
2. `_SdkAdapter` / `ScoreQ`: a Score with more than 10 levels must fail **before** any network call, with a
   clear `ValueError` naming the limit. A Choice with more than 255 options likewise. Put both limits as named
   constants with a comment citing the API message.
3. Tests: the floor question is a ChoiceQ with 16 options; the mapping from the answer to an int, from probabilities
   to int keys, and the pilot's floor accuracy on a canned response; the adapter's Score>10 and Choice>255
   checks fire before the client is called (the fake client records no call).
4. Run the covering tests (`engine/tests/test_decide_jev.py`, `engine/tests/test_decide_pilot.py`), then the full
   engine suite once.

**Constraints:** AGENTS.md binding rules. Never open the real `.env`. No network in tests. Don't run the real pilot;
the controller does. Don't touch engine/guard/**, FixProfile or unrelated tests. Stage files by name. Never a bare cd.
