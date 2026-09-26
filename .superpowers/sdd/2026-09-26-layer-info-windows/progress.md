# SDD ledger — plan: docs/superpowers/plans/2026-09-26-layer-info-windows.md

Spec: docs/superpowers/specs/2026-09-26-errors-and-fixes-page-design.md (+ owner 14:40: (i) button per layer). Worktree .claude/worktrees/layer-info, branch feat/layer-info from 0637037.

## Rulings
- Ruling: Tasks 1 and 2 go to ONE implementer (sonnet) in two commits and ONE review — Task 2 builds directly on Task 1's composable and both touch the same page logic; the owner is waiting for it — costs a larger single review.
- Ruling: in the workspace a screenshot opens in a new tab (no lightbox component extracted) — keeps ErrorsView's lightbox untouched — costs a less polished image view there.

## Progress
- Tasks 1+2: dispatched (implementer sonnet, BASE 0637037)
- Tasks 1+2: implementer DONE 7d76cfa (useErrorsDoc) + 63ce3c5 ((i) buttons); vitest 68/68; vue-tsc 3 known; build OK. Concern: workspace save errors lack the 'Not saved: ' prefix. Review dispatched (sonnet).
- Pre-deploy browser check (dev server on 5191 from the worktree, live API): real clicks — Gridlines (i) opens 'Gridlines…' with only the chtm_5ft_floor row and one verdict row; X-Ray (i) → Hidden inside faces; One-Sided (i) → Reversed faces; ✕ and Esc close; no layer checkbox changed; the refactored Errors page saved {ok, typed note} on type-then-click and cleared on the second click; validation.json back to {}. Launch config restored.
- Tasks 1+2: review — Task 1 a faithful line-by-line refactor (composable state per call; chain, errorText, set/delete, routing strings preserved); Task 2 Needs fixes. Important: the workspace window never clears a "Not saved" after a later success; a save result can land in another kind's window after a switch (no kind guard, no banner). Minors: no in-flight guard on load(); workspace errors lack the "Not saved: " prefix.
- Ruling: fix all four (mirror ErrorsView's routing; banner fallback; same wording; reuse an in-flight load) — the owner relies on accurate save feedback — costs one fix round.
- Tasks 1+2: fix round 1/5 dispatched (resumed implementer, sonnet)
- Tasks 1+2: re-review — all 4 findings addressed (vitest 69/69; vue-tsc 3 known); complete (commits 0637037..7d76cfa..63ce3c5 + fix 4776e3d, review clean). Deployed web 14:50 from 4776e3d (validation.json backed up; web image tagged :pre-20260926-3; API unchanged).
