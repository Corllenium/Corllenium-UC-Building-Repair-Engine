## Global Constraints

- **Branch and worktree.** Branch `feat/layer-info`, worktree `.claude/worktrees/layer-info`, from
  feat-dashboard. There is no API or database change.
- **Layer → catalogue kind:**

  | Layer | Kind id |
  |---|---|
  | `grid` (Gridlines) | `gridlines` |
  | `tri` (Triangles) | `gridlines` |
  | `hidden` (Removed Faces) | `hidden-faces` |
  | `xray` (X-Ray) | `hidden-faces` |
  | `onesided` (One-Sided / Flipped) | `reversed-faces` |

  Outlines, Creases and Sync get no (i): they are not errors.
- **Workspace model → catalogue model:** the catalogue model whose `name` equals the workspace model's
  `name` (`chtm_5ft_floor` → `CHTM5`, etc.). When nothing matches, the window shows every model's rows.
- **The (i) button** must not toggle its layer's checkbox. It sits inside the checkbox's `<label>`, so it
  needs `type="button"` and `@click.stop.prevent`.
- **Gates** (foreground, from the worktree root):
  - `pnpm --dir web install --frozen-lockfile` once;
  - `pnpm --dir web exec vitest run`, all pass;
  - `pnpm --dir web exec vue-tsc -b`: only the 3 known errors in `web/src/three/Viewport.ts`
    (332/333/360, still present on feat-dashboard);
  - `pnpm --dir web run build`.
- **Commits:** stage by name; the implementer's own model goes in the Co-Authored-By line.

