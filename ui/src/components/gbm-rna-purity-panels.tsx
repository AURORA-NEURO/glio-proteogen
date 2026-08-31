import {
  GBM_RNA_PURITY_MODEL_FEATURE_COUNT,
  gbmRnaPurityRequestStats,
  type GbmRnaPurityEvidence,
} from "@/lib/gbm-rna-purity";
import {
  formatNumber,
  formatSigned,
  objectAt,
  shortDigest,
  textAt,
  type JsonObject,
} from "@/lib/research-state";

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function fractionLabel(value: number | null): string {
  return value === null ? "—" : `${formatNumber(value * 100, 1)}%`;
}

function PurityFractionMark({ value }: { value: number | null }) {
  const bounded = Math.max(0, Math.min(1, value ?? 0));
  return (
    <div
      aria-label={value === null ? "No malignant-cell fraction estimate" : `Estimated malignant-cell fraction ${fractionLabel(value)}`}
      style={{
        position: "relative",
        height: 12,
        marginTop: 14,
        overflow: "hidden",
        border: "1px solid rgba(165, 182, 193, .14)",
        borderRadius: 999,
        background: "rgba(255, 255, 255, .035)",
      }}
    >
      <span
        style={{
          display: "block",
          width: `${bounded * 100}%`,
          height: "100%",
          background: value === null ? "transparent" : "linear-gradient(90deg, rgba(120, 182, 255, .7), rgba(118, 230, 202, .92))",
        }}
      />
    </div>
  );
}

function CoveragePanel({ evidence }: { evidence: GbmRnaPurityEvidence }) {
  const coverage = evidence.coverage;
  return (
    <section className="result-panel zero-fill-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">FROZEN 5,829-GENE FEATURE SPACE</p><h3>Source-model coverage and zero-fill burden</h3></div>
        <span className={`support-badge ${evidence.support}`}>{evidence.support}</span>
      </div>
      <div className="zero-fill-notice">
        <b>Published gate preserved</b>
        <span>Inference abstains below 80% exact feature overlap. Only after that gate, unprovided model genes receive the released model&apos;s numeric zero-fill convention; zero-fill is not evidence of biological absence.</span>
      </div>
      <div className="zero-fill-explainer">
        <article><b>Recognized model genes</b><strong>{coverage.recognizedModelGeneCount.toLocaleString("en-US")}</strong><p>{fractionLabel(coverage.coverageFraction)} of the frozen {coverage.modelFeatureCount.toLocaleString("en-US")}-gene input order.</p></article>
        <article className={coverage.missingModelGeneCount > 0 ? "warning" : undefined}><b>Missing / zero-filled</b><strong>{coverage.missingModelGeneCount.toLocaleString("en-US")}</strong><p>Applied only after the 80% overlap gate; the source warns this can lower estimates.</p></article>
        <article><b>Ignored non-model genes</b><strong>{coverage.ignoredNonModelGeneCount.toLocaleString("en-US")}</strong><p>Supplied counts outside the exact released feature order do not enter the network.</p></article>
        <article><b>Nonzero model genes</b><strong>{coverage.nonzeroModelGeneCount.toLocaleString("en-US")}</strong><p>Recognized genes with a positive raw count before source-parity preprocessing.</p></article>
      </div>
    </section>
  );
}

function AttributionPanel({ evidence }: { evidence: GbmRnaPurityEvidence }) {
  const explanation = evidence.explanation;
  return (
    <section className="result-panel state-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">EXACT ACTIVE-RELU PATH DECOMPOSITION</p><h3>Local numerical drivers</h3></div>
        <span className="boundary-chip">local forward-pass explanation · not causal biology</span>
      </div>
      {!explanation ? <p className="panel-empty">No local explanation is emitted when the model abstains.</p> : <>
        <div className="zero-fill-notice">
          <b>Exact only at this activation pattern</b>
          <span>The reported gradient × transformed-expression terms reconstruct this piecewise-linear forward pass. They are not global feature importance, biomarkers, causal genes, or effects of experimental intervention.</span>
        </div>
        <div className="state-table-wrap">
          <table className="state-table">
            <thead><tr><th>Rank / gene</th><th>Transformed expression</th><th>Local gradient</th><th>Raw-output contribution</th><th>Direction</th></tr></thead>
            <tbody>{explanation.attributions.map((attribution) => (
              <tr key={`${attribution.rank}-${attribution.geneSymbol}`} data-purity-attribution-gene={attribution.geneSymbol}>
                <td><b>{attribution.rank}. {attribution.geneSymbol}</b></td>
                <td className="mono-cell">{formatNumber(attribution.transformedExpression, 6)}</td>
                <td className="mono-cell">{formatSigned(attribution.localGradient, 6)}</td>
                <td className="mono-cell">{formatSigned(attribution.rawOutputContribution, 6)}</td>
                <td><span className={`state-badge ${attribution.rawOutputContribution > 0 ? "activated" : attribution.rawOutputContribution < 0 ? "suppressed" : "neutral"}`}>{humanize(attribution.direction)}</span></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
        <div className="zero-fill-explainer" style={{ marginTop: 12 }}>
          <article><b>All-gene contribution</b><strong>{formatSigned(explanation.allGeneContributionSum, 6)}</strong><p>Sum across all {GBM_RNA_PURITY_MODEL_FEATURE_COUNT.toLocaleString("en-US")} transformed model features.</p></article>
          <article><b>Active-path bias</b><strong>{formatSigned(explanation.activePathBiasContribution, 6)}</strong><p>Bias contribution along the exact active ReLU paths.</p></article>
          <article><b>Reconstructed raw output</b><strong>{formatSigned(explanation.reconstructedRawOutput, 6)}</strong><p>Contribution plus active-path bias before clipping.</p></article>
          <article className={explanation.clippingChangesLocalInterpretation ? "warning" : undefined}><b>Reconstruction error</b><strong>{formatNumber(explanation.reconstructionAbsoluteError, 8)}</strong><p>{explanation.clippingChangesLocalInterpretation ? "Clipping changes interpretation at the displayed output boundary." : "The displayed fraction does not alter this local interpretation through clipping."}</p></article>
        </div>
      </>}
    </section>
  );
}

function RuntimePanel({ evidence }: { evidence: GbmRnaPurityEvidence }) {
  const diagnostics = evidence.diagnostics;
  return (
    <section className="result-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">DETERMINISTIC NUMPY FORWARD PASS</p><h3>Network activation trace</h3></div>
        <span className="boundary-chip">dropout off · float32 inference</span>
      </div>
      <div className="zero-fill-explainer">
        <article><b>First hidden layer</b><strong>{diagnostics.firstLayerActiveNodes === null ? "—" : `${diagnostics.firstLayerActiveNodes} / 32`}</strong><p>Positive ReLU activations in the released first hidden layer.</p></article>
        <article><b>Second hidden layer</b><strong>{diagnostics.secondLayerActiveNodes === null ? "—" : `${diagnostics.secondLayerActiveNodes} / 16`}</strong><p>Positive ReLU activations in the released second hidden layer.</p></article>
        <article><b>Transformed input max</b><strong>{formatNumber(diagnostics.transformedInputMaximum, 6)}</strong><p>After source-order RPK share × 10,000 and log2(+1) preprocessing.</p></article>
        <article className={diagnostics.finiteInference ? undefined : "warning"}><b>Finite inference</b><strong>{diagnostics.finiteInference ? "yes" : "no"}</strong><p>{diagnostics.inferenceDtype} · activation pattern {shortDigest(diagnostics.activationPatternDigest)}</p></article>
      </div>
    </section>
  );
}

function UncertaintyAndScopePanel({ evidence }: { evidence: GbmRnaPurityEvidence }) {
  return (
    <section className="result-panel limitations-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">UNCERTAINTY / INTENDED USE</p><h3>No fabricated calibrated interval</h3></div>
        <span className="support-badge limited">{humanize(evidence.uncertaintyStatus)}</span>
      </div>
      <div className="zero-fill-notice">
        <b>Single fitted model</b>
        <span>{evidence.uncertaintyReason}</span>
      </div>
      <p>This lane is limited to research estimation of one malignant-cell fraction from primary IDH-wildtype glioblastoma bulk RNA-seq raw counts. It does not estimate immune or stromal composition, diagnose disease, predict outcome or response, or recommend treatment.</p>
      {evidence.abstentionReasons.length > 0 && <ul>{evidence.abstentionReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>}
    </section>
  );
}

function ProvenancePanel({ evidence }: { evidence: GbmRnaPurityEvidence }) {
  const provenance = evidence.provenance;
  const repository = provenance ? textAt(provenance, ["source_repository"]) : "";
  return (
    <section className="result-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">PINNED PUBLISHED SOURCE</p><h3>GBMPurity provenance</h3></div>
        <span className="boundary-chip">MIT model code · CC-BY-4.0 article</span>
      </div>
      {!provenance ? <p className="panel-empty">No model provenance was returned.</p> : (
        <div className="mechanism-list">
          <article><div><b>Source repository</b><span>{textAt(provenance, ["source_license"], "license not reported")}</span></div><strong>{repository || "not reported"}</strong><small>commit {textAt(provenance, ["source_commit"], "not reported")}</small></article>
          <article><div><b>Released PyTorch model</b><span>exact source lock</span></div><strong><code>{shortDigest(textAt(provenance, ["source_model_sha256"]))}</code></strong><small>gene lengths {shortDigest(textAt(provenance, ["source_gene_lengths_sha256"]))}</small></article>
          <article><div><b>Deterministic JSON conversion</b><span>no retraining</span></div><strong><code>{shortDigest(textAt(provenance, ["converted_artifact_digest"]))}</code></strong><small>file {shortDigest(textAt(provenance, ["converted_artifact_file_sha256"]))} · {textAt(provenance, ["transformation_notice"], "Transformation notice not reported.")}</small></article>
          <article><div><b>Runtime tensors / feature order</b><span>independent admission locks</span></div><strong><code>{shortDigest(textAt(provenance, ["weight_tensor_digest"]))}</code></strong><small>5,829-gene order {shortDigest(textAt(provenance, ["feature_order_digest"]))}</small></article>
          <article><div><b>Source article</b><span>{textAt(provenance, ["article_license"], "license not reported")}</span></div><strong>doi:{textAt(provenance, ["article_doi"], "not reported")}</strong><small>Published model estimate only; this adaptation is not upstream endorsement.</small></article>
        </div>
      )}
    </section>
  );
}

export function GbmRnaPurityResultPanels({ evidence }: { evidence: GbmRnaPurityEvidence }) {
  const estimate = evidence.estimate;
  return (
    <div className="panel-stack">
      <div className="summary-grid">
        <article><span>ESTIMATED MALIGNANT FRACTION</span><b>{fractionLabel(estimate?.malignantCellFraction ?? null)}</b><small>published GBMPurity model output</small></article>
        <article><span>RAW NETWORK OUTPUT</span><b>{formatSigned(estimate?.rawUnclippedOutput ?? null, 6)}</b><small>before output clipping</small></article>
        <article><span>CLIPPING</span><b>{estimate ? humanize(estimate.clippingState) : "not applicable"}</b><small>{estimate?.clippingState === "none" ? "raw and displayed estimates agree" : "displayed output is bounded to [0, 1]"}</small></article>
        <article><span>MODEL SUPPORT</span><b>{evidence.support}</b><small>{fractionLabel(evidence.coverage.coverageFraction)} exact feature overlap</small></article>
      </div>
      <section className="result-panel">
        <div className="panel-title-row">
          <div><p className="eyebrow">PUBLISHED GBMPURITY OUTPUT</p><h3>Estimated malignant-cell fraction</h3></div>
          <span className={`support-badge ${evidence.support}`}>{evidence.support}</span>
        </div>
        <div className="zero-fill-notice">
          <b>One bounded estimate</b>
          <span>This is the released primary IDH-wildtype GBM bulk-RNA model&apos;s numerical estimate—not histologic purity, a clinical truth label, or a decomposition of non-malignant cells.</span>
        </div>
        <strong style={{ display: "block", color: "var(--ink)", fontFamily: "monospace", fontSize: 38, fontWeight: 400 }}>{fractionLabel(estimate?.malignantCellFraction ?? null)}</strong>
        <PurityFractionMark value={estimate?.malignantCellFraction ?? null} />
        {evidence.abstentionReasons[0] && <p className="warning-copy" style={{ marginTop: 12 }}>{evidence.abstentionReasons[0]}</p>}
      </section>
      <CoveragePanel evidence={evidence} />
      <RuntimePanel evidence={evidence} />
      <AttributionPanel evidence={evidence} />
      <UncertaintyAndScopePanel evidence={evidence} />
      <ProvenancePanel evidence={evidence} />
    </div>
  );
}

export function GbmRnaPurityEvidencePanel({
  request,
  evidence,
}: {
  request: JsonObject;
  evidence: GbmRnaPurityEvidence;
}) {
  const stats = gbmRnaPurityRequestStats(request);
  const context = objectAt(request, ["context"]);
  return (
    <div className="panel-stack">
      <section className="result-panel zero-fill-panel">
        <div className="panel-title-row">
          <div><p className="eyebrow">EXECUTED RAW-COUNT CONTRACT</p><h3>Primary IDH-wildtype GBM bulk-RNA input</h3></div>
          <span className="count-chip">{stats.suppliedGenes.toLocaleString("en-US")}</span>
        </div>
        <div className="zero-fill-explainer">
          <article><b>Supplied genes</b><strong>{stats.suppliedGenes.toLocaleString("en-US")}</strong><p>{stats.uniqueGenes.toLocaleString("en-US")} unique exact symbols; duplicate counts are never summed.</p></article>
          <article><b>Nonzero raw counts</b><strong>{stats.nonzeroGenes.toLocaleString("en-US")}</strong><p>Unnormalized nonnegative count values declared by the caller.</p></article>
          <article><b>Recognized model genes</b><strong>{evidence.coverage.recognizedModelGeneCount.toLocaleString("en-US")}</strong><p>{fractionLabel(evidence.coverage.coverageFraction)} of the frozen source feature order.</p></article>
          <article><b>Counts provenance</b><strong><code>{shortDigest(textAt(request, ["counts_provenance_digest"]))}</code></strong><p>Caller-supplied receipt; no request or result is persisted by this service.</p></article>
        </div>
      </section>
      <section className="result-panel">
        <div className="panel-title-row">
          <div><p className="eyebrow">CALLER ATTESTATION</p><h3>Frozen assay and disease scope</h3></div>
          <span className="boundary-chip">exact literals required</span>
        </div>
        <div className="mechanism-list">
          <article><div><b>Disease context</b><span>intended population</span></div><strong>{context ? humanize(textAt(context, ["disease_context"], "not reported")) : "not reported"}</strong><small>No inference outside primary IDH-wildtype glioblastoma is supported.</small></article>
          <article><div><b>Specimen / assay</b><span>{context ? textAt(context, ["organism"], "not reported") : "not reported"}</span></div><strong>{context ? `${humanize(textAt(context, ["specimen"]))} · ${humanize(textAt(context, ["assay"]))}` : "not reported"}</strong><small>Raw nonnegative gene counts; batch-corrected values are explicitly out of contract.</small></article>
          <article><div><b>Missing-gene policy</b><span>caller authorized</span></div><strong>80% gate → source-parity zero-fill</strong><small>Missing values are not silently treated as evidence of decreased expression.</small></article>
          <article><div><b>Safety class</b><span>attested</span></div><strong>research use only</strong><small>No diagnosis, prognosis, treatment response, clinical classification, or automated action.</small></article>
        </div>
      </section>
      <CoveragePanel evidence={evidence} />
      <RuntimePanel evidence={evidence} />
      <ProvenancePanel evidence={evidence} />
    </div>
  );
}
