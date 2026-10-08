# D1 alignment with the Jev session's J1 (received 2026-10-08)

The Jev session's job J1 (branch `feat/jev-vps`) fixes these strings. The P1-D1 Decider must use them unchanged,
so that the Decider's log and cache keys match the VPS service.

- **qtype:** a lowercase dotted string `<area>.<question>`.
  - Inventory: `inv.building` (Choice), `inv.type` (Choice), `inv.floor` (a 16-option Choice keyed "0".."15"),
    `inv.duplicate` (Noul).
  - Materials: `mat.category` (Choice), `mat.trim` (Noul).
  - Reserved: `repair.next_step`, `review.priority`, `e5.winner`, `e4.same_look`, `e8.opening_kind` (spec §9 names).
- **subject:** a plain string.
  - `inv.*`: the group name exactly as `source.json`'s `group`.
  - `mat.*`: the material name exactly as the key in `materials.json` `materials`.
  - `repair.next_step` and `review.priority`: the campus-map unit id.
  - e4, e5 and e8: `<unit>:<site-id>`, the site id defined by P2.
- **Cache key** (`wire.question_key`), corrected after J1's review: the sha256 hex of canonical JSON
  (`sort_keys=True`, separators `,` `:`) of `{"state", "kind", "instructions", "criteria"}`.
  - kind is noul, choice or score.
  - criteria keeps the question's ORDER:
    - Choice: a list of `[label, description]` pairs in the question's order;
    - Score: the list of level texts in order;
    - Noul: null.
  - Sorting a dict of options would merge two questions whose options come in a different order, and Jev sees them
    as different questions.
  - state is key-sorted.
  - qtype and subject are NOT in the key.
- **Probabilities** on the wire are JSON objects with string keys; consumers normalise them.
- **Owner lookup:** by (qtype, subject). The owner's latest confirmed answer for that pair beats everything else.
- **Answers:** kept in raw option form ("MAIN INFRASTRUCTURE", floor "5"). The D1 log keeps the raw option too.
- **Fields:** J1 adds `qtype: str = ""` and `subject: str = ""` to NoulQ, ChoiceQ and ScoreQ in
  `engine/decide/jev.py`. They exist on `feat-dashboard` only after `feat/jev-vps` merges.
  - D1 must not edit `jev.py` (ruling D1-R1).
  - D1 defines its own question-type registry with these qtype and subject conventions, and imports nothing that
    exists only on `feat/jev-vps`.
