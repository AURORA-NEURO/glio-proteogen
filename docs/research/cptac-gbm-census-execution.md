# CPTAC census execution and exact numerical replay

Execution profile `cptac-gbm-census-execution/1.0.0`, evaluation
`cptac-gbm-real-census-execution/1.0.0`, adds bounded progress-file replacement
retries to the existing source-fit census. The entry point is
`tools/evaluate_cptac_gbm_census_execution.py`. This is an operational change,
with explicit execution provenance. It creates no scientific estimator, gene
universe, selection rule or validation experiment.

The inherited scientific profile remains
`cptac-gbm-source-fit-census/1.0.0`. Its original namespace, runner, method and
CLI retain their existing behavior. The
[source-fit census method](cptac-gbm-source-fit-census.md) continues to define
the numerical procedure, missingness semantics, support gates, model families,
fitting budget, external comparison and conditional interval limitations.
The execution profile requires exact replay of the complete inherited
artifacts, while adding two separately identified execution artifacts.

## Runtime baseline and provenance

Supply an existing complete baseline directory and exact `SourceLock` values
for its `protocol.json` and `evaluation.json`. A lock contains byte length,
MD5 and SHA256. Read bounded bytes, verify all three against the same bytes,
then parse canonical JSON. No baseline outcome count, derived hash or actual
result is embedded in this method or used as an implementation constant.

Before reading assay values, validate the complete baseline inventory:

1. The protocol and report use the inherited scientific identities and bind
   one another. Their closed schemas, completion declarations, source locks,
   numerical dependencies and method bindings must agree.
2. The ordered source and external manifests bind every declared page, byte
   length, canonical digest, gene record and stage count. All original gene
   identities occur once in the same source-defined order.
3. The root aggregates, catalogs, source checks, CSV, final progress snapshot
   and all page artifacts belong to that complete inventory. Reject unexpected
   or missing files, unsafe paths, links, changed bytes and incomplete runs.
4. Fresh generation of the inherited numerical protocol from the supplied
   source metadata must match the baseline protocol exactly before assays are
   opened. The new execution protocol cannot substitute for this check.

The baseline supplies locked comparison evidence, not fitted coefficients or
a predictor cache. Hashes establish local byte integrity; they do not prove
issuer authenticity, specimen identity, donor independence, reference-material
equivalence or permission to redistribute derivatives. Baseline results are
already known. Repeating them under this execution profile remains post hoc
computational replay, not an untouched external assessment.

Keep two protocol domains explicit:

| Domain | Purpose |
| --- | --- |
| Inherited census protocol | Numerical source/assay/fold bindings, source page context and per-gene request construction. It must reproduce the runtime baseline. |
| New execution protocol | New orchestration, progress policy, code and method provenance, plus the exact baseline locks and inherited bindings. It does not seed an inherited statistical calculation. |

The distinction prevents an operational source-code or documentation change
from silently changing the external bootstrap requests. Anchor requests retain
the historical approved-symbol construction:

```text
SHA256(canonical JSON {
  "protocol_digest": inherited provider-transfer protocol digest,
  "gene": approved anchor symbol
})
```

Every nonanchor retains the original census construction:

```text
SHA256(canonical JSON {
  "census_protocol_digest": runtime baseline census protocol digest,
  "hgnc_id": stable HGNC identity
})
```

Use the original lowercase `sha256:` representation. Neither the execution
profile ID nor its new protocol digest enters these requests. The inherited
evaluator therefore retains its original request-derived seeds and paired
external-patient sampling schedule. Retry attempts consume no model RNG draws.

## Recompute, then require complete equality

The runner accepts the existing census inputs and additionally:

```python
baseline_dir: Path
baseline_protocol_lock: SourceLock
baseline_evaluation_lock: SourceLock
```

All existing source metadata, measurement locks, historical panel-parent inputs
and output-directory requirements remain in force. The output directory must
be fresh. The baseline directory is read-only and cannot be the new output.

Every retained identity receives its ordinary source attempt using the unchanged
`fit_source_gene`. Count-capacity and variation flags do not select the genes
to recompute. Retain returned abstentions and explicit domain rejections.
Unexpected valid-input errors still stop an incomplete run. Do not load a
baseline source result instead of fitting, skip difficult genes, replace a
failed family, change support thresholds or relax convergence.

After all source fits, write and seal the inherited source pages, manifest,
catalog and source checks. Require their exact baseline bytes before admitting
external assay values. Preserve private source predictors only in RAM. Source
hydration reuses those same predictors without another fit or family choice.
A baseline source receipt cannot reconstruct a predictor after a process exit.

Read and project the external cohort only after this source equality gate.
Every identity receives the inherited external-stage behavior. Pass the
baseline numerical protocol to the existing external record/request helper;
evaluate with the unchanged `evaluate_external_gene`. Preserve its complete
point metrics, signed deltas, source-median R2, optional intervals, abstentions,
request identifiers, seeds and child profile identities.

Compare external result pages as they are written. At the end, require exact
equality for **every** inherited artifact, including CSV cells and bytes,
evaluation report, catalogs, manifests, pages, source checks and final progress
snapshot. Point-only, interval-only, count-only or tolerance-based matches do
not satisfy this execution profile. A mismatch stops completion; it is not a
new scientific result or a reason to retune the method.

The two additional files have separate responsibilities:

- `execution-protocol.json` freezes the new operational implementation,
  progress policy and baseline evidence before assay reads.
- `execution.json` records completion, exact inherited replay and execution
  provenance only after all inherited artifact checks pass.

The new execution seal is authoritative for this profile. A legacy report or
final legacy progress snapshot alone cannot establish successful execution
replay if a later equality check failed or `execution.json` is absent.

Inherited files keep their original scientific profile and protocol bytes.
The additional files identify the new execution profile. No execution metadata
is injected into legacy files to make an operational change look like a new
numerical experiment. No retry counters, wall-clock measurements or timing
values are added to the inherited artifacts.

## Bounded progress replacement

Windows handle-sharing policies can prevent operations requesting delete access;
delete access includes rename operations. These semantics explain a possible
source of transient replacement failures, but a returned access error alone
does not identify its exact cause.
[Microsoft CreateFileW documentation](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)

Python exposes replacement through `Path.replace`/`os.replace`. Filesystem,
permission and platform constraints still apply. This execution policy does
not change access-control lists, close another process's handles, guarantee
availability under a persistent lock, or establish crash durability.
[Python Path.replace](https://docs.python.org/3.12/library/pathlib.html#pathlib.Path.replace),
[Microsoft MoveFileExW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-movefileexw)

The orchestration guards the aggregate progress object and encodes canonical
bytes before calling `write_progress_snapshot`. The fixed default policy is:

```text
maximum retry wait = 2.0 seconds
maximum replacement attempts = 101
retry interval = 0.02 seconds
maximum encoded progress payload = 64 KiB
```

The bound limits retry scheduling; an operating-system call itself is not a
real-time operation. The writer performs these steps:

1. Validate the fixed retry policy and bounded byte payload. Honor cancellation
   without interpreting it as a sharing failure.
2. Exclusively create `progress.json.tmp`, write the exact payload once and
   close the temporary file. Writing and serialization are outside the narrow
   replacement retry handler.
3. Attempt replacement of `progress.json` using that same completed temporary
   file. Retry only on Windows `PermissionError` with `errno == EACCES` and
   `winerror` equal to 5, 32 or 33, within both the time and attempt bounds.
   These codes are an operational retry class, not proof that a reader caused
   the exception.
4. Publish only the original bytes. No retry repeats a source fit, numerical
   selection, prediction, bootstrap, page write or source/external checkpoint
   computation. Do not truncate the live progress file as a fallback.
5. Propagate unexpected errors immediately. Exhausted replacement attempts
   raise `ProgressReplacementExhaustedError`, a sanitized fatal timeout.
   Preserve incomplete evidence rather than
   falsely setting completion or advancing a scientific stage.

A completed temporary file may remain after failure. Do not delete or overwrite
it to resume the same run. Preserve the incomplete directory and restart all
source fitting in a fresh output directory under the same frozen method.
There is no serialized predictor recovery or public resume mechanism.

Observe long runs through process status and their terminal stdout/exit state.
Inspect progress files after termination. Retry support does not make arbitrary
live file readers safe, and `FILE_SHARE_DELETE` alone is not a portable promise
that every replacement will succeed.

## Controls and interpretation

Synthetic integration must establish complete inherited numerical parity for
anchors and nonanchors, including request-derived uncertainty. Tests must also
show baseline validation before assays, ordinary recomputation of every gene,
source equality before external values, unchanged predictor hydration, exact
page/CSV/report replay, and a separate new execution completion seal.

Inject transient replacement failures, exhaustion and unexpected errors.
Verify that retries publish identical bytes, never duplicate a numerical call,
never accept changed baseline evidence and never turn an incomplete run into
a valid report. Windows held-reader tests must use synthetic progress files,
close native handles, distinguish held-reader behavior from the unlocked
baseline, and make no claim about an earlier interruption's unrecorded cause.

Freeze the new operational method, code, baseline bindings and tests before
actual execution. Then perform complete fresh executions, compare all inherited
artifacts against the baseline, and independently audit both the numerical
replay and new provenance. Preserve any failed operational attempt separately;
do not discard contrary evidence or edit result files to obtain a match.

All inherited scientific limitations remain: source selection is already
outcome-informed; winning OOF selection criteria are not unbiased performance
estimates; external intervals condition on frozen source fitting/selection;
genes share patients and differ in complete-case support and target scale;
and processing, reference, molecular-eligibility and donor-independence limits
remain unresolved. Exact replay is an execution property. It establishes no
new biological mechanism, clinical usefulness, calibrated interval coverage,
multiplicity-controlled discovery, simultaneous gene inference or novelty.

Outputs contain approved gene identities, aggregate diagnostics and integrity
bindings. They contain no patient/specimen/file IDs, measurement arrays,
coefficients, predictions, residuals or resampling memberships. Source-derived
artifacts remain `local_only_terms_unverified`; keep actual outcome files and
private baseline bindings outside Git. No UI, HTTP endpoint or new scientific
lane is introduced by this execution profile.
