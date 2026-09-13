# Published GBMPurity NumPy lane (`gbm-rna-tumor-purity/1.0.0`)

This research-only lane runs the published GBMPurity neural model for one
narrow task: estimating malignant-cell fraction from raw bulk RNA-sequencing
counts in primary IDH-wildtype glioblastoma. It is a port of fitted weights,
not a repository-authored score and not a protein deconvolution method.

## Exact admitted source

| Item | Lock |
|---|---|
| Upstream repository | `https://github.com/scmpht/GBMPurity` |
| Commit | `af054edcf4c54e9bbcf0dbe6d89dfac6e20aa950` |
| `model/GBMPurity.pt` | `sha256:80abd8d8f4875799f839701bec655d2e4753c750e63e60b9119b8b66342025c7` |
| `model/input-genes-lengths.csv` | `sha256:de148837ab4d487b3fd86436f63e95b451fa4a305c5bf8d5eb094c117941884b` |
| Upstream `LICENSE` | MIT, `sha256:3f0041f0cfe77a6f4153e1465b1590b744102d9e8948203bcb56d9b244367ef7` |
| Converted artifact content | `sha256:651fa1ea9100650d8b34cec3c980624e42bada1ec3ff9cfe23fdf13049585722` |
| Converted artifact file | `sha256:2999d845c602c7b8b44d45c37a7f43bea57ad6a930af12f9c7b56cc221ffccc2` |
| Ordered 5,829-gene vector | `sha256:8a2e26d736fb8e1eb2a0ddf5799e2368acb1b6798275d75ef9c60f0c49204112` |
| Six-tensor bundle | `sha256:2d9ceef433761d9b68419bce4c9c7ed4fb1009b9b195f1b1ea2d81f8913a30f4` |

The source article is Thomas et al., *Neuro-Oncology* 27(6):1458-1473
(2025), DOI [`10.1093/neuonc/noaf026`](https://doi.org/10.1093/neuonc/noaf026),
published under CC BY 4.0. The upstream root MIT license covers the distributed
software, pretrained object, and input table. The converted artifact retains
the complete MIT notice and a modification statement.

`tools/import_gbm_rna_purity.py` checks the complete tracked Git inventory,
repository and commit, every tracked byte digest, the serialized archive member
inventory, parameter sizes and finiteness, source architecture fragments, input
gene order, and license before regenerating the artifact. It reads the known
float32 storages directly from the PyTorch ZIP container and never executes the
pickle. The runtime therefore has no PyTorch dependency.
The runtime independently hard-pins all four converted-artifact, content,
feature-order, and tensor-bundle digests; recomputing an internal checksum does
not make a substituted model admissible.

One upstream training-script typo is preserved as provenance rather than hidden:
`trainGBMPurity.py` imports `MLP2h` but later names an undefined `GBMPurity`
constructor. The released pickle, `torch_models.MLP2h`, inference script, tensor
shapes, and published methods all unambiguously identify the deployed network.

## Exact computation

Inputs are unique, case-sensitive gene symbols with finite nonnegative raw
counts. The request must attest the intended disease, specimen, assay, raw-count,
and no-batch-correction scope. Counts are reindexed to the exact 5,829 source
genes. Missing source genes are zero-filled only after the published overlap
gate passes:

- below 80% recognized genes: abstain without executing the network;
- 80% through below 99%: execute but label support `limited`;
- at least 99%: label support `supported`.

For ordered source gene `g`, the preprocessing is

```text
rpk[g] = count[g] / feature_length[g]
source_scaled_tpm[g] = rpk[g] / sum(rpk) * 10,000
x[g] = log2(source_scaled_tpm[g] + 1)
```

The `10,000` multiplier is the source implementation's deliberate 100-fold
rescaling of conventional TPM. The network is evaluated in float32 with dropout
disabled:

```text
5,829 inputs -> Linear(32) -> ReLU -> Linear(16) -> ReLU -> Linear(1)
```

The raw linear output is clipped to `[0,1]`, exactly as upstream. Locked
synthetic inputs match independent upstream PyTorch results within `5e-7`; the
versioned demo differs by `8.94e-8` before output quantization.

## Explanation and uncertainty

For the input-specific ReLU masks, the network is exactly affine. The engine
multiplies the active weight paths to compute the local gradient for all 5,829
features, decomposes the raw output into gene and active-bias contributions,
and reports the 20 largest absolute gene contributions. The reconstruction
error is carried in the receipt. This is a local numerical explanation only;
it is not causal importance, a biomarker panel, or a global SHAP substitute.
Hidden nodes are not assigned biological meanings.

The published release contains a single fitted MLP and no calibrated ensemble.
The result therefore says uncertainty is unavailable instead of fabricating a
bootstrap interval. Gene coverage, zero-total-count abstention, clipping state,
hidden activations, and every source/profile/result digest remain explicit.

## Interfaces

- `GET /v1/research/gbm-rna-purity/profile`
- `GET /v1/research/gbm-rna-purity/demo`
- `POST /v1/research/gbm-rna-purity/analyze`
- `POST /v1/research/gbm-rna-purity/verify`
- `glio-proteogen gbm-rna-purity profile|demo|analyze|verify`

The service is synchronous, stateless, bounded, and non-persistent. The v2
route-derived deployment catalog registers the demo as a validated example.

## Claim ceiling

The output is the published model's estimated malignant-cell fraction for the
declared primary IDH-wildtype GBM bulk-RNA context. It is not a histopathology
measurement, tumor diagnosis, purity ground truth, immune or stromal breakdown,
cell-state composition, protein result, prognosis, treatment prediction, or
clinical recommendation. Cohort shift, sampling, RNA quality, library
composition, and missing genes remain limitations.
