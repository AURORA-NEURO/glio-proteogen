# Published GBM proteomic-axis models (`gbm-proteomic-axes/1.0.0`)

## What this lane is

This research lane runs seven unchanged protein-abundance models from Lam et al.,
“Topographic mapping of the glioblastoma proteome reveals a triple-axis model of
intra-tumoral heterogeneity” ([Nature Communications 2022](https://doi.org/10.1038/s41467-021-27667-w)).
It is the first repository API backed by learned, glioblastoma-specific model weights rather
than caller-declared labels or a proxy formula.

The authors screened 1,410 gene-set signatures and published a 64-signature XGBoost protein
model family. This profile ports the three reported GBM axes plus four useful orthogonal
reference programs:

- `SWEET_KRAS_TARGETS_UP`
- `HALLMARK_MYC_TARGETS_V1`
- `WINTER_HYPOXIA_UP`
- `VERHAAK_GLIOBLASTOMA_MESENCHYMAL`
- `VERHAAK_GLIOBLASTOMA_NEURAL`
- `VERHAAK_GLIOBLASTOMA_PRONEURAL`
- `EGFR_UP.V1_UP`

These are continuous bulk-proteome signature scores. They are not cell fractions, diagnoses,
clinical subtypes, outcome predictions, or treatment recommendations. In particular, neural
and mesenchymal bulk signals can reflect normal-neural, immune, vascular, or hypoxic tissue
content as well as malignant-cell biology.

## Locked upstream provenance

The conversion is pinned to the authors’ MIT-licensed
[repository](https://github.com/diamandis-lab/paper-prot-atlas-gbm) at commit
`8d8c5725a82ef9505562e25fe2c5ea19fe608195`.

| Artifact | Locked SHA-256 |
|---|---|
| Original 64-model `RData` | `56aee53d2b247bb5dbaec7f876c0574ac0f89eccd98eade8f9437e1f1684a76c` |
| Repository prediction script | `f41614ac5a18e237e87a0f52159711c2be8fc39434f44a7a6ae3d994b0cbee1d` |
| Converted seven-model artifact | `2cd772b24a34c8f4fda56d932f40930f312750915c49695caad0e50dd9a5309d` |
| Author sample input | `7ab1a95f3f7d9e5afd5dd2710a3dcdd02dcc3df599c6f1f7d7b277ccf1311c62` |
| Author expected-output table | `bac5226c212d5ded43d88b8ef4abb3ebc140793486a1e82a817a8c031401906d` |
| Bundled deterministic oracle fixture | `ac5d185b2645c51dafbde8dd2daebd567a7d05c607c45d8e152900b4949ba475` |
| Upstream MIT license | `150f17448621b4c79dee5b975fc08f235eb09e4de6d5dff54a1a24854d9d482c` |

`tools/import_gbm_proteomic_axes.py` checks every upstream digest, uses R only to unpack the
legacy object, instantiates XGBoost 1.4.2 in an isolated maintainer environment, verifies that
each selected ensemble contains exactly 600 constant or depth-one trees over the same 3,025
features, and emits ordered numeric arrays. XGBoost and R are not application dependencies.
The wheel includes the converted arrays, oracle fixture, and upstream license.

## Exact inference semantics

For each sample, every positive LFQ value—including proteins outside the model feature
universe—participates in the authors’ normalization:

$$
x'_g = x_g\frac{10^7}{\exp\left(\frac{1}{|P|}\sum_{h\in P}\log x_h\right)},
\qquad P=\{h:x_h>0\}.
$$

Each model feature absent from the request is then filled with numeric zero, matching the
published script. Zero-fill is a software convention, not biological absence or negative
evidence, so every signature reports observed count, observed fraction, missing count, and
missing ratio. Left-censored measurements retain their upper limits in the receipt but are
excluded from point prediction; `missing` and `unsupported` declarations are also numerically
inactive.

The runtime evaluates all 600 trees in original training order with NumPy `float32`
accumulation, subtracts the authors’ training offset of 10, and reports the published
four-decimal score. It also groups selected stump-path leaves by feature for an auditable
decomposition. Those values are tree-path contributions—not SHAP values, causal effects, or
independent biological importance.

Fewer than 32 observed model features forces abstention. At least 32 but less than 50% of the
3,025-feature universe is labeled `limited`; at least 50% is labeled `supported`. These are
repository safety policies bound into the profile, not biologically validated cutoffs. The raw
published prediction is not altered when support is sufficient.

## Uncertainty and replay

When observed proteins include caller-supplied log2 standard errors, deterministic bootstrap
replicates perturb positive LFQ values on the log2 scale and rerun normalization plus every
tree. Seeds derive only from numerically active evidence, selected models, and replicate count;
sample labels, provenance, censored bounds, and inactive declarations cannot change draws.
Intervals propagate the supplied measurement-error model only. They do not cover cohort shift,
model-form error, sampling uncertainty, or tissue-origin confounding.

The profile digest binds NumPy 2.5.2, all numerical and support constants, exact model IDs,
source commit, original-model digest, converted-artifact digest, limits, and synthetic demo
digest. Results bind the request, profile, computational projection, evidence provenance,
scores, coverage, intervals, tree-path explanations, and limitations. Replay recomputes the
complete receipt and reports request, profile, model-source, result-digest, and semantic checks
separately.

The pure NumPy evaluator has maximum absolute error `0.0` against XGBoost 1.4.2 for the bundled
author sample and matches all 28 published signature/sample values exactly at four decimals.
That is a software-port oracle, not external biological validation.

## Interfaces and limits

- `GET /v1/research/gbm-proteomic-axes/profile`
- `GET /v1/research/gbm-proteomic-axes/demo`
- `POST /v1/research/gbm-proteomic-axes/analyze`
- `POST /v1/research/gbm-proteomic-axes/verify`
- `glio-proteogen gbm-axes profile|demo|analyze|verify`

Requests are stateless and accept at most 8,192 measurements, seven selected signatures, and
256 bootstrap replicates. Analysis requests are limited to 2 MiB, results to 1 MiB, and replay
envelopes to 4 MiB. Inputs and outputs are never persisted by this adapter.
