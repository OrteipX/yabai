# macOS 27 compatibility with SIP enabled

## Scope and status

Work is on `fix-macos27`, based on upstream `dd84572`. Neither `master` nor
`macos-27-sip` has been modified. The Homebrew executable and launchd plist
are unchanged. No scripting addition is installed or loaded by this work.

Target: macOS 27.0.1 / 26A434, Apple M5 Pro, FEAT_PAuth_LR=0. SIP was checked
with `csrutil status` and is enabled. The build is ordinary arm64 + x86_64;
it does not use an arm64e Dock payload to implement Space switching.

**Verification is split by build.** The pre-review implementation passed
46/46 live assertions on 2026-11-10. The critical review then found and fixed
additional edge cases; the revised source passes automated and sanitizer tests
but has not undergone another live daemon handoff. Do not treat the historical
46/46 as a live pass for the final commit. The original Homebrew service remains
in place. Results are retained in `doc/macos27-live-results.json`.

## Evidence and applicability

- [yabai #2822](https://github.com/asmvik/yabai/issues/2822): upstream distinguishes
  the broken SIP-enabled path from scripting-addition offset fixes.
- [yabai #2842](https://github.com/asmvik/yabai/issues/2842) and
  [#2844](https://github.com/asmvik/yabai/issues/2844): reports for 27.0.1;
  the latter's scripting-addition loading procedure is outside this work's scope.
- [InstantSpaceSwitcher #88](https://github.com/jurplel/InstantSpaceSwitcher/pull/88):
  10 ms pacing between began/changed/ended phases. The PR also pumps the CLI
  runloop, which is not needed for yabai's persistent application runloop.
- The advertised `macos-27` branch is no longer present in `git ls-remote`.
  `refs/pull/88/head` was verified and fetched, resolving to
  `c64e0fd09857330422084387cb98e8d1f4c3e2d1`. Its diff adds pacing; it
  depends on serialization code already in its parent. It cannot be applied
  alone to yabai.
- The actual serializer and modern swipe fields were inspected at
  [InstantSpaceSwitcher 2b883a9](https://github.com/jurplel/InstantSpaceSwitcher/tree/2b883a9).
  This includes subsequent changes for natural scrolling, companion events,
  and signed minimal progress. The serializer is adapted under its MIT license,
  retained in `doc/InstantSpaceSwitcher-LICENSE`.
- Local `macos-27-sip` was compared without merging or cherry-picking. Its
  non-payload version gates inform the macOS 27 notification/window handling
  changes. Its Dock signatures, loader and installation scripts are not needed
  for this SIP-enabled fix.

## Changes

macOS 27 swipe events carry a packed IOHID payload in serialized field 4205.
Each began/changed/ended phase has a companion gesture event. Phases are spaced
10 ms apart; only the ended phase carries fling velocity. Direction accounts
for the natural scrolling preference. All phase allocations finish before
posting begins. Serialization rejects unknown CGEvent format versions.

Switching uses the target display's ordered Space IDs. Each hop confirms the
WindowServer current Space, with at most one second of polling and a shared
two-second monotonic budget for the entire switch. Route order, source Space
and cursor display are rechecked before every hop. External gestures or Space
reordering cause failure rather than a stale-direction retry. The upstream
animation query is stubbed on modern macOS, including 27, so these checks do
**not** establish animation completion.
Final display activation is checked through the active menu-bar display.
It does not depend on the event loop consuming queued `space_changed` events.
`space --focus` propagates gesture failure to the client with a nonzero exit
status. Pre-27 gesture construction and asynchronous completion behavior are
preserved; there is no new pre-27 confirmation guarantee.

macOS 27 now uses the existing modern notification subscriptions, Mission
Control observation, window-level query, and Tahoe window-sublevel message ID.
The sublevel message ID is inherited from the experimental branch. Live
window discovery, focusing and tiling succeeded with it on this build;
other macOS 27 builds and unusual window levels remain unverified.

Window moves check the bridged class and initializer as well as the private
function; nil initialization falls through to the existing fallback. Only
macOS 27's send-window path waits for actual target membership before changing
its tiling tree. `window --space` and `window --display` report failed
confirmation. Low-level single/bulk moves, cross-Space warp/swap and scratchpad
paths retain upstream asynchronous behavior. Older OS command paths also keep
the upstream order and do not gain a new completion guarantee.

## Completed checks

- `make`: universal arm64/x86_64 build succeeds.
- `make -C tests`: eight tests pass (existing geometry, payload/round-trip,
  malformed-format/numeric inputs, invalid targets, >1,024 notification IDs,
  sublevel reply/timeout, and window-move confirmation/timeout). Fourteen
  additional transition scenarios use the actual production state machine
  with a mocked WindowServer and clock. No events are posted.
- `make -C tests asan`: the same suite passes with address, undefined-behavior
  and float-cast-overflow sanitizers; no sanitizer faults reported. This is
  not a proof of private-framework ownership or all concurrent interactions.
- The test build retains five existing CoreVideo deprecation warnings.
- `make -C tests diagnostics`: read-only probe reports the bridged move
  function, initializer, and connection-port symbol present on 27.0.1.
  Run outside a sandbox if reading the effective user scrolling preference is
  important; sandbox preference access can report the default.
- `git diff --check`: passes. Final review also verified the original Homebrew
  service still runs/responds, its checksum is unchanged, and SIP is enabled.
- `bin/yabai --version`: `yabai-v7.1.25` (upstream version is unchanged).
- Running Homebrew daemon and skhd confirmed through process/launchd queries.
  Two displays are available, with 12 and 10 Spaces respectively.
- Existing skhd commands were inspected. Numeric/prev/next Space selectors,
  directional window focus, warp/swap, resize, grid, zoom, mirror, rotation,
  balance and display commands keep their existing syntax. These command
  paths were exercised live against the replacement daemon; physical keyboard
  delivery through skhd was not synthesized.

Homebrew binary SHA-256 before replacement testing:
`372ad557a7c54a6199a78dcbcefe5b60fd0224e5c1f5139cfaed00dfdaa44501`.

## Approved-session procedure

The session captured display, Space, window, cursor, process, service, SIP,
Homebrew binary and launchd plist state before stopping the service. The
following procedure describes the authorized handoff and rollback:

1. Boot out only `gui/$(id -u)/com.asmvik.yabai` with `launchctl bootout`, and
   verify the original PID exited before starting the replacement. Direct
   bootout avoids the enable/disable state changes in `--stop-service`.
2. Run the local `bin/yabai --verbose` as a temporary foreground daemon with
   logs captured. The actual session used a temporary copy of `~/.yabairc`
   with the initial layout changed to float, then enabled BSP only on empty
   test Spaces 4 and 20. This avoided deliberately retiling working windows.
   The user configuration file was unchanged. Clients in that config and
   skhd still connect to the same socket. Do not install this executable
   or rewrite the launchd plist. If Accessibility authorization blocks startup,
   record it and roll back; do not change permissions or security settings.
3. Verify adjacent and multi-hop switching in both directions, first on the
   active display and then across displays, including a destination already
   visible on an inactive display and an empty Space. Check queried Space ID,
   active display, command status and timeout logs after each command.
4. Move a disposable window to another Space and back, then across displays
   and back. Check actual membership and source/destination tiling trees.
5. Exercise focus and tiling with disposable windows, then the exact commands
   used by skhd. Verify actual frame/focus changes, not merely exit status.
6. Exercise invalid selectors, same-Space focus, missing windows and restricted
   Space operations. Verify nonzero statuses and useful errors. Do not invoke
   scripting-addition install/load commands. Mission Control/animation and
   natural-scrolling-off scenarios remain separate checks if unavailable.
7. Restore test windows, the original visible Spaces and cursor. Stop the
   temporary daemon, restore Homebrew service, and recheck SIP and checksum.

Rollback at any point:

```sh
# Stop only the recorded temporary daemon PID, if it is still running.
kill -TERM <test-daemon-pid>
/opt/homebrew/bin/yabai --start-service
launchctl print gui/$(id -u)/com.asmvik.yabai
/opt/homebrew/bin/yabai -m query --spaces
```

There is no binary to copy back: `/opt/homebrew/bin/yabai` is never replaced.
Do not stop the replacement with an unqualified `killall yabai`.

## Live results

Raw snapshots, command results and daemon/disposable-app logs are retained
locally outside the repository. They include window titles and are intentionally
not copied into Git. The original test source was uncommitted and its patched
binary checksum was not recorded, so the historical result cannot identify an
exact independently rebuildable artifact. The new replay records both HEAD
and the local binary checksum and requires a clean source checkout.
The sanitized, reviewable assertion list is `doc/macos27-live-results.json`.

| Check | Result | Actual verification |
| --- | --- | --- |
| Homebrew handoff and local startup | PASS | Original PID exited; local PID/executable verified and socket responded; no Accessibility block |
| Next/previous Space | PASS | Destination Space ID/index and focused display checked on both monitors across the runs |
| Numeric, multi-hop and empty Space switching | PASS | Included 1→12 and 13→22; each final target/display confirmed |
| Cross-display and already-visible Space focus | PASS | Correct monitor focused; other monitor's visible Space unchanged after each switch |
| Window discovery and BSP layout | PASS | Three disposable native Cocoa windows tracked; split metadata and actual tiled frames checked |
| Window focus | PASS | Numeric and directional focus checked; focusing a window on another Space activated its Space |
| Swap and warp | PASS | Numeric and skhd-style directional selectors changed actual placement/BSP geometry |
| Rotate and mirror | PASS | 270-degree rotation and both mirror axes checked against actual geometry |
| Resize and balance | PASS | Resize changed frames; balance restored altered split ratios |
| Move window between Spaces | PASS | Numeric and next/previous selectors; actual membership checked; returned window tiled |
| Move window between displays | PASS | west/east move-and-focus sequences; destination Space/display and tiling state checked |
| Invalid Space/window/selector and same-Space focus | PASS | All four returned status 1 with specific errors |
| Crashes and gesture/move timeouts | PASS | None observed in the final suite; daemon terminated only by the test harness |
| Desktop restoration | PASS | All 17 existing windows retained exact frames, Space/display membership, floating/minimized state; visible/focused Spaces restored; cursor restored within one point of the final session baseline |
| Homebrew, SIP and file integrity | PASS | Original binary running/responding; checksum and plist unchanged; SIP enabled |

The pre-review final run contains **46 passing assertions, zero failed
assertions**; all 46 recorded results have been reviewed. Its final read-only
verification found exactly one yabai process, `/opt/homebrew/bin/yabai`, with a
successful Space query.
The original skhd process was also running.
Ordinary commands were sent using the unchanged Homebrew client to the patched
daemon, verifying the existing message protocol as well as command syntax.

Two earlier runs stopped on incorrect test expectations, with Homebrew restored
after each. First, mirroring a tree with no splits on that axis can legitimately
leave its geometry unchanged. The corrected test checks the reflected geometry
rather than demanding movement. Second, the test initially omitted the
`display --focus west` half of the user's skhd move/focus binding. The return
`--display east` correctly returned status 1 because the active display was
still the rightmost monitor. The full configured sequence passed in both
directions. Neither finding required a production source change.

The startup-only check took its first post-restore frame snapshot before the
Homebrew configuration had settled: three windows temporarily showed zero-gap
frames. Subsequent settled captures and all integration-run comparisons showed
no existing-window frame differences. Each integration session restored its
own baseline, including user state changes between sessions. Cursor warping
rounded the saved fractional position to integer coordinates (delta −0.145,
−0.348 points); the cursor was restored within one point, not bit-for-bit.

The daemon logged an existing-app discovery warning for Microsoft Azure
Storage Explorer (not all application windows resolved). Saved snapshots show
one tracked window for that application under both Homebrew and the patched
daemon; the total set remained at 17. The warning/recovery routine is unchanged
from upstream. This does not establish a reproducible regression or prove that
all windows were tracked. No suppression or speculative fix was added; a fresh
application/window lifecycle comparison is still needed if the symptom recurs.
No unexpected Space/window movement remained in the final state comparisons.

Physical hotkey delivery, forced gesture-delivery failure/timeouts, natural
scrolling off, native fullscreen, sleep/wake and display disconnects were not
covered. Invalid-selector errors do not prove recovery from a WindowServer
failure. No scripting addition, TCC update, SIP change, sudoers update, binary
replacement or launchd plist edit was performed. No merge or push occurred.

## Critical review and reproducibility

Confirmed problems corrected after the live session:

- Direction was derived from an earlier snapshot than the actual hop route.
  Use one ordered route and abort on source/route/cursor changes between hops.
- A wait called an active-display helper that asserts on a missing menu-bar
  display UUID. Read/release the nullable UUID directly instead.
- Per-hop iteration limits allowed many seconds of accumulated polling. Use
  monotonic per-hop deadlines and one two-second budget across all hops.
  Private IPC/Accessibility calls can still exceed a polling budget.
- Synchronous window confirmation had spread to internal warp/swap/scratchpad
  callers that ignored the new boolean result. Restore asynchronous low-level
  APIs and confine confirmation to the macOS 27 send-window command path.
- The notification array could overflow with more than 1,024 tracked windows.
  Allocate for the actual table sizes; retain prior subscriptions on allocation
  failure. Automated coverage exercises 1,100 IDs and an empty table.
- The macOS 27 private sublevel MIG request had no send/receive timeout. Bound
  each phase to 250 ms, validate the reply and return a neutral sublevel with
  diagnostics on failure. This does not verify every future MIG layout.
- Harden the serializer's numeric conversion and allocation-size bounds. Its
  borrowed CFData input is released only by the owning wrapper; event objects
  are released on successful and failed phase construction. Tests cover
  allocation/augmentation failure before posting, owned-event balance and
  unknown/truncated serialization formats. No IOKit kernel object is created;
  the IOHID payload is owned malloc memory copied into CFData/CGEvent objects.

The transition code is isolated in `src/space_transition.c` so tests compile
the production state machine with fake display state, clock and event posting.
The normal automated suite sends no keyboard/mouse gestures. Client commands
are serialized by yabai's event thread; real user gestures remain concurrent
and cannot be made atomic with private WindowServer state.

Replay instructions, fixture prerequisites, disposable-window source and the
opt-in rollback runner are in `tests/live/README.md`. The runner has been
syntax checked and its Cocoa fixture compiled, but not executed through a new
handoff in this review phase. A normal invocation without `--run` performs no
service changes. Logs are private and outside Git. `.DS_Store` and Python
bytecode are ignored; license attribution is retained. Only public source,
sanitized historical assertions and reusable test/procedure files are included.

Production installation and rollback are prepared separately in
`doc/macos27-deployment.md`; no stable-path installation, certificate/TCC update,
launchd modification, master merge or push has been executed. Fast-forward
instructions are in `doc/macos27-master-integration.md`.

## Remaining limitations

These private interfaces can change between macOS builds. One second is a
bounded confirmation period, not a cancellation guarantee: macOS may complete
an operation after a timeout. A failed multi-hop switch may stop on an
intermediate Space; it is reported as failure rather than silently retried.
The synchronous waits run on the command/event thread and delay queued events
(up to the polling budget plus time spent inside private/system calls).
If a timed-out move later completes, the source tree can remain stale until
normal Space/window revalidation. Cross-Space warp/swap and bulk operations
still have upstream failure/partial-completion limitations. Switching moves the cursor to the target display, consistent
with the upstream routing requirement. Natural scrolling off, native fullscreen,
Mission Control, rapid repeat commands, display disconnects, sleep/wake and
Intel runtime behavior still require verification. Bulk window operations and
all unrelated commands do not acquire a new success guarantee from this patch.

No merge or push has been performed. Consolidating into the fork's `master`
should follow live validation and review, with explicit merge/push approval.
