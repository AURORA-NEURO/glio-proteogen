"use client";

import type {
  ReactomeAblation,
  ReactomeConditionalTransition,
  ReactomeEvaluationSummary,
  ReactomePathwayConcordance,
} from "@/lib/longitudinal-gbm-reactome-transition";
import {
  LONGITUDINAL_GBM_REACTOME_PI3K_ID,
  reactomeEstimatedPathwayCount,
  reactomePathwayCount,
  reactomeSupportedPathwayCount,
  reactomeTransitionRequestStats,
} from "@/lib/longitudinal-gbm-reactome-transition";
import {
  arrayAt,
  formatNumber,
  formatSigned,
  isJsonObject,
  numberAt,
  objectAt,
  shortDigest,
  textAt,
  type JsonObject,
} from "@/lib/research-state";

type ResultsProps = {
  request: JsonObject;
  transitions: ReactomeConditionalTransition[];
  evaluation: ReactomeEvaluationSummary | null;
};

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function percent(value: number | null, digits = 1): string {
  return value === null ? "—" : `${formatNumber(value * 100, digits)}%`;
}

function interval(pathway: ReactomePathwayConcordance): string {
  return pathway.lower === null || pathway.upper === null
    ? "not estimable"
    : `[${formatNumber(pathway.lower)}, ${formatNumber(pathway.upper)}]`;
}

function classificationTone(classification: string): string {
  if (classification.includes("recurrence_aligned")) return "recurrence";
  if (classification.includes("primary_aligned")) return "primary";
  if (classification.includes("stable")) return "stable";
  return "indeterminate";
}

function ClassificationBadge({ value }: { value: string }) {
  return (
    <span className={`reactome-classification ${classificationTone(value)}`}>
      {humanize(value)}
    </span>
  );
}

function ScoreIntervalMark({ pathway }: { pathway: ReactomePathwayConcordance }) {
  const bound = (value: number) => Math.max(-2, Math.min(2, value));
  const score = bound(pathway.score ?? 0);
  const lower = bound(pathway.lower ?? score);
  const upper = bound(pathway.upper ?? score);
  return (
    <div
      className="reactome-score-mark"
      aria-label={`${pathway.pathwayName} conditional concordance ${formatSigned(pathway.score)}, interval ${interval(pathway)}`}
    >
      <span className="reactome-neutral-band" />
      <span className="reactome-score-zero" />
      {pathway.lower !== null && pathway.upper !== null && (
        <span
          className="reactome-score-interval"
          style={{
            left: `${50 + lower * 25}%`,
            width: `${Math.max(0, upper - lower) * 25}%`,
          }}
        />
      )}
      {pathway.score !== null && <i style={{ left: `${50 + score * 25}%` }} />}
    </div>
  );
}

function GlobalTimeline({ transitions }: { transitions: ReactomeConditionalTransition[] }) {
  return (
    <section className="result-panel reactome-global-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">GLOBAL RECURRENCE COORDINATE</p><h3>Source-cohort concordance before pathway conditioning</h3></div>
        <span className="boundary-chip">90% interval-classified · not patient evolution</span>
      </div>
      <div className="reactome-global-grid">
        {transitions.map((transition) => (
          <article key={transition.id} data-reactome-global-transition={transition.id}>
            <header>
              <div><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{formatNumber(transition.durationDays, 0)} days · {transition.id}</small></div>
              <span className={`support-badge ${transition.global.support}`}>{transition.global.support}</span>
            </header>
            <strong>{formatSigned(transition.global.score)}</strong>
            <ClassificationBadge value={transition.global.classification} />
            <dl>
              <div><dt>90% interval</dt><dd>[{formatNumber(transition.global.lower)}, {formatNumber(transition.global.upper)}]</dd></div>
              <div><dt>active genes</dt><dd>{transition.global.activeGenes.toLocaleString("en-US")}</dd></div>
              <div><dt>coefficient mass</dt><dd>{percent(transition.global.coefficientMassCoverage)}</dd></div>
              <div><dt>effective sample</dt><dd>{formatNumber(transition.global.effectiveSampleSize, 1)}</dd></div>
            </dl>
            {transition.global.reasons[0] && <small className="warning-copy">{transition.global.reasons[0]}</small>}
          </article>
        ))}
      </div>
    </section>
  );
}

function PathwayIntervalMatrix({ transitions }: { transitions: ReactomeConditionalTransition[] }) {
  const pathways = transitions[0]?.pathways ?? [];
  return (
    <section className="result-panel reactome-matrix-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">FIXED REACTOME V97 PANEL</p><h3>Ten-pathway conditional transition interval matrix</h3></div>
        <span className="boundary-chip">−0.25 ↔ +0.25 is the stable interval band</span>
      </div>
      <div className="zero-fill-notice reactome-pi3k-notice">
        <b>PI3K/AKT overlap boundary</b>
        <span>The Reactome source title contains “activation,” but the displayed number is only a conditional source-cohort concordance coordinate. PI3K/AKT has zero unique fitted panel members, so its estimate is always conspicuously LIMITED and overlap-confounded.</span>
      </div>
      <div className="state-table-wrap">
        <table className="state-table reactome-matrix" aria-label="Reactome pathway transition interval matrix">
          <thead>
            <tr>
              <th>Reactome pathway</th>
              {transitions.map((transition) => (
                <th key={transition.id}>{transition.fromTimePointId} → {transition.toTimePointId}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {pathways.map((pathway) => (
              <tr
                key={pathway.reactomeId}
                className={pathway.reactomeId === LONGITUDINAL_GBM_REACTOME_PI3K_ID ? "overlap-confounded" : undefined}
                data-reactome-pathway-row={pathway.reactomeId}
              >
                <td>
                  <b>{pathway.pathwayName}</b>
                  <small>{pathway.reactomeId} · locked source pathway title</small>
                  {pathway.reactomeId === LONGITUDINAL_GBM_REACTOME_PI3K_ID && <span className="reactome-overlap-badge">LIMITED · 0 unique fitted members</span>}
                </td>
                {transitions.map((transition) => {
                  const value = transition.pathways.find((candidate) => candidate.reactomeId === pathway.reactomeId);
                  return (
                    <td key={`${transition.id}-${pathway.reactomeId}`} data-reactome-matrix-cell={`${transition.id}:${pathway.reactomeId}`}>
                      {value ? <>
                        <div className="reactome-score-heading"><b>{formatSigned(value.score)}</b><span className={`support-badge ${value.support}`}>{value.support}</span></div>
                        <ScoreIntervalMark pathway={value} />
                        <small>{interval(value)}</small>
                        <ClassificationBadge value={value.classification} />
                      </> : <span>not returned</span>}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function CoordinateDecomposition({ transitions }: { transitions: ReactomeConditionalTransition[] }) {
  return (
    <section className="result-panel state-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">UNADJUSTED − GLOBAL = CONDITIONAL</p><h3>Coordinate decomposition and request reconstruction</h3></div>
        <span className="boundary-chip">coordinates · not pathway activity or flux</span>
      </div>
      <div className="state-table-wrap">
        <table className="state-table reactome-coordinate-table">
          <thead><tr><th>Transition / pathway</th><th>Unadjusted</th><th>Global adjustment</th><th>Conditional</th><th>Request reconstruction</th><th>Support</th></tr></thead>
          <tbody>{transitions.flatMap((transition) => transition.pathways.map((pathway) => (
            <tr key={`${transition.id}-${pathway.reactomeId}`} data-reactome-coordinate={pathway.reactomeId}>
              <td><b>{pathway.pathwayName}</b><small>{transition.fromTimePointId} → {transition.toTimePointId} · {pathway.reactomeId}</small></td>
              <td className="mono-cell">{formatSigned(pathway.unadjustedCoordinate)}<small>raw pathway membership coordinate</small></td>
              <td className="mono-cell">{formatSigned(pathway.globalAdjustment)}<small>subtracted from unadjusted</small></td>
              <td className="mono-cell"><b>{formatSigned(pathway.score)}</b><small>{interval(pathway)}</small></td>
              <td>
                <b>{pathway.reconstructionEvaluableFoldCount > 0
                  ? `improved ${pathway.reconstructionImprovedFoldCount} of ${pathway.reconstructionEvaluableFoldCount} evaluable (five planned)`
                  : `improved ${pathway.reconstructionImprovedFoldCount} of 0 evaluable (five planned)`}</b>
                <small>median relative gain {percent(pathway.reconstructionMedianRelativeGain, 2)} · request-specific stability check, not validation</small>
              </td>
              <td><span className={`support-badge ${pathway.support}`}>{pathway.support}</span>{pathway.reasons[0] && <small className="warning-copy">{pathway.reasons[0]}</small>}</td>
            </tr>
          )))}</tbody>
        </table>
      </div>
    </section>
  );
}

function CoverageAndUncertainty({ transitions }: { transitions: ReactomeConditionalTransition[] }) {
  return (
    <section className="result-panel reactome-coverage-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">EVIDENCE CONSERVATION / UNCERTAINTY</p><h3>Coverage, censoring, and measurement × fitted-model sensitivity</h3></div>
        <span className="boundary-chip">missing / unsupported never become negative evidence</span>
      </div>
      <div className="reactome-coverage-grid">
        {transitions.flatMap((transition) => transition.pathways.map((pathway) => (
          <article key={`${transition.id}-${pathway.reactomeId}`} data-reactome-coverage={pathway.reactomeId}>
            <header><div><b>{pathway.pathwayName}</b><small>{transition.fromTimePointId} → {transition.toTimePointId}</small></div><span className={`support-badge ${pathway.support}`}>{pathway.support}</span></header>
            <dl>
              <div><dt>active / fitted</dt><dd>{pathway.activeFeatureCount} / {pathway.fittedFeatureCount}</dd></div>
              <div><dt>observed / censored</dt><dd>{pathway.observedCount} / {pathway.leftCensoredCount}</dd></div>
              <div><dt>coefficient mass</dt><dd>{percent(pathway.coefficientMassCoverage)}</dd></div>
              <div><dt>effective sample</dt><dd>{formatNumber(pathway.effectiveSampleSize, 1)}</dd></div>
              <div><dt>unique active / mass</dt><dd>{pathway.uniqueActiveGeneCount} / {percent(pathway.uniqueCoefficientMass)}</dd></div>
              <div><dt>stability / discordance</dt><dd>{percent(pathway.stability)} / {percent(pathway.discordance)}</dd></div>
              <div><dt>measurement SE</dt><dd>{formatNumber(pathway.uncertainty.measurementStandardError)}</dd></div>
              <div><dt>fitted-model SE</dt><dd>{formatNumber(pathway.uncertainty.fittedModelStandardError)}</dd></div>
              <div><dt>covariance</dt><dd>{formatSigned(pathway.uncertainty.measurementModelCovariance, 6)}</dd></div>
              <div><dt>combined SE</dt><dd>{formatNumber(pathway.uncertainty.combinedStandardError)}</dd></div>
            </dl>
            <small>{pathway.uncertainty.bootstrapReplicates} deterministic bootstrap replicates · variance closure residual {formatNumber(pathway.uncertainty.varianceClosureResidual, 6)}</small>
          </article>
        ))) }
      </div>
    </section>
  );
}

function ContributionPanels({ transitions }: { transitions: ReactomeConditionalTransition[] }) {
  return (
    <section className="result-panel reactome-contribution-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">OBSERVED-GENE NUMERICAL DECOMPOSITION</p><h3>Top conditional contributions</h3></div>
        <span className="boundary-chip">local numerical terms · never causal drivers</span>
      </div>
      <div className="zero-fill-notice">
        <b>Contribution boundary</b>
        <span>These terms explain the executed coordinate using observed gene deltas and frozen loadings. They are not causal genes, intervention effects, biomarkers, or treatment targets.</span>
      </div>
      <div className="longitudinal-explanation-grid reactome-contribution-grid">
        {transitions.flatMap((transition) => transition.pathways.map((pathway) => (
          <article key={`${transition.id}-${pathway.reactomeId}`} data-reactome-contributions={pathway.reactomeId}>
            <header><div><b>{pathway.pathwayName}</b><small>{transition.fromTimePointId} → {transition.toTimePointId} · {pathway.support}</small></div><strong>{formatSigned(pathway.score)}</strong></header>
            <div className="longitudinal-driver-list">
              {pathway.contributions.length ? pathway.contributions.slice(0, 5).map((contribution) => (
                <div key={`${contribution.geneSymbol}-${contribution.fromObservationId}-${contribution.toObservationId}`}>
                  <b>{contribution.geneSymbol}</b><span>{formatSigned(contribution.conditionalContribution)}</span>
                  <small>Δz {formatSigned(contribution.standardizedDelta)} · unadjusted {formatSigned(contribution.unadjustedContribution)} − global {formatSigned(contribution.globalAdjustmentContribution)} · pathway loading {formatSigned(contribution.pathwayLoading)} · reliability {formatNumber(contribution.reliabilityWeight)}</small>
                </div>
              )) : <p>No ranked numerical contribution was returned for this pathway.</p>}
            </div>
          </article>
        ))) }
      </div>
    </section>
  );
}

const ABLATION_LABELS: Record<ReactomeAblation["kind"], string> = {
  global_axis: "global-axis removal",
  source_processing: "source-processing sensitivity",
  degree_normalization: "topology / degree normalization",
  unique_members: "unique-member attribution",
  leave_pathway_out: "leave-pathway-out",
  overlapping_pathway: "overlap removal",
  top_contribution: "measurement / top-contribution omission",
};

function AblationPanels({ transitions }: { transitions: ReactomeConditionalTransition[] }) {
  return (
    <section className="result-panel reactome-ablation-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">SOURCE / MEASUREMENT / TOPOLOGY / OVERLAP / LEAVE-PATH / UNIQUE</p><h3>Conditional-coordinate sensitivity ledger</h3></div>
        <span className="boundary-chip">recomputed point sensitivity · support retained</span>
      </div>
      <div className="longitudinal-explanation-grid reactome-ablation-grid">
        {transitions.flatMap((transition) => transition.pathways.map((pathway) => (
          <article key={`${transition.id}-${pathway.reactomeId}`} data-reactome-ablations={pathway.reactomeId}>
            <header><div><b>{pathway.pathwayName}</b><small>{pathway.reactomeId} · {transition.id}</small></div><span className={`support-badge ${pathway.support}`}>{pathway.support}</span></header>
            <div className="longitudinal-ablation-list">
              {pathway.ablations.length ? pathway.ablations.map((ablation, index) => (
                <div key={`${ablation.kind}-${ablation.componentId}-${index}`} data-reactome-ablation-kind={ablation.kind}>
                  <b>{ABLATION_LABELS[ablation.kind]}</b><span>Δ {formatSigned(ablation.scoreDelta)}</span>
                  <small>{ablation.componentId} · score without {formatSigned(ablation.scoreWithout)} · {humanize(ablation.classificationWithout)} · {ablation.support} · removed {ablation.removedFeatureCount}{ablation.reason ? ` · ${ablation.reason}` : ""}</small>
                </div>
              )) : <p>No estimable ablation record was returned.</p>}
            </div>
          </article>
        ))) }
      </div>
    </section>
  );
}

export function ReactomeLockedEvaluationPanel({ evaluation }: { evaluation: ReactomeEvaluationSummary | null }) {
  return (
    <section className="result-panel reactome-evaluation-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">LOCKED SAME-COHORT EVALUATION</p><h3>Evidence ceiling and reconstruction audit</h3></div>
        <span className="support-badge limited">not external validation</span>
      </div>
      {!evaluation ? <p className="panel-empty">The locked evaluation summary was not returned in the profile.</p> : <>
        <div className="zero-fill-notice">
          <b>Modest collective evidence</b>
          <span>{evaluation.interpretation}. All ten cohort leave-pathway-out q05–q95 intervals cross zero; no individual pathway attribution is validated.</span>
        </div>
        <div className="zero-fill-explainer reactome-evaluation-grid">
          <article><b>Patient-grouped design</b><strong>{evaluation.patientCount}</strong><p>{evaluation.evaluationCount} held-patient × held-gene evaluations. {evaluation.protocol}.</p></article>
          <article><b>Median standardized MAE</b><strong>{formatNumber(evaluation.jointMedianMae, 4)}</strong><p>zero {formatNumber(evaluation.zeroPredictionMedianMae, 4)} · global only {formatNumber(evaluation.globalOnlyMedianMae, 4)} · joint conditional dictionary {formatNumber(evaluation.jointMedianMae, 4)}.</p></article>
          <article><b>Median relative gain</b><strong>{percent(evaluation.medianRelativeMaeImprovement, 2)}</strong><p>{percent(evaluation.evaluationImprovedFraction)} of evaluations improved; patient-cluster median {percent(evaluation.patientClusterMedianImprovement, 2)}.</p></article>
          <article><b>Patient-cluster 90% interval</b><strong>{percent(evaluation.patientClusterInterval[0], 2)} – {percent(evaluation.patientClusterInterval[1], 2)}</strong><p>{evaluation.patientClusterBootstrapReplicates.toLocaleString("en-US")} descriptive resamples · same cohort only.</p></article>
          <article><b>Reference condition</b><strong>{formatNumber(evaluation.conditionNumber, 3)}</strong><p>minimum held-fold loading cosine {formatNumber(evaluation.minimumOuterLoadingCosine, 4)}.</p></article>
          <article className="warning"><b>Individual pathway ceiling</b><strong>{evaluation.allLeavePathwayIntervalsCrossZero ? "all 10 cross zero" : "review profile"}</strong><p>{evaluation.allPrimaryFitsConverged ? "Primary solver fits converged." : "One or more primary fits did not converge."} This is not external validation.</p></article>
        </div>
        <p className="reactome-validation-scope">{evaluation.validationScope}</p>
      </>}
    </section>
  );
}

export function ReactomeTransitionResultPanels({ request, transitions, evaluation }: ResultsProps) {
  const total = reactomePathwayCount(transitions);
  const supported = reactomeSupportedPathwayCount(transitions);
  const estimated = reactomeEstimatedPathwayCount(transitions);
  const overlapConfounded = transitions.reduce(
    (count, transition) => count + transition.pathways.filter((pathway) => pathway.overlapConfounded).length,
    0,
  );
  const meanCoverage = total
    ? transitions.reduce((sum, transition) => sum + transition.pathways.reduce((inner, pathway) => inner + pathway.coefficientMassCoverage, 0), 0) / total
    : null;
  return (
    <div className="panel-stack">
      <div className="summary-grid">
        <article><span>FULL SUPPORT</span><b>{supported} / {total}</b><small>{estimated} estimated conditional coordinates across {transitions.length} transition{transitions.length === 1 ? "" : "s"}</small></article>
        <article><span>MEAN COEFFICIENT MASS</span><b>{percent(meanCoverage)}</b><small>active fitted evidence; missing and unsupported remain excluded</small></article>
        <article><span>GLOBAL COORDINATES</span><b>{transitions.filter((transition) => transition.global.score !== null).length}</b><small>source-cohort recurrence concordance before pathway conditioning</small></article>
        <article><span>OVERLAP-CONFOUNDED</span><b className="warn">{overlapConfounded}</b><small>PI3K/AKT is always LIMITED in each transition</small></article>
      </div>
      <GlobalTimeline transitions={transitions} />
      <PathwayIntervalMatrix transitions={transitions} />
      <CoordinateDecomposition transitions={transitions} />
      <CoverageAndUncertainty transitions={transitions} />
      <ContributionPanels transitions={transitions} />
      <AblationPanels transitions={transitions} />
      <ReactomeLockedEvaluationPanel evaluation={evaluation} />
    </div>
  );
}

export function ReactomeTransitionEvidencePanel({
  request,
  transitions,
  profile,
  provenance,
}: {
  request: JsonObject;
  transitions: ReactomeConditionalTransition[];
  profile: JsonObject | null;
  provenance: JsonObject | null;
}) {
  const stats = reactomeTransitionRequestStats(request);
  const points = arrayAt(request, ["time_points"]);
  const rows = points.flatMap((point, pointIndex) => !isJsonObject(point)
    ? []
    : arrayAt(point, ["observations"]).flatMap((observation) => isJsonObject(observation)
      ? [{ pointId: textAt(point, ["time_point_id"], `T${pointIndex + 1}`), observation }]
      : []));
  const visibleRows = rows.slice(0, 256);
  const assay = objectAt(request, ["assay_compatibility"]);
  const reference = objectAt(request, ["normalization_reference"]);
  const counts = profile ? objectAt(profile, ["counts"]) : null;
  const digests = profile ? objectAt(profile, ["digests"]) : null;
  return (
    <div className="panel-stack">
      <section className="result-panel zero-fill-panel">
        <div className="panel-title-row"><div><p className="eyebrow">INTERPRETATION BOUNDARY</p><h3>KNCC protein-transition evidence on a locked Reactome panel</h3></div><span className="boundary-chip">conditional concordance · not pathway activity, flux, or clinical prediction</span></div>
        <div className="zero-fill-explainer">
          <article><b>Source cohort</b><strong>{counts ? numberAt(counts, ["source_patient_count"]) ?? 104 : 104}</strong><p>Strict PDC000514 paired-patient source groups; no patient matrices or identifiers are redistributed.</p></article>
          <article><b>Ordered request</b><strong>{stats.timePoints}</strong><p>{stats.transitions} consecutive transition{stats.transitions === 1 ? "" : "s"} · {stats.genes.toLocaleString("en-US")} distinct exact gene symbols.</p></article>
          <article><b>Active observations</b><strong>{stats.active.toLocaleString("en-US")}</strong><p>Observed plus left-censored values. Missing and unsupported records remain non-numeric.</p></article>
          <article className="warning"><b>Fixed pathway panel</b><strong>10</strong><p>Reactome V97 source membership selected before outcome fitting; PI3K/AKT remains overlap-confounded.</p></article>
        </div>
      </section>
      <section className="result-panel">
        <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h3>Ordered protein evidence ledger</h3></div><span className="count-chip">{rows.length}</span></div>
        {rows.length > visibleRows.length && <p className="longitudinal-ledger-note">Showing the first {visibleRows.length} of {rows.length} observations; the downloadable request receipt retains every row.</p>}
        <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Time point</th><th>Observation</th><th>Gene</th><th>State</th><th>Log abundance ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
          {visibleRows.map(({ pointId, observation }, index) => <tr key={textAt(observation, ["observation_id"], String(index))}>
            <td><b>{pointId}</b></td><td>{textAt(observation, ["observation_id"], `observation-${index + 1}`)}</td><td><b>{textAt(observation, ["gene_symbol"], "—")}</b></td><td><span className="evidence-state">{textAt(observation, ["state"], "—")}</span></td><td className="mono-cell">{formatNumber(numberAt(observation, ["log_abundance"]), 3)} ± {formatNumber(numberAt(observation, ["standard_error"]), 3)}</td><td className="mono-cell">{formatNumber(numberAt(observation, ["quality_weight"]))}</td><td><code>{shortDigest(textAt(observation, ["provenance_digest"]))}</code></td>
          </tr>)}
        </tbody></table></div>
      </section>
      <CoverageAndUncertainty transitions={transitions} />
      <section className="mechanism-grid">
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">INVARIANT PREPROCESSING</p><h3>Normalization reference</h3></div></div>{reference ? <pre>{JSON.stringify(reference, null, 2)}</pre> : <p className="panel-empty">No normalization reference was supplied.</p>}</section>
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">REQUIRED INPUT COMPATIBILITY</p><h3>Assay and quantification attestation</h3></div></div>{assay ? <pre>{JSON.stringify(assay, null, 2)}</pre> : <p className="panel-empty">No compatible assay attestation was supplied.</p>}</section>
      </section>
      <section className="result-panel reactome-provenance-panel">
        <div className="panel-title-row"><div><p className="eyebrow">CONTENT-BOUND SOURCE / FITTED ARTIFACT</p><h3>Reactome V97 and KNCC provenance</h3></div><span className="boundary-chip">public topology · transformed de-identified model</span></div>
        <div className="mechanism-list">
          <article><div><b>Source attribution</b><span>{provenance ? textAt(provenance, ["source_patient_count"], "104") : "104"} source patients</span></div><strong>{provenance ? textAt(provenance, ["source_attribution"], "not reported") : "not reported"}</strong><small>{provenance ? arrayAt(provenance, ["source_licenses"]).filter((value): value is string => typeof value === "string").join(" · ") : "licenses not reported"}</small></article>
          <article><div><b>Reactome source catalog</b><span>release 97 · 10 fixed pathways</span></div><strong><code>{shortDigest(digests ? textAt(digests, ["source_catalog_content_digest"]) : "")}</code></strong><small>membership {shortDigest(digests ? textAt(digests, ["pathway_membership_digest"]) : "")} · order {shortDigest(digests ? textAt(digests, ["pathway_order_digest"]) : "")}</small></article>
          <article><div><b>Fitted conditional model</b><span>global + 10 conditional coordinates</span></div><strong><code>{shortDigest(digests ? textAt(digests, ["fitted_content_digest"]) : "")}</code></strong><small>design {shortDigest(digests ? textAt(digests, ["reference_design_digest"]) : "")} · ensemble {shortDigest(digests ? textAt(digests, ["bootstrap_ensemble_digest"]) : "")}</small></article>
          <article><div><b>Executed computation</b><span>request-derived deterministic seed</span></div><strong><code>{shortDigest(provenance ? textAt(provenance, ["computational_digest"]) : "")}</code></strong><small>engine {shortDigest(provenance ? textAt(provenance, ["engine_semantic_digest"]) : "")} · NumPy {provenance ? textAt(provenance, ["numpy_version"], "not reported") : "not reported"}</small></article>
        </div>
        {provenance && <p className="reactome-transformation-notice">{textAt(provenance, ["source_transformation_notice"], "No transformation notice was returned.")}</p>}
      </section>
      <ContributionPanels transitions={transitions} />
      <AblationPanels transitions={transitions} />
    </div>
  );
}
