# Theoretical IL-L3 Handoff — Not an Establishment Declaration

## Purpose

This handoff advances the repository from disconnected object-level proof
fragments toward an executable **theoretical** IL-L3 proof suite.  It must not
be used to declare the frozen IL-L3 criterion established.  The remaining
integration tests require a real backend entry, a real user correction, and a
controlled process-loss injection in the target local environment.

## Changes in this handoff

1. `Ledger.get_latest_for_binding()` reconstructs all current formal objects
   for one `RunBinding` and integrity-checks every returned object.
2. `rebuild_authority_bundle()` fails closed unless a local `RunBinding`,
   `TaskDossier`, and `TaskRun` exist.  It returns the current formal refs,
   including action/evidence/experience refs, for a clean backend session.
3. The controlled write cycle accepts `task_dossier_ref` and `task_revision`.
   The first `TaskRun` revision is causally bound to the persisted task intent;
   a later plan carries the same task revision.
4. A new test makes an actual write in an isolated Git repository, closes the
   SQLite process, and rebuilds binding, intent, task, authorization, action,
   evidence, completion, and experience solely from local state.

## Required next implementation increments

The following are blocking L3 proof obligations.  Do not replace any one with
unit-object construction or an assertion about a simulated string reference.

### A. T4 / G3 — real backend-session destruction and continuation

Add a neutral backend integration test with this exact sequence:

1. Start a task using a backend session and persist a local `AuthorityBundle`.
2. Destroy the original backend session/process; assert its handle is unusable.
3. Start a fresh backend session with only refs reconstructed from the local
   ledger, not previous session history.
4. Continue the same task and verify that the backend cannot alter the dossier,
   authorization decision, or completion verdict directly.

The test must use the selected local backend entry.  `FileBackend` can be a
development double only when a separate real-backend acceptance run is kept.

### B. T7 / G2 — mid-task user correction must invalidate old action authority

Implement a correction command/service that atomically:

1. writes a new `TaskDossier` revision with the user correction source ref;
2. pauses the current `TaskRun` and records the superseded plan/ticket refs;
3. revokes or makes unexecutable every ticket bound to the superseded plan;
4. requires a fresh observation, plan, authorization, and verification before
   the corrected task can act.

Add an integration test that creates a first plan for `notes/welcome.txt`,
receives a correction to `notes/greeting.txt` before action, and proves the
old ticket cannot create `welcome.txt` while the corrected task can complete.

### C. T3 / G4 — crash at the side-effect/receipt boundary

Add a test-only executor hook immediately after the filesystem mutation and
before the final `ActionReceipt` is persisted.  The test must terminate the
worker at that hook, reopen the ledger in a fresh process, and run recovery.
It must prove that recovery observes the target and never calls the writer a
second time.  Keep the hook unavailable in production configuration.

### D. T5 / G7 — reality drift invalidates completed evidence

After a successful verified write, externally mutate the target.  The system
must create new revisions that invalidate the verification and completion
verdicts, then prevent those old refs from being used for experience promotion
or a user-visible `completed` claim.

### E. T2 / G6 — governance attack from a backend candidate

Have the backend produce a normalized candidate that requests an out-of-scope
or destructive operation during a live task.  The candidate must reach the
same authorization/enforcement boundary and be denied before any project
write.  A manually-created standalone plan is insufficient evidence.

### F. T6 / G8 — genuinely post-first unknown second task

The test harness must request or generate the second task only after first
completion and candidate experience persistence.  Its path/content must not
be created before the first task starts.  Preserve the causal chain
`experience → match → plan → completion`, and demonstrate that the match
changed the second plan without becoming an authorization.

## Establishment checklist

Only update `_project_source/active/20_CURRENT_REALITY/05_INITIAL_LOOP_ESTABLISHMENT_RECORD.md`
after all six increments have green, retained evidence from the selected local
backend entry, and a human review.  The record must state the exact commit,
test count, CI commit, environment, and remaining scope; it must never equate
a PR test merge commit with `main` CI.
