# Final fix round — Errors page (branch feat/errors-page, worktree .claude/worktrees/errors-page, HEAD b7f843d)

Source: the final whole-branch review. The page is already live for the owner, who is about to type
notes into it, so items 1 and 2 must be right.

Work test-first where a unit test is possible. Make one commit per group (A, B, C, D), staging files by
name. Gates, run in the foreground at the end:
- `api/tests/test_docs.py api/tests/test_health.py` and `tools/tests` (pytest with `PYTHONPATH` = the
  worktree);
- `pnpm --dir web exec vitest run`;
- `pnpm --dir web exec vue-tsc -b`: only the 3 known `Viewport.ts` errors, 332/333/360;
- `pnpm --dir web run build`.

## A. The floating window and the owner's notes (web)

1. **✕ does not close the window in Chrome or Edge.**
   - Cause (`web/src/components/ErrorWindow.vue`, around lines 3, 6 and 181-186): `startDrag` takes
     pointer capture on the title bar for every press, including a press on ✕, so the click goes to the
     title bar.
   - Fix: first line of `startDrag`:
     `if (ev.button !== 0 || (ev.target as Element).closest('button')) return`.
2. **Notes can be lost.** The textarea shows the last *saved* note (`:value="noteFor(m)"`), and Vue
   resets it on every render. So:
   - a failed save wipes the typed text;
   - typing a note and then clicking a verdict sends two PUTs, and the second carries `note: ""`, so the
     last write loses the note;
   - verdicts that failed to load look empty, so a click overwrites a saved note on the server.

   Fix, all of these:
   - **a. A draft per model in the window.** `const drafts = reactive<Record<string, string>>({})`.
     - The textarea gets `:value="drafts[m] ?? noteFor(m)"`,
       `@input="drafts[m] = ($event.target as HTMLTextAreaElement).value"` and `maxlength="2000"`.
     - Blur emits `verdict` with the current verdict (`'unsure'` when none) and `note: drafts[m]`, only
       when the draft differs from the saved note.
     - A verdict click emits `{ verdict: <new or null>, note: drafts[m] ?? noteFor(m) }`, so the note
       travels with the click.
     - Drafts live as long as the window.
   - **b. Saves in order, in `web/src/views/ErrorsView.vue` `saveVerdict`.** Chain the saves per
     `kind/model` key with a `Map<string, Promise<void>>`: a save for a key waits for the previous save
     for that key before sending.
   - **c. Verdicts that did not load.** Keep a flag when `GET /api/docs/validation` failed, and pass a
     new boolean prop `verdictsReady` to `ErrorWindow`.
     - When false, the verdict buttons and textareas are disabled.
     - The verdict part then shows: "Verdicts could not be loaded — reload the page before giving
       verdicts."
   - **d. A failed save for a window that is no longer open** (closed, or another kind open) shows a
     dismissible page-level banner: `Not saved: <kind title> — <model id>: <message>`.
   - **e. Error text.** For a 422, show `detail[0].msg`; for a string `detail`, show it; otherwise show
     `HTTP <status>`. Never show raw JSON.
3. Commit A: `fix(web): Errors window -- ✕ closes it; notes are drafts that survive a failed save and travel with the verdict click`.

## B. The verdict API keeps a note it was not sent (api)

4. In `api/routers/docs.py`, `VerdictIn.note` becomes
   `note: str | None = Field(default=None, max_length=2000)`.
   - In `put_verdict`, when `note is None` and a verdict is set, keep the stored note of that
     kind/model (`""` when there is none).
   - Append a test to `api/tests/test_docs.py`: PUT `{"verdict": "ok", "note": "keep"}`, then PUT
     `{"verdict": "error"}`. The GET shows verdict `error` and note `keep`.
   - Keep all existing tests passing.
   - Update the module docstring of `docs.py` and of `test_docs.py`: they still describe only the image
     route.
5. Commit B: `fix(api): a verdict without a note keeps the saved note`.

## C. The content file is checked where the page relies on it (web)

6. `validateCatalogue` in `web/src/utils/errorsDoc.ts` gains these checks. Keep the existing messages
   and their order.
   - **For each kind:** `title` empty after trim gives `id: "title" is empty`, checked *before*
     `summary`. After the list checks, a `sources` with no non-empty item gives
     `id: "sources" is empty`.
   - **For each engine mistake:** `title` empty gives `id: "title" is empty`, before `what_happened`.
   - **Ids the verdict API accepts:** a kind id must match `/^[a-z0-9][a-z0-9-]{0,63}$/`, else
     `id: id does not fit the verdict API`, checked right after the duplicate check.
   - **For each model**, first, before the kinds:
     - an id not matching `/^[A-Za-z0-9][A-Za-z0-9_-]{0,31}$/` gives
       `model <id>: id does not fit the verdict API`;
     - a `numbers` value that is neither a number nor an array of exactly two numbers gives
       `model <id>: bad number "<key>"`.
   - Add a NEW test with a catalogue that triggers each new message, and assert the exact list.
   - The existing tests must pass unchanged: its catalogues trigger none of the new messages.
7. In `ErrorsView.vue`'s load of `/docs/errors.json`:
   - when the response is not JSON (the `content-type` does not contain `json`), show "The
     documentation file is missing from this build (/docs/errors.json)";
   - after parsing, run `validateCatalogue`. When it returns problems, show "The documentation file has
     N problems:" with the list, and do not render the catalogue.
8. Commit C: `fix(web): the page refuses a missing or invalid errors.json with a readable message`.

## D. Small things (web, tools)

9. **Image placeholder.** On `@error` of every doc image, in the page, the window and the strip, show a
   grey box in its place: "Screenshot not found on this machine (data/errors_doc/img/<name>)".
10. **`tools/errors_doc/check.py`.** When `owner_images.json` or the errors.json is missing, print a
    one-line message naming the missing file and the command that makes it
    (`python -m tools.errors_doc.extract_owner_images <log> --out data/errors_doc`), and exit 2 with no
    traceback. Add a test to `tools/tests/test_errors_doc.py`.
11. **Engine mistakes section.** Its heading shows the filtered count. When the filter leaves none, show
    "No engine mistake for this filter." instead of an empty grid.
12. **"saved <time>".** Show the local time (`new Date(at).toLocaleString()`) and keep the raw UTC in the
    element's `title`.
13. Commit D: `fix(web,tools): placeholders for missing screenshots, clear check.py messages, empty-filter text, local times`.

## Report

Append a "Final fix round" section to `task-10-report.md`: what changed per item, the gate results with
their summary lines, and the four SHAs.
