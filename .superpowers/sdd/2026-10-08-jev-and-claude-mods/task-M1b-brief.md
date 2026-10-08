# M1b — uc-guard: let the engine be handed the key file (follow-up to M1)

**Base:** feat-dashboard. Branch claude/M1b.

**Gap (measured 2026-10-08):** the owner's decision is that code reads the TypeSafe key at run time from the
git-ignored repo-root `.env`. `engine.cli decide-pilot --env-file <main>/.env` reads only the
`TYPESAFE_API_KEY=` line. uc-guard denied every such command, so the controller twice had to run the engine through
a scratchpad script the guard could not see.

**Change:** in a segment that runs `-m engine.cli`, the value of `--env-file` (`--env-file X` or `--env-file=X`)
is not treated as a secret read. Everything else stays denied:
- `cat .env`;
- any other option pointing at `.env`;
- another module given `--env-file`;
- a second segment that reads `.env`.

**Done when:** tests cover each case, validate and tsc pass, a review passes, and the README names the exemption.
