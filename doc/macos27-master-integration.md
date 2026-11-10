# Fast-forward preparation (not executed)

Read-only remote checks on 2026-11-10 found both `upstream/master` and the
fork's remote `master` at `dd845723416f5fe92af49fad5ebab00369e07edd`.
The implementation is based on that commit, so a fast-forward is possible
provided neither branch diverges. No merge, master checkout or push has occurred.

The historical 46/46 live result applies to the pre-review build. Before
approving integration, review the new commit and accept/repeat live validation
of that exact build as described in `tests/live/README.md`. The review includes
changes to timeout, race and failure paths that the historical live run did
not exercise. Automated/sanitizer success is not a substitute for that decision.

After explicit approval, run the following from the repository. Replace the
placeholder with the full reviewed commit hash reported for `fix-macos27`:

```sh
set -e
REVIEWED_COMMIT=<full-reviewed-commit-hash>
test -z "$(git status --porcelain)"
test "$(git rev-parse fix-macos27)" = "$REVIEWED_COMMIT"
git fetch origin master
git merge-base --is-ancestor master "$REVIEWED_COMMIT"
git merge-base --is-ancestor origin/master "$REVIEWED_COMMIT"
git switch master
git merge --ff-only "$REVIEWED_COMMIT"
git log -1 --oneline
```

Stop on any failed precondition: do not reset or force a divergent master.
Fetching updates the remote-tracking ref, not the local master or server.
After separate push approval (or one explicit approval covering merge and push):

```sh
git push --dry-run origin master
git push origin master
```

This is a normal fast-forward push, never a force push. If the remote moves
again, the push must fail and be reviewed. Branch cleanup is optional after
successful integration and review; do not keep merging from the unrelated
`macos-27-sip` experimental branch. Future compatibility work should start from
the fork's maintained master and return through reviewed commits. Production
cutover remains a separate approved operation in `doc/macos27-deployment.md`.
