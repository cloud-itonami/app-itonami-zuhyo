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

A follow-up carries Kotoba-generated input names via the `BV2|` view protocol;
Chrome checked the heading and notes names and repeated the UI and fault tests.
Native/Wasm model and reorder mutation checks passed. This does not establish
full accessibility. The earlier intermittent first-tab refusal was reproduced
with a diagnostic build as the adapter's 30-second Worker timeout; the reason
for the Worker delay remains unproven. The adapter now distinguishes timeout
and cross-tab conflict for the user, and an artificially shortened timeout test
confirmed the prior saved deck remains. Follow-up browser Wasm SHA-256:
`5b9f1cfc3f6d0ca37dd5af90aec201a81fe4d91af5925ed802bb09db8b7ec062`.

A local instrumented copy recorded one slow step with Worker-start message at
3.555 s, Wasm-start message at 4.581 s and completion message at 16.938 s.
These are main-thread notification times, include scheduling, and do not prove
the cause of the earlier 30-second timeout. The adapter now compiles Wasm once
after its digest check and sends the immutable `WebAssembly.Module` to each
fresh Worker instead of sending bytes for repeated compilation. Chrome reran
the UI, interrupted-save and negative digest tests successfully. This change
is not evidence that the timeout is fixed or that other browsers are qualified.

A small instrumented comparison alternated two runs of the prior bytes-per-
Worker build and two runs of the precompiled-module build, each with eight
synthetic heading saves in a fresh Chrome profile on the shared Mac. The
harness verified identical Wasm and Worker bytes. All 32 saves completed.
Step completion-notification medians were 11/10 ms (bytes) and 7/7 ms
(module); view medians were 34/33 ms and 28/28 ms. No timeout occurred. These
main-thread notification timings include instrumentation and scheduling. The
sample is too small to establish speedup, root cause, or timeout resolution.
Reproduce with `scripts/measure-worker-latency.py AMU_DIR OLD_BUILD NEW_BUILD
NEW_OUTPUT CHROME`; the two builds must have the same Wasm and Worker bytes.
The old build must be produced from the prior bytes-per-Worker revision.
