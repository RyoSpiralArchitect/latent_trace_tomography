# Output-only Furnace/API bridge v1

A separate, bounded **observability and behavior-prediction pilot**. It is not
frozen OSS-1 collection, semantic-mechanism attribution, or hidden-trace recovery.
The matched-renderer pilot found a semantic-carrier measurement blind spot; its
zero scores must not become semantic-reliance training labels here.

## Fixed panel

Two fresh synthetic contents; balanced semantic/cue/codebook cells. Weak queries
have semantic == cue. Five training-aligned renderers: baseline, rule paraphrase,
evidence reorder, irrelevant distractor, and lower-salience but still explicit cue.
Eight aligned cases × five projections × two declared repetitions = 80 queries.
Repetitions are not independent subjects. Neither temperature zero nor two samples
establish determinism or a calibrated sampling distribution.

Challenge queries have semantic != cue. Eight cases × ordinary/table rendering ×
two repetitions = 32 queries. The table uses the same required/candidate evidence,
not a supplied mismatch answer. This is a new successor rendering, not the frozen
OSS-1 mismatch-table contract. Full inventory: 112 queries per target.

Furnace: all nine retained anchors, 1,008 logical completions, at most 16,128 counted
forwards / 600 seconds, unchanged fp32/eager/greedy/EOS/max-16 decoder. No new
interventions, training, model downloads or original evidence edits.

API: one pinned `gpt-4.1-mini-2025-04-14` endpoint, maximum 112 requests, sequential,
temperature 0, max_output_tokens 32, service_tier default, store false, no tools,
no log probabilities, no conversation state, no automatic retries or model fallback.
API message wrapping and its 32-token cap differ from the OSS raw-completion
runtime; comparisons are not claims of identical underlying computation.

Only synthetic prompt text is transmitted. The existing key is read from the Mac
environment, never written, printed, placed in argv, or copied to Furnace. The
HTTP destination is fixed to api.openai.com:443 with normal TLS verification.
No redirects or implicit proxy routing. Error bodies are not persisted; only safe
status categories are retained. store=false is not a zero-retention guarantee.

## Budget

Observed official standard price on 2026-10-23 JST: $0.40/M input, $1.60/M output
tokens. A conservative reservation of 8,192 input + 32 output tokens per request
costs $0.003328, or **$0.372736 for 112 requests**, below the $0.50 pilot ceiling.
Prompts are capped at 4,096 ASCII bytes and contain no tools/history. The input
allowance includes substantial wrapper margin; it is a client-side estimate, not
an account-level billing cap. Returned usage is checked and reported separately.
An unknown network outcome consumes its reservation and stops that phase, never
creating retry credit. An HTTP, usage, or response-contract error also stops it.

Sources actually consulted:

- https://developers.openai.com/api/docs/models/gpt-4.1-mini
- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/reference/resources/responses/methods/create

## Exact interface and honest abstention

The estimator sees only six fields: opaque target ID, case ID, projection ID,
replicate ID, prompt text, output text. Feature values use only parsed A/B/failure:
15 marginal counts + 36 baseline-to-projection transition counts, denominator 16.
Model names, family labels, timings, usage, logits, tensors, and causal labels
never enter those feature values. IDs are joins, not predictive covariates.

Compute the nine OSS feature vectors and the API weak vector. Exact equality
defines a finite reference support set; this is a conservative operational rule,
not a calibrated out-of-distribution test. No match -> abstain on prediction.
Matches -> use their observed OSS challenge outputs, add one count per A/B/failure
within each reference family, and average family distributions equally. This is
a fixed, **behavior-only** reference forecast, not mechanistic prediction.
It can still learn renderer sensitivity or family quirks; no population/general
mechanism claim is licensed. Single-match attribution is also prohibited.

Persist that forecast/abstention and its source receipts **before** API challenge
requests. Score the locked probabilities descriptively if any; always report
coverage, parse failures, semantic/cue-consistent challenge behavior, and all
reference-support ambiguity. Do not move thresholds after seeing API results.
The nine OSS instances share three lineage clusters; effective independent n is
not nine. No calibrated confidence, significance test, or population CI is claimed.

## Sequence

Prepare/hash the panel; simulate all API request/response contracts without network;
run Furnace and API-weak; lock the output-only forecast; run API-challenge once;
audit receipts, event chains, prompt inventories, costs and chronology; describe
the saved evidence. Every phase has an exclusive claim and an immutable receipt.
No restart/resume in this version. A failed attempt remains evidence.
