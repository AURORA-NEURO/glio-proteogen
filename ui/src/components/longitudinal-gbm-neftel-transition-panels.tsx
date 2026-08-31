"use client";

import type {
  NeftelAblation,
  NeftelConditionalTransition,
  NeftelEvaluationSummary,
  NeftelProgramConcordance,
} from "@/lib/longitudinal-gbm-neftel-transition";
import {
  neftelEstimatedProgramCount,
  neftelProgramCount,
  neftelSupportedProgramCount,
  neftelTransitionRequestStats,
} from "@/lib/longitudinal-gbm-neftel-transition";
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
  transitions: NeftelConditionalTransition[];
  evaluation: NeftelEvaluationSummary | null;
};

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function percent(value: number | null, digits = 1): string {
  return value === null ? "—" : `${formatNumber(value * 100, digits)}%`;
}

function interval(program: NeftelProgramConcordance): string {
  return program.lower === null || program.upper === null
    ? "not estimable"
    : `[${formatNumber(program.lower)}, ${formatNumber(program.upper)}]`;
}

function classificationTone(classification: string): string {
  if (classification.includes("later_timepoint_aligned")) return "recurrence";
  if (classification.includes("earlier_timepoint_aligned")) return "primary";
  if (classification.includes("stable")) return "stable";
  return "indeterminate";
}

function ClassificationBadge({ value }: { value: string }) {
  return (
    <span className={`reactome-classification neftel-classification ${classificationTone(value)}`}>
      {humanize(value)}
    </span>
  );
}

function ScoreIntervalMark({ program }: { program: NeftelProgramConcordance }) {
  const bound = (value: number) => Math.max(-2, Math.min(2, value));
  const score = bound(program.score ?? 0);
  const lower = bound(program.lower ?? score);
  const upper = bound(program.upper ?? score);
  return (
    <div
      className="reactome-score-mark neftel-score-mark"
      aria-label={`${program.programName} conditional concordance ${formatSigned(program.score)}, interval ${interval(program)}`}
    >
      <span className="reactome-neutral-band neftel-neutral-band" />
      <span className="reactome-score-zero neftel-score-zero" />
      {program.lower !== null && program.upper !== null && (
        <span
          className="reactome-score-interval neftel-score-interval"
          style={{
            left: `${50 + lower * 25}%`,
            width: `${Math.max(0, upper - lower) * 25}%`,
          }}
        />
      )}
      {program.score !== null && <i style={{ left: `${50 + score * 25}%` }} />}
    </div>
  );
}

function GlobalTimeline({ transitions }: { transitions: NeftelConditionalTransition[] }) {
  return (
    <section className="result-panel neftel-global-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">GLOBAL TRANSITION COORDINATE</p><h3>Source-cohort bulk-protein concordance before program conditioning</h3></div>
        <span className="boundary-chip">90% interval-classified · not patient evolution</span>
      </div>
      <div className="reactome-global-grid neftel-global-grid">
        {transitions.map((transition) => (
          <article key={transition.id} data-neftel-global-transition={transition.id}>
            <header>
              <div><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{formatNumber(transition.durationDays, 0)} days · {transition.id}</small></div>
              <span className={`support-badge ${transition.global.support}`}>{transition.global.support}</span>
            </header>
            <strong>{formatSigned(transition.global.score)}</strong>
            <ClassificationBadge value={transition.global.classification} />
            <dl>
              <div><dt>90% interval</dt><dd>[{formatNumber(transition.global.lower)}, {formatNumber(transition.global.upper)}]</dd></div>
              <div><dt>admitted active genes</dt><dd>{transition.global.admittedActiveGenes.toLocaleString("en-US")}</dd></div>
              <div><dt>informative genes</dt><dd>{transition.global.informativeActiveGenes.toLocaleString("en-US")}</dd></div>
              <div><dt>exact / binding censor</dt><dd>{transition.global.observedCount} / {transition.global.bindingLeftCensoredCount}</dd></div>
              <div><dt>all admitted censor</dt><dd>{transition.global.admittedLeftCensoredCount}</dd></div>
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

function ProgramIntervalMatrix({ transitions }: { transitions: NeftelConditionalTransition[] }) {
  const programs = transitions[0]?.programs ?? [];
  return (
    <section className="result-panel neftel-matrix-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">EXACT NEFTEL TABLE S2 PROGRAMS</p><h3>Eight-program conditional transition interval matrix</h3></div>
        <span className="boundary-chip">−0.25 ↔ +0.25 is the stable interval band</span>
      </div>
      <div className="zero-fill-notice neftel-pi3k-notice">
        <b>LIMITED fitted-dictionary boundary</b>
        <span>MES2, MES1, AC, OPC, NPC1, NPC2, G1/S, and G2/M are exact source identities. Their fitted coordinates did not beat the prespecified equal-membership baseline and must not be read as cell states, fractions, activation, or individually validated effects.</span>
      </div>
      <div className="state-table-wrap">
        <table className="state-table reactome-matrix neftel-matrix" aria-label="Neftel program transition interval matrix">
          <thead>
            <tr>
              <th>Neftel program</th>
              {transitions.map((transition) => (
                <th key={transition.id}>{transition.fromTimePointId} → {transition.toTimePointId}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {programs.map((program) => (
              <tr
                key={program.programId}
                data-neftel-program-row={program.programId}
              >
                <td>
                  <b>{program.programName}</b>
                  <small>{program.programId} · exact Neftel Table S2 module</small>
                  <span className="neftel-overlap-badge">LIMITED · no individual fitted effect established</span>
                </td>
                {transitions.map((transition) => {
                  const value = transition.programs.find((candidate) => candidate.programId === program.programId);
                  return (
                    <td key={`${transition.id}-${program.programId}`} data-neftel-matrix-cell={`${transition.id}:${program.programId}`}>
                      {value ? <>
                        <div className="reactome-score-heading neftel-score-heading"><b>{formatSigned(value.score)}</b><span className={`support-badge ${value.support}`}>{value.support}</span></div>
                        <ScoreIntervalMark program={value} />
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

function CoordinateDecomposition({ transitions }: { transitions: NeftelConditionalTransition[] }) {
  return (
    <section className="result-panel state-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">UNADJUSTED − GLOBAL = CONDITIONAL</p><h3>Coordinate decomposition and request reconstruction</h3></div>
        <span className="boundary-chip">coordinates · not program activity or flux</span>
      </div>
      <div className="state-table-wrap">
        <table className="state-table neftel-coordinate-table">
          <thead><tr><th>Transition / program</th><th>Unadjusted</th><th>Global adjustment</th><th>Conditional</th><th>Request reconstruction</th><th>Support</th></tr></thead>
          <tbody>{transitions.flatMap((transition) => transition.programs.map((program) => (
            <tr key={`${transition.id}-${program.programId}`} data-neftel-coordinate={program.programId}>
              <td><b>{program.programName}</b><small>{transition.fromTimePointId} → {transition.toTimePointId} · {program.programId}</small></td>
              <td className="mono-cell">{formatSigned(program.unadjustedCoordinate)}<small>raw program membership coordinate</small></td>
              <td className="mono-cell">{formatSigned(program.globalAdjustment)}<small>subtracted from unadjusted</small></td>
              <td className="mono-cell"><b>{formatSigned(program.score)}</b><small>{interval(program)}</small></td>
              <td>
                <b>{program.reconstructionEvaluableFoldCount > 0
                  ? `improved ${program.reconstructionImprovedFoldCount} of ${program.reconstructionEvaluableFoldCount} evaluable (five planned)`
                  : `improved ${program.reconstructionImprovedFoldCount} of 0 evaluable (five planned)`}</b>
                <small>median relative gain {percent(program.reconstructionMedianRelativeGain, 2)} · request-specific stability check, not validation</small>
              </td>
              <td><span className={`support-badge ${program.support}`}>{program.support}</span>{program.reasons[0] && <small className="warning-copy">{program.reasons[0]}</small>}</td>
            </tr>
          )))}</tbody>
        </table>
      </div>
    </section>
  );
}

function CoverageAndUncertainty({ transitions }: { transitions: NeftelConditionalTransition[] }) {
  return (
    <section className="result-panel neftel-coverage-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">EVIDENCE CONSERVATION / UNCERTAINTY</p><h3>Coverage, censoring, and measurement × fitted-model sensitivity</h3></div>
        <span className="boundary-chip">missing / unsupported never become negative evidence</span>
      </div>
      <div className="zero-fill-notice">
        <b>Admitted is not automatically informative</b>
        <span>Admitted active evidence contains exact observed pairs plus every reliable one-sided censor pair. Informative evidence contains the exact pairs plus only censor bounds that bind the fitted coordinate; non-binding censor bounds remain conserved in the admitted count without being scored as negative evidence.</span>
      </div>
      <div className="reactome-coverage-grid neftel-coverage-grid">
        {transitions.flatMap((transition) => transition.programs.map((program) => (
          <article key={`${transition.id}-${program.programId}`} data-neftel-coverage={program.programId}>
            <header><div><b>{program.programName}</b><small>{transition.fromTimePointId} → {transition.toTimePointId}</small></div><span className={`support-badge ${program.support}`}>{program.support}</span></header>
            <dl>
              <div><dt>admitted / fitted</dt><dd>{program.admittedActiveFeatureCount} / {program.fittedFeatureCount}</dd></div>
              <div><dt>informative / fitted</dt><dd>{program.activeFeatureCount} / {program.fittedFeatureCount}</dd></div>
              <div><dt>exact / binding censor</dt><dd>{program.observedCount} / {program.leftCensoredCount}</dd></div>
              <div><dt>all admitted censor</dt><dd>{program.admittedLeftCensoredCount}</dd></div>
              <div><dt>coefficient mass</dt><dd>{percent(program.coefficientMassCoverage)}</dd></div>
              <div><dt>effective sample</dt><dd>{formatNumber(program.effectiveSampleSize, 1)}</dd></div>
              <div><dt>unique active / mass</dt><dd>{program.uniqueActiveGeneCount} / {percent(program.uniqueCoefficientMass)}</dd></div>
              <div><dt>stability / discordance</dt><dd>{percent(program.stability)} / {percent(program.discordance)}</dd></div>
              <div><dt>measurement SE</dt><dd>{formatNumber(program.uncertainty.measurementStandardError)}</dd></div>
              <div><dt>fitted-model SE</dt><dd>{formatNumber(program.uncertainty.fittedModelStandardError)}</dd></div>
              <div><dt>covariance</dt><dd>{formatSigned(program.uncertainty.measurementModelCovariance, 6)}</dd></div>
              <div><dt>combined SE</dt><dd>{formatNumber(program.uncertainty.combinedStandardError)}</dd></div>
            </dl>
            <small>{program.uncertainty.bootstrapReplicates} deterministic bootstrap replicates · variance closure residual {formatNumber(program.uncertainty.varianceClosureResidual, 6)}</small>
          </article>
        ))) }
      </div>
    </section>
  );
}

function ContributionPanels({ transitions }: { transitions: NeftelConditionalTransition[] }) {
  return (
    <section className="result-panel neftel-contribution-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">OBSERVED-GENE NUMERICAL DECOMPOSITION</p><h3>Top conditional contributions</h3></div>
        <span className="boundary-chip">local numerical terms · never causal drivers</span>
      </div>
      <div className="zero-fill-notice">
        <b>Contribution boundary</b>
        <span>These terms explain the executed coordinate using observed gene deltas and frozen loadings. They are not causal genes, intervention effects, biomarkers, or treatment targets.</span>
      </div>
      <div className="longitudinal-explanation-grid reactome-contribution-grid neftel-contribution-grid">
        {transitions.flatMap((transition) => transition.programs.map((program) => (
          <article key={`${transition.id}-${program.programId}`} data-neftel-contributions={program.programId}>
            <header><div><b>{program.programName}</b><small>{transition.fromTimePointId} → {transition.toTimePointId} · {program.support}</small></div><strong>{formatSigned(program.score)}</strong></header>
            <div className="longitudinal-driver-list">
              {program.contributions.length ? program.contributions.slice(0, 5).map((contribution) => (
                <div key={`${contribution.geneSymbol}-${contribution.fromObservationId}-${contribution.toObservationId}`}>
                  <b>{contribution.geneSymbol}</b><span>{formatSigned(contribution.conditionalContribution)}</span>
                  <small>Δz {formatSigned(contribution.standardizedDelta)} · unadjusted {formatSigned(contribution.unadjustedContribution)} − global {formatSigned(contribution.globalAdjustmentContribution)} · program loading {formatSigned(contribution.programLoading)} · reliability {formatNumber(contribution.reliabilityWeight)}</small>
                </div>
              )) : <p>No ranked numerical contribution was returned for this program.</p>}
            </div>
          </article>
        ))) }
      </div>
    </section>
  );
}

const ABLATION_LABELS: Record<NeftelAblation["kind"], string> = {
  global_axis: "global-axis removal",
  source_processing: "source-processing sensitivity",
  degree_normalization: "topology / degree normalization",
  unique_members: "unique-member attribution",
  leave_program_out: "leave-program-out",
  overlapping_program: "overlap removal",
  top_contribution: "measurement / top-contribution omission",
};

function AblationPanels({ transitions }: { transitions: NeftelConditionalTransition[] }) {
  return (
    <section className="result-panel neftel-ablation-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">SOURCE / MEASUREMENT / TOPOLOGY / OVERLAP / LEAVE-PATH / UNIQUE</p><h3>Conditional-coordinate sensitivity ledger</h3></div>
        <span className="boundary-chip">recomputed point sensitivity · support retained</span>
      </div>
      <div className="longitudinal-explanation-grid reactome-ablation-grid neftel-ablation-grid">
        {transitions.flatMap((transition) => transition.programs.map((program) => (
          <article key={`${transition.id}-${program.programId}`} data-neftel-ablations={program.programId}>
            <header><div><b>{program.programName}</b><small>{program.programId} · {transition.id}</small></div><span className={`support-badge ${program.support}`}>{program.support}</span></header>
            <div className="longitudinal-ablation-list">
              {program.ablations.length ? program.ablations.map((ablation, index) => (
                <div key={`${ablation.kind}-${ablation.componentId}-${index}`} data-neftel-ablation-kind={ablation.kind}>
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

export function NeftelLockedEvaluationPanel({ evaluation }: { evaluation: NeftelEvaluationSummary | null }) {
  return (
    <section className="result-panel neftel-evaluation-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">LOCKED SAME-COHORT EVALUATION</p><h3>Evidence ceiling and reconstruction audit</h3></div>
        <span className="support-badge limited">not external validation</span>
      </div>
      {!evaluation ? <p className="panel-empty">The locked evaluation summary was not returned in the profile.</p> : <>
        <div className="zero-fill-notice">
          <b>Release gate failed against equal membership</b>
          <span>{evaluation.interpretation}. The fitted joint dictionary has higher held-marker MAE than equal membership, and all eight leave-program-out q05–q95 intervals cross zero. No individual fitted program effect is established.</span>
        </div>
        <div className="zero-fill-explainer reactome-evaluation-grid neftel-evaluation-grid">
          <article><b>Patient-grouped design</b><strong>{evaluation.patientCount}</strong><p>{evaluation.evaluationCount} held-patient × held-marker evaluations. {evaluation.protocol}.</p></article>
          <article className="warning"><b>Joint vs equal-membership MAE</b><strong>{formatNumber(evaluation.jointMedianMae, 4)} &gt; {formatNumber(evaluation.equalMembershipMedianMae, 4)}</strong><p>relative gain {percent(evaluation.jointVsEqualMedianGain, 2)} · only {percent(evaluation.jointVsEqualImprovedFraction)} of evaluations improved.</p></article>
          <article><b>Joint vs global-only gain</b><strong>{percent(evaluation.jointVsGlobalMedianGain, 2)}</strong><p>patient-cluster median {percent(evaluation.patientClusterJointVsGlobalGain, 2)}; descriptive same-cohort comparison only.</p></article>
          <article className="warning"><b>Joint vs equal patient interval</b><strong>{percent(evaluation.patientClusterJointVsEqualInterval[0], 2)} – {percent(evaluation.patientClusterJointVsEqualInterval[1], 2)}</strong><p>{evaluation.patientClusterBootstrapReplicates.toLocaleString("en-US")} descriptive resamples · point {percent(evaluation.patientClusterJointVsEqualGain, 2)}.</p></article>
          <article><b>Reference condition</b><strong>{formatNumber(evaluation.conditionNumber, 3)}</strong><p>minimum held-fold loading cosine {formatNumber(evaluation.minimumOuterLoadingCosine, 4)}.</p></article>
          <article className="warning"><b>Individual program ceiling</b><strong>{evaluation.allLeaveProgramIntervalsCrossZero ? "all 8 cross zero" : "review profile"}</strong><p>{evaluation.individuallySupportedProgramCount} individually supported · equal-baseline interval supports positive gain: {evaluation.jointVsEqualIntervalSupportsPositiveGain ? "yes" : "no"} · {evaluation.releaseGate.replaceAll("_", " ")}.</p></article>
        </div>
        <p className="reactome-validation-scope neftel-validation-scope">{evaluation.validationScope}</p>
      </>}
    </section>
  );
}

export function NeftelTransitionResultPanels({ request, transitions, evaluation }: ResultsProps) {
  const total = neftelProgramCount(transitions);
  const supported = neftelSupportedProgramCount(transitions);
  const estimated = neftelEstimatedProgramCount(transitions);
  const meanCoverage = total
    ? transitions.reduce((sum, transition) => sum + transition.programs.reduce((inner, program) => inner + program.coefficientMassCoverage, 0), 0) / total
    : null;
  return (
    <div className="panel-stack">
      <div className="summary-grid">
        <article><span>FULL SUPPORT</span><b>{supported} / {total}</b><small>{estimated} estimated conditional coordinates across {transitions.length} transition{transitions.length === 1 ? "" : "s"}</small></article>
        <article><span>MEAN COEFFICIENT MASS</span><b>{percent(meanCoverage)}</b><small>informative fitted evidence; admitted non-binding censor bounds remain conserved but unscored</small></article>
        <article><span>GLOBAL COORDINATES</span><b>{transitions.filter((transition) => transition.global.score !== null).length}</b><small>source-cohort bulk-protein concordance before program conditioning</small></article>
        <article><span>RELEASE GATE</span><b className="warn">LIMITED</b><small>fitted dictionary loses to equal-membership baseline</small></article>
      </div>
      <GlobalTimeline transitions={transitions} />
      <ProgramIntervalMatrix transitions={transitions} />
      <CoordinateDecomposition transitions={transitions} />
      <CoverageAndUncertainty transitions={transitions} />
      <ContributionPanels transitions={transitions} />
      <AblationPanels transitions={transitions} />
      <NeftelLockedEvaluationPanel evaluation={evaluation} />
    </div>
  );
}

export function NeftelTransitionEvidencePanel({
  request,
  transitions,
  profile,
  provenance,
}: {
  request: JsonObject;
  transitions: NeftelConditionalTransition[];
  profile: JsonObject | null;
  provenance: JsonObject | null;
}) {
  const stats = neftelTransitionRequestStats(request);
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
        <div className="panel-title-row"><div><p className="eyebrow">INTERPRETATION BOUNDARY</p><h3>KNCC protein-transition evidence on a locked Neftel panel</h3></div><span className="boundary-chip">conditional concordance · not program activity, flux, or clinical prediction</span></div>
        <div className="zero-fill-explainer">
          <article><b>Source cohort</b><strong>{counts ? numberAt(counts, ["source_patient_count"]) ?? 104 : 104}</strong><p>Strict PDC000514 paired-patient source groups; no patient matrices or identifiers are redistributed.</p></article>
          <article><b>Ordered request</b><strong>{stats.timePoints}</strong><p>{stats.transitions} consecutive transition{stats.transitions === 1 ? "" : "s"} · {stats.genes.toLocaleString("en-US")} distinct exact gene symbols.</p></article>
          <article><b>Submitted active observations</b><strong>{stats.active.toLocaleString("en-US")}</strong><p>Observed plus left-censored request rows. Transition-level panels separately report admitted pairs and the exact / binding-censor subset that is numerically informative.</p></article>
          <article className="warning"><b>Exact source programs</b><strong>8</strong><p>Neftel Table S2 identities projected onto the frozen KNCC protein axis; fitted weights failed the equal-membership release gate.</p></article>
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
      <section className="result-panel reactome-provenance-panel neftel-provenance-panel">
        <div className="panel-title-row"><div><p className="eyebrow">CONTENT-BOUND SOURCE / FITTED ARTIFACT</p><h3>Neftel Table S2, HGNC, and KNCC provenance</h3></div><span className="boundary-chip">exact source modules · transformed de-identified model</span></div>
        <div className="mechanism-list">
          <article><div><b>Source attribution</b><span>{provenance ? textAt(provenance, ["source_patient_count"], "104") : "104"} source patients</span></div><strong>{provenance ? textAt(provenance, ["source_attribution"], "not reported") : "not reported"}</strong><small>{provenance ? arrayAt(provenance, ["source_terms"]).filter((value): value is string => typeof value === "string").join(" · ") : "source terms not reported"}</small></article>
          <article><div><b>Neftel/HGNC source catalog</b><span>8 exact Table S2 programs</span></div><strong><code>{shortDigest(digests ? textAt(digests, ["source_catalog_content_digest"]) : "")}</code></strong><small>membership {shortDigest(digests ? textAt(digests, ["program_membership_digest"]) : "")} · order {shortDigest(digests ? textAt(digests, ["program_order_digest"]) : "")}</small></article>
          <article><div><b>Fitted conditional model</b><span>global + 8 conditional coordinates · LIMITED</span></div><strong><code>{shortDigest(digests ? textAt(digests, ["fitted_content_digest"]) : "")}</code></strong><small>design {shortDigest(digests ? textAt(digests, ["reference_design_digest"]) : "")} · ensemble {shortDigest(digests ? textAt(digests, ["bootstrap_ensemble_digest"]) : "")}</small></article>
          <article><div><b>Executed computation</b><span>request-derived deterministic seed</span></div><strong><code>{shortDigest(provenance ? textAt(provenance, ["computational_digest"]) : "")}</code></strong><small>engine {shortDigest(provenance ? textAt(provenance, ["engine_semantic_digest"]) : "")} · NumPy {provenance ? textAt(provenance, ["numpy_version"], "not reported") : "not reported"}</small></article>
        </div>
        {provenance && <p className="reactome-transformation-notice neftel-transformation-notice">{textAt(provenance, ["source_transformation_notice"], "No transformation notice was returned.")}</p>}
      </section>
      <ContributionPanels transitions={transitions} />
      <AblationPanels transitions={transitions} />
    </div>
  );
}
