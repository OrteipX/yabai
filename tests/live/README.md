# Opt-in macOS 27 replay

`make -C tests` runs only automated tests and mocked scenarios. It never runs
this directory's live suite. No launchd, TCC, SIP or installed binary changes
have been executed while preparing this replay harness.

The original 46-assertion session predated the critical review. Its sanitized
results are in `doc/macos27-live-results.json`; they are historical evidence,
not a live pass for the revised source. `session.py` and `suite.py` preserve
that procedure with an explicit opt-in, stronger preconditions, private local
logs, build provenance and rollback checks. They have been syntax checked and
the disposable Cocoa program compiled, but the revised runner has not itself
been run through a daemon handoff. Approval for another live session is needed.

## Fixture

This deliberately targets the tested desktop arrangement, not arbitrary Macs:

- macOS 27.0.1 / 26A434 is the only live-tested build. SIP must be fully enabled.
- Exactly one yabai is running, under `com.asmvik.yabai`, with its existing
  Homebrew plist and `/opt/homebrew/bin/yabai` executable.
- Display arrangement index 1 is the right monitor, with 12 Spaces; index 2 is
  west of it, with 10 Spaces. Do not confuse arrangement indices with display IDs.
- Mission Control indices 4, 12, 13, 14, 20 and 22 are empty, non-fullscreen
  Spaces. The suite refuses to proceed if any contains a window.
- Start on a Space with a next neighbor on the same monitor. Leave the mouse
  and keyboard alone during the run, since real user input can invalidate the
  observations. Cancel with Ctrl-C if necessary.
- Commit changes first, then build from that clean checkout. Logs capture HEAD,
  source status and local binary SHA-256. Keep other GUI apps open.

If the arrangement no longer matches, do not create/delete/reorder Spaces just
to make the test pass. Adapt and review the fixture first. The explicit lists
are there to avoid silently choosing occupied working Spaces.

## Commands (only after approval for a live session)

```sh
make
make -C tests
python3 tests/live/session.py --run
```

Without `--run`, the runner prints usage and performs no service changes. It
compiles `windows.m` into a private temporary directory and launches three
owned, disposable Cocoa windows. A minimal temporary config uses float layout
globally, then enables BSP only on the empty test Spaces. It does not source
user scripts, load the scripting addition, or modify `~/.yabairc`.

Before stopping Homebrew it captures display/Space/window frames and state,
service identity, checksums, SIP, cursor and build provenance. It boots out
only the original service and verifies its PID exited before spawning the
local foreground daemon. It never overwrites the Homebrew binary or plist.
Accessibility failure aborts the run and restores Homebrew; the runner never
grants permissions, resets TCC, installs a certificate or touches sudoers.

The 46 assertions cover switching with actual Space/display checks; empty,
already-visible and multi-hop destinations; window discovery/BSP geometry;
focus; numeric and directional warp/swap; rotate/mirror; resize/balance;
numeric and next/previous window Space moves; the complete skhd west/east
move-and-focus sequences; and four negative client-status checks. Mirror tests
allow a geometrically correct no-op. These are command compatibility tests,
not physical key delivery tests.

## Rollback and evidence

The suite terminates only its owned disposable application, returns to the
saved visible Spaces/focused window, then the outer `finally` block terminates
only the owned daemon and bootstraps the unchanged original plist. It verifies
window IDs/frames/membership, visible/focused Spaces, binary/plist integrity and
service response. If restoration differs, the run fails and saves before/after
snapshots rather than claiming a clean desktop. Fractional cursor coordinates
may be rounded by `CGWarpMouseCursorPosition`.

The printed `/tmp/yabai-live-*` directory is mode 0700. Its JSON snapshots and
logs contain local application data: keep them local and never add them to Git.
Review the complete daemon log for warnings as well as assertion results. If
interrupts, a process crash or snapshot errors occur, inspect the saved records.
Python `finally` cannot handle SIGKILL, power loss or a killed host terminal.
Manual fallback, after confirming the temporary PID belongs to this runner:

```sh
kill -TERM <temporary-daemon-pid>
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.asmvik.yabai.plist"
launchctl print "gui/$(id -u)/com.asmvik.yabai"
/opt/homebrew/bin/yabai -m query --spaces
csrutil status
shasum -a 256 /opt/homebrew/bin/yabai
```

If `bootstrap` reports the service is already loaded, inspect `launchctl print`
and the running executable before using `launchctl kickstart` on that label.
Never use `killall yabai`. If the desktop still differs, use the saved snapshot
and restore individual window/Space state deliberately; do not close real apps.
