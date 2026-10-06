# Escrow with AI Dispute Resolution

A standalone GenLayer Intelligent Contract primitive submitted for the **Standalone Contracts** track.

## Purpose

A client funds a job in native GEN for a provider to deliver a piece of work
at some URL (a repo, a document, a deployed page, an API response, anything
web-readable). The happy path is fully deterministic: the client approves
and the provider is paid, no AI involved. The contract only calls the AI
when the parties actually disagree: the client disputes that the delivered
work satisfies the agreed description.

This is a direct implementation of GenLayer's own flagship use case ("the
internet never had a judge") applied to the simplest possible agent-to-agent
transaction: pay for a service, the seller says "delivered", and now
something has to decide whether that is true without a human in the loop,
and without trusting either party or a centralized middleman.

Real-world use cases:

- **Freelance / gig payments** between parties with no prior trust.
- **Agent-to-agent commerce** — one AI agent pays another for a task and
  needs a neutral settlement layer when the result is contested.
- **API/data delivery contracts** — pay on confirmed, verifiable delivery
  instead of trusting a status flag the seller controls.

## Why this is a real primitive, not a demo

- **AI is not the default path.** Funding, delivery, manual approval, and
  reclaiming an unfulfilled job are all deterministic, zero-AI code paths.
  The AI consensus round only runs on `resolve_dispute`, when it is
  genuinely needed. This matters: many GenLayer submissions treat AI as a
  rubber stamp on every transaction; here it is reserved for the one step
  that actually requires judgment.
- **Equivalence Principle is used for real.** The validator does not just
  check that the leader's JSON is well-formed. It independently re-fetches
  the same `deliverable_url` and re-derives its own verdict, then the two
  are compared on the decision field only (`work_satisfies_description`,
  a strict boolean). Free-text reasoning is stored but never compared,
  since two independent LLM runs will always phrase it differently.
- **Errors are classified, not swallowed.** Following GenLayer's documented
  error-handling convention, failures are tagged `[EXPECTED]` (business
  logic, must match exactly), `[EXTERNAL]` (4xx from the evidence URL, must
  match exactly), `[TRANSIENT]` (network/5xx, validators agree if both hit
  one), or `[LLM_ERROR]` (malformed model output, always forces
  disagreement and rotation). A validator never silently agrees with a
  leader that got a broken LLM response.
- **Money safety.** Amounts are native GEN wei (`u256`), exactly as sent via
  `@gl.public.write.payable` / `gl.message.value` — no float math anywhere.
  A job's status is flipped to its terminal value (`released`/`refunded`)
  *before* the payout is emitted, so retrying `resolve_dispute` can never
  pay out twice. The GEN transfer is emitted with `on="finalized"`, so
  funds only actually move once the resolving transaction itself survives
  its own appeal window, not the instant consensus is first reached.

## Design

### Lifecycle

```
fund_job            (client, payable)   -> status: funded
mark_delivered       (provider)          -> status: delivered
release_payment      (client)            -> status: released   [deterministic]
reclaim_unfulfilled  (client)            -> status: refunded    [deterministic,
                                             only while still "funded"]
dispute              (client)            -> status: disputed
resolve_dispute      (anyone)            -> status: released | refunded  [AI consensus]
```

### Consensus (Equivalence Principle, independent comparison)

```
leader_fn():
    page = gl.nondet.web.get(deliverable_url)
    ask LLM: does this evidence satisfy the agreed description,
             given the client's stated complaint?
    return _validate_verdict(parsed JSON)      # strict, see below

validator_fn(leader_result):
    leader_data    = _validate_verdict(leader_result)   # reject malformed leader output
    validator_data = leader_fn()                        # independently re-fetch + re-derive
    accept only if:
        work_satisfies_description matches exactly (strict boolean)
```

### Strict verdict validation before any payout decision

LLM output is untrusted. `_validate_verdict` is applied to both the leader's
and the validator's own result, and once more immediately before the
contract decides who gets paid. A result is accepted only if:

| Field | Requirement |
|---|---|
| `work_satisfies_description` | a real JSON boolean — a string like `"false"` is rejected |
| `reasoning` | a string (stored truncated to 500 characters) |

Malformed results make validators disagree, so a dispute can never resolve
to a payout based on garbage model output. These rules are covered by
offline tests (`tests/test_verdict_validation.py`) that load the helper
functions straight from the contract source, so they always test exactly
the code that is deployed:

```
python3 tests/test_verdict_validation.py
```

## Deployed contract

The source in this repository is byte-for-byte the source that was deployed.

| Field | Value |
|---|---|
| Network | GenLayer Studio (Studionet) |
| Deployed address | `<FULL ADDRESS OF THE DEPLOYMENT>` |
| Explorer | `https://explorer-studio.genlayer.com/address/<FULL ADDRESS>` |
| Source | [`escrow_dispute_resolution.py`](./escrow_dispute_resolution.py) |

## Live test evidence

Two consensus rounds on `resolve_dispute`: one where the evidence genuinely
does **not** support the provider's delivery, and one where it does.

### Scenario 1 — dispute upheld, client refunded

| Field | Value |
|---|---|
| `description` | `<job description used>` |
| `deliverable_url` | `<evidence URL used>` |
| `dispute_evidence` | `<client's stated complaint>` |
| Result | `work_satisfies_description: false` -> `status: refunded` |
| Tx (`resolve_dispute`) | `<TX HASH>` |

### Scenario 2 — dispute rejected, provider paid

| Field | Value |
|---|---|
| `description` | `<job description used>` |
| `deliverable_url` | `<evidence URL used>` |
| `dispute_evidence` | `<client's stated complaint>` |
| Result | `work_satisfies_description: true` -> `status: released` |
| Tx (`resolve_dispute`) | `<TX HASH>` |

## Reproducing

1. Open [GenLayer Studio](https://studio.genlayer.com) and deploy
   `escrow_dispute_resolution.py` (constructor takes no arguments).
2. `fund_job(provider_address, description)` — attach GEN as the call value.
3. `mark_delivered(job_id, deliverable_url)` as the provider.
4. Either `release_payment(job_id)` as the client (deterministic), or
   `dispute(job_id, evidence)` followed by `resolve_dispute(job_id)` to
   trigger AI consensus.
5. `get_job(job_id)` to read back `status`, `verdict_reasoning`, and the
   rest of the job state.

## Files

- [`escrow_dispute_resolution.py`](./escrow_dispute_resolution.py) — contract source
- [`tests/test_verdict_validation.py`](./tests/test_verdict_validation.py) — offline validation tests
- [`LICENSE`](./LICENSE) — MIT
