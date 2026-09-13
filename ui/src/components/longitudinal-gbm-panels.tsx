"use client";

import {
  formatNumber,
  formatSigned,
  isJsonObject,
  numberAt,
  objectAt,
  shortDigest,
  textAt,
  type JsonObject,
} from "@/lib/research-state";
import type {
  LongitudinalTransition,
  PeltEvidence,
} from "@/lib/longitudinal-gbm";

type LongitudinalPanelsProps = {
  request: JsonObject;
  transitions: LongitudinalTransition[];
  pelt: PeltEvidence | null;
};

function intervalLabel(transition: LongitudinalTransition): string {
  if (transition.lower === null || transition.upper === null) return "not estimable";
  return `[${formatNumber(transition.lower)}, ${formatNumber(transition.upper)}]`;
}

function classificationLabel(value: string): string {
  return value.replaceAll("_", " ");
}

function TransitionScoreMark({ transition }: { transition: LongitudinalTransition }) {
  const score = transition.score ?? 0;
  const lower = transition.lower ?? score;
  const upper = transition.upper ?? score;
  const bounded = (value: number) => Math.max(-2, Math.min(2, value));
  return (
    <div
      className="longitudinal-score-mark"
      aria-label={`Transition score ${formatSigned(transition.score)}`}
    >
      <span className="longitudinal-score-zero" />
      {transition.lower !== null && transition.upper !== null && (
        <span
          className="longitudinal-score-interval"
          style={{
            left: `${50 + bounded(lower) * 25}%`,
            width: `${Math.max(0, bounded(upper) - bounded(lower)) * 25}%`,
          }}
        />
      )}
      <i style={{ left: `${50 + bounded(score) * 25}%` }} />
    </div>
  );
}

function requestTimePoints(request: JsonObject): Array<{
  id: string;
  offset: number | null;
  observations: number;
  active: number;
}> {
  const raw = request.time_points;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((value, index) => {
    if (!isJsonObject(value)) return [];
    const observations = Array.isArray(value.observations) ? value.observations : [];
    return [{
      id: textAt(value, ["time_point_id"], `time-point-${index + 1}`),
      offset: numberAt(value, ["time_offset_days"]),
      observations: observations.length,
      active: observations.filter((item) => (
        isJsonObject(item) && (item.state === "observed" || item.state === "left_censored")
      )).length,
    }];
  });
}

export function LongitudinalTimeline({ request, transitions, pelt }: LongitudinalPanelsProps) {
  const timePoints = requestTimePoints(request);
  const boundaries = new Map(pelt?.boundaries.map((item) => [item.index, item]) ?? []);
  return (
    <section className="result-panel longitudinal-timeline-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">ORDERED PROTEIN TRANSITIONS</p>
          <h3>Longitudinal concordance timeline</h3>
        </div>
        <span className="boundary-chip">interval-classified · source-cohort direction</span>
      </div>
      <div className="longitudinal-timeline" aria-label="Longitudinal GBM transition timeline">
        {timePoints.map((point, index) => {
          const transition = transitions[index];
          return (
            <div className="longitudinal-timeline-segment" key={point.id}>
              <article className="longitudinal-time-point" data-time-point-id={point.id}>
                <span>T{index + 1}</span>
                <b>{point.id}</b>
                <small>day {formatNumber(point.offset, 0)} · {point.active}/{point.observations} active</small>
              </article>
              {transition && (
                <article
                  className={`longitudinal-transition ${boundaries.has(index + 1) ? "has-boundary" : ""}`}
                  data-transition-id={transition.id}
                >
                  {boundaries.has(index + 1) && (
                    <span className="pelt-boundary-marker" data-pelt-boundary-index={index + 1}>
                      rate regime @ {boundaries.get(index + 1)?.rightTimePointId}
                    </span>
                  )}
                  <div><span>→</span><b>{formatSigned(transition.score)}</b></div>
                  <small>{intervalLabel(transition)}</small>
                  <span className={`support-badge ${transition.support}`}>{transition.support}</span>
                  <em>{classificationLabel(transition.classification)}</em>
                </article>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function LongitudinalTransitionTable({ transitions }: { transitions: LongitudinalTransition[] }) {
  return (
    <section className="result-panel state-panel longitudinal-transition-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">PAIRED TRANSITION MODEL</p><h3>Scores, support, and covariance-aware uncertainty</h3></div>
        <span className="boundary-chip">90% deterministic bootstrap intervals</span>
      </div>
      <div className="state-table-wrap">
        <table className="state-table longitudinal-transition-table">
          <thead><tr><th>Transition</th><th>Score / interval</th><th>Classification</th><th>Support</th><th>Coverage / ESS</th><th>Measurement uncertainty</th><th>Coefficient uncertainty</th><th>Covariance interaction</th><th>Top driver</th></tr></thead>
          <tbody>{transitions.map((transition) => (
            <tr key={transition.id} data-longitudinal-transition-id={transition.id}>
              <td><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{transition.id}</small></td>
              <td><span className="activity-value">{formatSigned(transition.score)}</span><TransitionScoreMark transition={transition} /><small>{intervalLabel(transition)} · {transition.bootstrapReplicates} bootstrap</small></td>
              <td><span className={`state-badge ${transition.classification}`}>{classificationLabel(transition.classification)}</span></td>
              <td><span className={`support-badge ${transition.support}`}>{transition.support}</span>{transition.reasons[0] && <small className="warning-copy">{transition.reasons[0]}</small>}</td>
              <td className="mono-cell">{transition.sharedActiveGenes} genes<small>{formatNumber((transition.coverage ?? 0) * 100, 1)}% · ESS {formatNumber(transition.effectiveSampleSize, 1)} · source pctl {formatNumber((transition.sourceSupportPercentile ?? 0) * 100, 1)}%</small></td>
              <td className="mono-cell">{formatNumber(transition.measurementUncertainty.standardError)}<small>{transition.measurementUncertainty.state.replaceAll("_", " ")} · variance {formatNumber(transition.measurementUncertainty.varianceFraction)}</small></td>
              <td className="mono-cell">{formatNumber(transition.coefficientUncertainty.standardError)}<small>{transition.coefficientUncertainty.state.replaceAll("_", " ")} · variance {formatNumber(transition.coefficientUncertainty.varianceFraction)}</small></td>
              <td className="mono-cell">{formatNumber(transition.uncertaintyInteraction.varianceContribution)}<small>cov {formatNumber(transition.uncertaintyInteraction.covariance)} · combined {formatNumber(transition.uncertaintyInteraction.combinedVariance)} · residual {formatNumber(transition.uncertaintyInteraction.decompositionResidual)}</small></td>
              <td>{transition.drivers[0] ? <><b>{transition.drivers[0].geneSymbol}</b><small>{formatSigned(transition.drivers[0].contribution)} · {classificationLabel(transition.drivers[0].direction)}</small></> : "—"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}

export function LongitudinalUncertaintyInteractionPanel({ transitions }: { transitions: LongitudinalTransition[] }) {
  return (
    <section className="result-panel longitudinal-uncertainty-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">PAIRED BOOTSTRAP VARIANCE IDENTITY</p><h3>Measurement × coefficient covariance</h3></div>
        <span className="boundary-chip">total = measurement + coefficient + 2 covariance</span>
      </div>
      <div className="longitudinal-uncertainty-grid">{transitions.map((transition) => {
        const interaction = transition.uncertaintyInteraction;
        const measurementVariance = transition.measurementUncertainty.standardError === null
          ? null
          : transition.measurementUncertainty.standardError ** 2;
        const coefficientVariance = transition.coefficientUncertainty.standardError === null
          ? null
          : transition.coefficientUncertainty.standardError ** 2;
        return <article key={transition.id} data-uncertainty-interaction-id={transition.id}>
          <header><div><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{interaction.method.replaceAll("_", " ")}</small></div><span className={`support-badge ${interaction.state === "estimated" ? transition.support : "abstained"}`}>{interaction.state.replaceAll("_", " ")}</span></header>
          <dl>
            <div><dt>measurement variance</dt><dd>{formatNumber(measurementVariance, 6)}</dd></div>
            <div><dt>coefficient variance</dt><dd>{formatNumber(coefficientVariance, 6)}</dd></div>
            <div><dt>covariance</dt><dd>{formatSigned(interaction.covariance, 6)}</dd></div>
            <div><dt>2 × covariance</dt><dd>{formatSigned(interaction.varianceContribution, 6)}</dd></div>
            <div><dt>combined variance</dt><dd>{formatNumber(interaction.combinedVariance, 6)}</dd></div>
            <div><dt>identity residual</dt><dd>{formatNumber(interaction.decompositionResidual, 8)}</dd></div>
          </dl>
          <small>{interaction.bootstrapReplicates} paired replicates{interaction.reason ? ` · ${interaction.reason}` : " · exact decomposition reported"}</small>
        </article>;
      })}</div>
    </section>
  );
}

export function LongitudinalExplanationPanels({ transitions }: { transitions: LongitudinalTransition[] }) {
  return (
    <section className="result-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">PROTEIN-LEVEL EXPLANATION / SENSITIVITY</p><h3>Drivers and frozen-model ablations</h3></div>
        <span className="boundary-chip">associations · not causal effects</span>
      </div>
      <div className="longitudinal-explanation-grid">{transitions.map((transition) => (
        <article key={transition.id} data-longitudinal-explanation-id={transition.id}>
          <header><div><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{classificationLabel(transition.classification)} · {transition.support}</small></div><strong>{formatSigned(transition.score)}</strong></header>
          <div className="longitudinal-driver-list">
            {transition.drivers.length ? transition.drivers.map((driver) => (
              <div key={`${driver.geneSymbol}-${driver.fromObservationId}-${driver.toObservationId}`}>
                <b>{driver.geneSymbol}</b><span>{formatSigned(driver.contribution)}</span>
                <small>source label {driver.sourceGeneLabel} · Δz {formatSigned(driver.standardizedDelta)} · coefficient {formatSigned(driver.coefficient)} · reliability {formatNumber(driver.reliabilityWeight)} · source pairs {formatNumber(driver.sourceFeatureSupport, 0)}</small>
              </div>
            )) : <p>No ranked driver claim; this transition abstained.</p>}
          </div>
          <div className="longitudinal-ablation-list">
            {transition.ablations.map((ablation, index) => (
              <div key={`${ablation.kind}-${ablation.label}-${index}`} data-ablation-kind={ablation.kind}>
                <b>{ablation.kind === "source_processing" ? "source-processing ablation" : `omit ${ablation.label}`}</b>
                <span>Δ {formatSigned(ablation.scoreDelta)}</span>
                <small>{ablation.label} · score without {formatSigned(ablation.scoreWithout)} · {classificationLabel(ablation.classification)} · {ablation.support}{ablation.reason ? ` · ${ablation.reason}` : ""}</small>
              </div>
            ))}
          </div>
        </article>
      ))}</div>
    </section>
  );
}

export function PeltPanel({ pelt }: { pelt: PeltEvidence | null }) {
  return (
    <section className="result-panel pelt-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">DURATION-NORMALIZED RATE-REGIME SENSITIVITY</p><h3>Exact transition-rate Huber PELT</h3></div>
        <span className={`support-badge ${pelt?.support ?? "abstained"}`}>{pelt?.support ?? "not returned"}</span>
      </div>
      {!pelt ? <p className="panel-empty">PELT is unavailable for this series.</p> : (
        <>
          <dl className="pelt-metrics">
            <div><dt>method</dt><dd>{pelt.method.replaceAll("_", " ")}</dd></div>
            <div><dt>penalty</dt><dd>{formatNumber(pelt.penalty)}</dd></div>
            <div><dt>objective</dt><dd>{formatNumber(pelt.objective)}</dd></div>
            <div><dt>bootstrap</dt><dd>{pelt.bootstrapReplicates}</dd></div>
          </dl>
          <p className="pelt-semantics">Transition scores are converted to rates per 90 days before segmentation. PELT requires at least four time points and each candidate segment requires at least two transition-rate observations. Boundary <i>b</i> is anchored at right time point <i>b</i>, with left endpoint <i>b−1</i>; it marks a rate-regime change, not a clinical event.</p>
          {pelt.boundaries.length ? <div className="pelt-boundary-list">{pelt.boundaries.map((boundary) => (
            <article key={boundary.index} data-pelt-boundary={boundary.index}>
              <span>B{boundary.index}</span>
              <div><b>rate regime changes at {boundary.rightTimePointId}</b><small>left {boundary.leftTimePointId} · right {boundary.rightTimePointId} · cost reduction {formatNumber(boundary.costReduction)} · bootstrap frequency {formatNumber((boundary.bootstrapFrequency ?? 0) * 100, 1)}%</small></div>
            </article>
          ))}</div> : <p className="panel-empty">No supported change-point boundary was selected.{pelt.reason ? ` ${pelt.reason}` : ""}</p>}
        </>
      )}
    </section>
  );
}

export function LongitudinalEvidencePanel({
  request,
  transitions,
  profile,
  provenance,
}: {
  request: JsonObject;
  transitions: LongitudinalTransition[];
  profile: JsonObject | null;
  provenance: JsonObject | null;
}) {
  const rawPoints = Array.isArray(request.time_points) ? request.time_points : [];
  const rows = rawPoints.flatMap((pointValue, pointIndex) => {
    if (!isJsonObject(pointValue) || !Array.isArray(pointValue.observations)) return [];
    return pointValue.observations.flatMap((observationValue) => isJsonObject(observationValue)
      ? [{ point: textAt(pointValue, ["time_point_id"], `T${pointIndex + 1}`), value: observationValue }]
      : []);
  });
  const visibleRows = rows.slice(0, 256);
  const reference = objectAt(request, ["normalization_reference"]);
  const assayCompatibility = objectAt(request, ["assay_compatibility"]);
  const counts = profile ? objectAt(profile, ["counts"]) : null;
  return (
    <div className="panel-stack">
      <section className="result-panel zero-fill-panel">
        <div className="panel-title-row"><div><p className="eyebrow">INTERPRETATION BOUNDARY</p><h3>Protein-level source-cohort transition evidence</h3></div><span className="boundary-chip">not patient evolution or recurrence prediction</span></div>
        <div className="zero-fill-explainer">
          <article><b>Source paired transitions</b><strong>{counts ? numberAt(counts, ["strict_paired_transition_count"]) ?? 104 : 104}</strong><p>The frozen axis describes concordance with source-cohort T2−T1 protein direction.</p></article>
          <article><b>Ordered time points</b><strong>{rawPoints.length}</strong><p>Every point is bound to one caller-declared invariant normalization reference.</p></article>
          <article><b>Active observations</b><strong>{rows.filter((row) => row.value.state === "observed" || row.value.state === "left_censored").length}</strong><p>Missing and unsupported proteins remain non-numeric evidence states.</p></article>
          <article className="warning"><b>Abstained transitions</b><strong>{transitions.filter((transition) => transition.support === "abstained").length}</strong><p>Inadequate overlap never becomes reverse-aligned or stable evidence.</p></article>
        </div>
      </section>
      <section className="result-panel">
        <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h3>Ordered protein evidence ledger</h3></div><span className="count-chip">{rows.length}</span></div>
        {rows.length > visibleRows.length && <p className="longitudinal-ledger-note">Showing the first {visibleRows.length} of {rows.length} observations; the downloadable request receipt retains every row.</p>}
        <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Time point</th><th>Observation</th><th>Gene</th><th>State</th><th>Log abundance ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
          {visibleRows.map(({ point, value }, index) => <tr key={textAt(value, ["observation_id"], String(index))}>
            <td><b>{point}</b></td><td>{textAt(value, ["observation_id"], `observation-${index + 1}`)}</td><td><b>{textAt(value, ["gene_symbol"], "—")}</b></td><td><span className="evidence-state">{textAt(value, ["state"], "—")}</span></td><td className="mono-cell">{formatNumber(numberAt(value, ["log_abundance"]), 3)} ± {formatNumber(numberAt(value, ["standard_error"]), 3)}</td><td className="mono-cell">{formatNumber(numberAt(value, ["quality_weight"]))}</td><td><code>{shortDigest(textAt(value, ["provenance_digest"]))}</code></td>
          </tr>)}
        </tbody></table></div>
      </section>
      <section className="mechanism-grid">
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">INVARIANT PREPROCESSING</p><h3>Normalization reference</h3></div></div>{reference ? <pre>{JSON.stringify(reference, null, 2)}</pre> : <p className="panel-empty">No normalization reference was supplied.</p>}</section>
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">REQUIRED INPUT COMPATIBILITY</p><h3>Assay and quantification attestation</h3></div></div>{assayCompatibility ? <pre>{JSON.stringify(assayCompatibility, null, 2)}</pre> : <p className="panel-empty">No compatible assay attestation was supplied.</p>}</section>
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">DE-IDENTIFIED SOURCE LOCKS</p><h3>Model provenance</h3></div></div>{provenance ? <pre>{JSON.stringify(provenance, null, 2)}</pre> : <p className="panel-empty">No source provenance was returned.</p>}</section>
      </section>
      <LongitudinalExplanationPanels transitions={transitions} />
    </div>
  );
}
