# Production deployment and rollback (prepared, not executed)

The reviewed commit remains on `fix-macos27`. The 46 live assertions describe
an earlier build; review hardening has automated coverage and still needs an
approved live replay. Do not deploy or fast-forward `master` until that exact
commit/build has been reviewed and the remaining live validation accepted.
None of the commands in this document have been used to install the new daemon.

## Paths and identity

Use a real executable at `$HOME/.local/libexec/yabai-custom/yabai`, never a
build directory under `/tmp` and never `/opt/homebrew/bin/yabai`. Keep a dated
previous release in `$HOME/.local/libexec/yabai-custom/releases/`, including the
binary, commit/build checksum manifest, original `LICENSE.txt` and
`doc/InstantSpaceSwitcher-LICENSE`. The stable executable path stays constant
when versions change. Keep the Homebrew executable and plist untouched.

Use an existing persistent code-signing identity (Developer ID or a dedicated
local code-signing certificate approved/created manually by the owner), with
private key retained in Keychain. Select its SHA-1 fingerprint explicitly; do
not let a duplicate certificate name select a different key. Never commit the
key, certificate export, Keychain output or credentials. Do not sign with `-`
for production: an ad-hoc identity is not a stable identity across rebuilds.

Sign every release using the same certificate and explicit identifier
`com.orteipx.yabai`. Verify `codesign --verify --strict --verbose=2` and compare
`codesign -d -r-` between old and new releases: the designated requirement must
retain the intended identifier and signing identity. Do not loosen the
requirement to accept any signer or copy Homebrew's identity. Apple describes
how [designated requirements identify code across updates](https://developer.apple.com/library/archive/technotes/tn2206/_index.html).
Code signing does not itself grant Accessibility; macOS policy may require
manual reauthorization after an OS update or identity/certificate change.

Suggested staging sequence, after approval and selecting a signing identity:

```sh
# Run from the clean reviewed checkout. Choose the build type to be live-tested.
make
make -C tests
REVIEWED_COMMIT=$(git rev-parse HEAD)
STAGE=$(mktemp -d)
export STAGE
cp bin/yabai "$STAGE/yabai"
cp LICENSE.txt "$STAGE/LICENSE.txt"
cp doc/InstantSpaceSwitcher-LICENSE "$STAGE/InstantSpaceSwitcher-LICENSE"
# Replace SIGNING_IDENTITY with the approved persistent identity fingerprint.
codesign --force --sign "$SIGNING_IDENTITY" --identifier com.orteipx.yabai "$STAGE/yabai"
codesign --verify --strict --verbose=2 "$STAGE/yabai"
codesign -d -r- "$STAGE/yabai"
shasum -a 256 "$STAGE/yabai"
```

Record HEAD, SDK/OS build, architecture, build flags, signed-binary SHA-256 and
designated requirement in the release manifest. `make` builds debug flags;
`make install` in this repository only builds an optimized local binary, but
changing build flags still changes the artifact and requires validation. Do
not imply a debug test validates a different optimized/signed artifact.

## Controlled cutover (future approved work)

1. Capture desktop state, original Homebrew checksum/plist checksum and service
   identity as in `tests/live/README.md`. Ensure the staged artifact and signing
   identity match the approved build. Prepare the rollback commands first.
2. Create the stable directory and release backup; copy the signed candidate
   as `yabai.new` in the same directory. Verify the copy; defer the atomic
   rename until step 4 confirms all prior daemon PIDs have exited. Copy both
   license notices with it. On
   updates, keep the previous signed executable for rollback.
3. Use the label `com.orteipx.yabai` for the custom **user LaunchAgent**. Render
   a plist with absolute paths (launchd does not expand `$HOME` or `~`), not a
   LaunchDaemon/root job. Its `ProgramArguments` is the stable executable;
   `RunAtLoad` is true, `ProcessType` is Interactive, `ThrottleInterval` is 30,
   and `KeepAlive` is `{SuccessfulExit: false}`. Use user-owned stdout/stderr
   log paths under `~/Library/Logs/yabai-custom/`. Set an explicit PATH that
   includes `/opt/homebrew/bin` for configuration scripts. Validate the rendered
   plist with `plutil -lint`. Install it only after approval.
4. To prevent both agents starting after login, persistently disable only the
   original Homebrew **service label**, then boot it out. This does not edit
   the Homebrew executable or plist. Record the prior disabled-state override
   for rollback. Do not run `brew services`, `yabai --start-service` or the
   existing skhd service-start binding while the custom service is in use.

   ```sh
   launchctl print-disabled "gui/$(id -u)"
   launchctl disable "gui/$(id -u)/com.asmvik.yabai"
   launchctl bootout "gui/$(id -u)/com.asmvik.yabai"
   pgrep -x yabai
   ```

   Confirm the original PID exited and no other yabai exists before proceeding.
   Do not remove socket/lock files or bypass yabai's exclusive lock. If a
   daemon remains, identify it and stop only that known instance.
   On a custom-release update, boot out the custom label as well before
   replacing its binary. Leave Homebrew disabled throughout that update. When
   all known daemon PIDs have exited, atomically rename `yabai.new` to `yabai`.
   Never overwrite the executable in place while its daemon is running.
5. Run the **stable signed path** once in the foreground. If Accessibility is
   denied, stop and roll back. The owner can manually add that exact executable
   in System Settings → Privacy & Security → Accessibility, then approve a new
   attempt. Never automate TCC grants, database edits, resets, SIP changes or
   privileged injection. Do not try to fix authorization by making the program
   root. A working terminal launch does not guarantee the eventual launchd
   process is authorized; verify the launchd identity too.
6. Stop the foreground instance and verify its PID exited. Bootstrap only the
   custom agent, then inspect its PID and executable and query Spaces:

   ```sh
   launchctl enable "gui/$(id -u)/com.orteipx.yabai"
   launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.orteipx.yabai.plist"
   launchctl print "gui/$(id -u)/com.orteipx.yabai"
   pgrep -x yabai
   /opt/homebrew/bin/yabai -m query --spaces
   ```

   There must be exactly one daemon, at the stable custom path. Homebrew's
   client can continue sending `-m` commands over the unchanged socket. Run
   the approved smoke checks and examine logs. Logout/login must then be
   explicitly tested: the custom job should launch and the disabled Homebrew
   label should stay stopped. [Apple documents user-agent login behavior](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingLaunchdJobs.html).
7. Existing skhd `yabai -m ...` bindings remain valid. Its `yabai --stop-service`
   and `--start-service` bindings control the Homebrew label, not the custom
   one; they must be changed separately after approval to target the custom
   `launchctl` label. Never use those upstream service flags to manage this
   custom agent. Check for config signals that load the scripting addition
   and omit them in the approved custom config; this SIP-enabled deployment
   does not use one.

## Concrete staging and plist rendering commands

The following are future deployment commands, **not executed in this review**.
They extend the signing/staging block above. Run them only after deployment
approval. Do not paste a staged plist into LaunchAgents until cutover step 4.

```sh
INSTALL_ROOT="$HOME/.local/libexec/yabai-custom"
RELEASE="$INSTALL_ROOT/releases/$REVIEWED_COMMIT-$(date +%Y%m%d%H%M%S)"
mkdir -p "$INSTALL_ROOT/releases" "$HOME/Library/Logs/yabai-custom"
mkdir "$RELEASE"
cp "$STAGE/yabai" "$STAGE/LICENSE.txt" "$STAGE/InstantSpaceSwitcher-LICENSE" "$RELEASE/"
if test -f "$INSTALL_ROOT/yabai"; then
    cp "$INSTALL_ROOT/yabai" "$RELEASE/previous-yabai"
fi
install -m 755 "$STAGE/yabai" "$INSTALL_ROOT/yabai.new"
codesign --verify --strict "$INSTALL_ROOT/yabai.new"
shasum -a 256 "$INSTALL_ROOT/yabai.new" "$RELEASE/yabai"
python3 - <<'PYPLIST'
import os
from pathlib import Path
import plistlib
home = Path.home()
root = home / '.local/libexec/yabai-custom'
logs = home / 'Library/Logs/yabai-custom'
agent = {
    'Label': 'com.orteipx.yabai',
    'ProgramArguments': [str(root / 'yabai')],
    'RunAtLoad': True,
    'KeepAlive': {'SuccessfulExit': False},
    'ThrottleInterval': 30,
    'ProcessType': 'Interactive',
    'EnvironmentVariables': {'PATH': '/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'},
    'StandardOutPath': str(logs / 'stdout.log'),
    'StandardErrorPath': str(logs / 'stderr.log'),
}
with (Path(os.environ['STAGE']) / 'com.orteipx.yabai.plist').open('wb') as handle:
    plistlib.dump(agent, handle)
PYPLIST
plutil -lint "$STAGE/com.orteipx.yabai.plist"
```

After step 4 has stopped/disabled the appropriate jobs and verified their PIDs
are gone, complete the atomic switch and install the staged agent:

```sh
mv "$INSTALL_ROOT/yabai.new" "$INSTALL_ROOT/yabai"
mkdir -p "$HOME/Library/LaunchAgents"
install -m 644 "$STAGE/com.orteipx.yabai.plist" "$HOME/Library/LaunchAgents/com.orteipx.yabai.plist"
```

Then follow the foreground authorization check and single-agent bootstrap in
steps 5–6. Save the release manifest beside the notices before accepting the
release; do not infer commit identity from `yabai --version`, which still
reports the upstream version. These commands preserve `/opt/homebrew/bin/yabai`
and `com.asmvik.yabai.plist`.

## Rollback

After verifying that the custom label is the one to stop:

```sh
launchctl disable "gui/$(id -u)/com.orteipx.yabai"
launchctl bootout "gui/$(id -u)/com.orteipx.yabai"
# Verify its PID exited before starting Homebrew.
pgrep -x yabai
launchctl enable "gui/$(id -u)/com.asmvik.yabai"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.asmvik.yabai.plist"
launchctl print "gui/$(id -u)/com.asmvik.yabai"
/opt/homebrew/bin/yabai -m query --spaces
csrutil status
shasum -a 256 /opt/homebrew/bin/yabai
```

Restore the recorded original enabled-state override if it was different.
If a service is already bootstrapped, inspect it before using `kickstart` on
that specific label. Do not kill unrelated processes. Leave the custom label
disabled until another approved cutover, or archive its plist outside
`LaunchAgents` after approval. The Homebrew binary never needed replacement.
To roll back just a custom release instead, boot out the custom agent, verify
it exited, atomically restore the prior signed binary at the same stable path,
verify its signature/manifest and bootstrap only the custom agent.

## Later macOS releases

Record `sw_vers` and the SDK version before rebuilding. Update from reviewed
upstream changes in a separate review branch; inspect private class/method,
MIG message and serialized field changes rather than adding a broad version
check. Run all automated tests, diagnostics and an approved disposable-window
live replay on the actual OS/hardware. Preserve the certificate and designated
requirement, keep the previous signed release and repeat controlled cutover.
Do not promise macOS 27.2, future majors, Intel runtime behavior or a changed
SDK from the 27.0.1 M5 Pro result. A timeout does not cancel an OS operation.
