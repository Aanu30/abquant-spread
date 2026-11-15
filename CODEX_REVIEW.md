# Live final reliability review

Static review of `abquant/live.py`, `abquant/desk.py`, and `run_final.sh`, against the local Spread rules/API. No bot run or network request was made.

## Findings (most severe first)

### 1. [P1] Ambiguous actions can be replayed before the required state read

**Files:** `abquant/live.py:186-209`, `abquant/live.py:117-131`, `abquant/desk.py:819-853`, `abquant/desk.py:1008-1028`

When an action request fails with a non-400 `SpreadError`, `Desk.send()` puts the failed chunk back in `outbox` and sets `sync_needed` (`desk.py:850-853`). The main loop calls `desk.send()` unconditionally at `live.py:186`, before it reaches the snapshot/reconcile block at `live.py:198-209`. A 502/503 or lost response can therefore cause an action that the server already applied to be sent again before the bot checks server state. The restart path also calls `desk.send()` at `live.py:131` even if the preceding `reconcile()` raised and was only logged (`live.py:125-131`). Further, `reconcile()` removes uncertain `post` and `quote` actions only; pending `offer`, `withdraw`, and `reprice` actions survive (`desk.py:1010-1012`). Retrying an accepted offer can send it twice; other actions can be duplicated or refused.

**Suggested fix:** Make `sync_needed` a hard send gate. After any ambiguous result, first obtain a successful authoritative snapshot and reconcile every pending action type against state/events before retrying it. Keep unresolved actions quarantined rather than blindly replaying them; use server idempotency keys if the API supports them. Apply the same gate when restart reconciliation fails.

### 2. [P1] A handler error permanently skips that event

**Files:** `abquant/live.py:119-124`, `abquant/live.py:164-173`, `abquant/live.py:218-220`

Both restart catch-up and the live loop advance `last_seq` even when `desk.handle(event)` raises. In the live loop this happens before the handler call (`live.py:166`), and the exception is logged and discarded (`live.py:169-173`). The advanced sequence is then saved periodically. Reconnects and restarts request only events after that sequence, so an event that failed before queuing its action (for example, a `price_request`) can be permanently skipped, and a partially processed `order_won` can be left without the expected follow-up work.

**Suggested fix:** Treat event application and sequence advancement as one recoverable operation: make handlers idempotent and advance the cursor only after successful handling. On a handler failure, restore the prior desk state or rebuild/reconcile before continuing; do not persist a cursor past an unapplied event.

### 3. [P1] Quote handling has no deadline protection and can block behind backlog or HTTP calls

**Files:** `abquant/live.py:148-186`, `abquant/desk.py:819-853`, `abquant/desk.py:1196-1201`

The loop drains the queue until it observes it empty (`live.py:151-155`), then handles the whole batch before sending (`live.py:157-186`). The queue is unbounded, so a sustained event burst can keep the drain/handling phase from reaching the send. `Desk.send()` is synchronous, and a multi-leg `post()` can call it inline while handling an event (`desk.py:1196-1201`), before a later queued price request is handled. The bundled client also waits for rate-limit tokens/429 responses and has a 20-second HTTP timeout; either wait can exceed the 4.5-second quote window while the main event loop is blocked. Sorting quotes first only helps after the current `send()` call begins.

**Suggested fix:** Use bounded event batches and a deadline-aware quote queue. Do not make network calls inside event handlers; queue all actions for one scheduler that prioritizes the oldest expiring quote over non-urgent actions. Track each request’s `respondBy` and record/alert when a quote cannot be sent in time.

### 4. [P1] Stream reader threads are not reliably stopped across an in-process rejoin

**Files:** `abquant/live.py:84-98`, `abquant/live.py:138`, `abquant/live.py:158-162`, `abquant/live.py:237-239`, `abquant/live.py:281-289`

`play()` starts a daemon reader but does not retain or join it. Its `stop` flag is checked only after `world.stream()` yields an event. The stream can be blocked on socket input or inside its reconnect delay, so setting the flag in `finally` does not stop it promptly. `final()` catches a `play()` failure and starts another `play()` in the same process, creating another reader while the old one may still be reconnecting. Repeated failures can leave multiple streams consuming the team’s concurrent-stream allowance and resources.

**Suggested fix:** Keep the reader handle and a way to close/interupt its active socket and reconnect wait. On every `play()` exit, stop and join that reader before retrying; enforce exactly one active reader for the world.

### 5. [P1] The shell runner allows two copies to trade and overwrite the same state

**File:** `run_final.sh:6-15`

The restart loop has no single-instance lock. Starting the script twice (or leaving an earlier copy running) launches two bots with the same team key and world. Each process has its own client-side rate limiter while the server shares the 20-actions/sec and 50-reads/sec buckets by team key, so their combined traffic can receive 429s. Both also write the same state file and `.tmp` path, creating a race that can lose or corrupt the checkpoint and make both copies replay actions.

**Suggested fix:** Acquire an atomic per-project/per-team lock before launching the loop and release it with a shell trap. Exit with a clear message if another runner already holds it.

### 6. [P2] Permanent errors while waiting for the final are retried forever

**File:** `abquant/live.py:250-265`

`next_final()` retries every `SpreadError` indefinitely. It specially handles the expected missing-final statuses, but also prints and then sleeps/retries for permanent errors such as an unauthorized key or forbidden access. Since this loop does not exit, `run_final.sh` cannot detect the failure or restart into a useful state.

**Suggested fix:** Retry only expected not-ready, network, and transient server errors (including 502/503/504). Fail clearly on permanent authentication/permission/client errors so they can be corrected before the final.

## Rate-limit note

I found no unconditional over-limit loop in these three files when only one bot process runs: the bundled client paces requests and waits out 429 responses. Those waits are synchronous and can still cost the quote window (finding 3). The missing runner lock makes multiple local copies a concrete way to defeat that per-process pacing (finding 5).
