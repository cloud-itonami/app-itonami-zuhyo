# Zuhyo browser candidate — 2026-11-02

This is a bounded local candidate, not a complete slide editor or a release.
One deck holds 1–16 slides; each slide has heading, body and speaker notes
(up to 512 UTF-8 bytes each), plus one of three shapes (none, rectangle,
circle). Kotoba state transitions add, remove, reorder, select, edit and
present slides. The presentation uses a simple CSS shape and is not an OOXML
or general-purpose layout engine. Theme editing and external import/export are
not implemented.

The `ZS1|` framed state validates complete input, field lengths, slide count,
selection, mode and shape before adopting it. The static browser candidate
uses a distinct localStorage key, Web Locks and a stored-value check for stale
cross-tab writes, the pinned shared broker and no declared external operations.
It does not infer or alter old-origin data.

On macOS ARM64 / Chrome 156.0.8078.74, native Amu and browser Wasm passed the
model test; a mutation that breaks the selected index on reorder was detected
on both. Loopback Chrome tests exercised edit, notes, add/remove, shape,
reorder, present, navigation, reload, oversized input, cross-tab conflict,
storage failure, corrupt state and mutated artifact digest. Observed main-page
requests were loopback only. One earlier extended test timed out waiting for a
first-tab save; a diagnostic rerun and the unchanged candidate rerun passed,
as did the final build. The cause was not determined and stability remains
open; the isolated retry is not proof the issue is fixed.

Compiler SHA-256:
`2c551579c06a0228029bb06bae177e93126ecbbc37d636d693c471dbac8d1536`.
Model source SHA-256:
`061b6ff0e82a73e73706ca03585ceca09a103236b75b11fca7eec8b9b70749b1`.
Browser Wasm SHA-256:
`8543e46dc1de03be05e2335f4cc70991b6a536659be43dfebc69db54e590bc86`.
The canonical broker was copied from `kotoba-lang/wasm-webcomponent` revision
`e00ae75e1c589f76b4f53a88a5e3256c98c9e162`, SHA-256
`7f760128c3a58098123c31ec3dd34b9c871932e3933f2c952facc4ab0e647212`.
The compiler is the unmerged candidate in kotoba-lang/amu#1779. The Wasm
digest is generated with the bundle and is not independent release attestation.

Reproduce with `scripts/check-deck-wasm.py AMU_DIR NEW_OUTPUT CHROME`, then
`scripts/build-browser.py AMU_DIR BROKER_REPO NEW_BUILD` and
`scripts/check-browser-ui.py AMU_DIR NEW_BUILD NEW_OUTPUT CHROME`.
Accessibility, other browsers, maximum-size performance, crash/interruption
recovery, old data migration, Itonami OS/QEMU, fleet, distribution and
production qualification remain open.
