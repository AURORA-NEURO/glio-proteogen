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
import type { PhosphoTransition } from "@/lib/longitudinal-gbm-phospho";

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function interval(transition: PhosphoTransition): string {
  if (transition.lower === null || transition.upper === null) return "not estimable";
  return `[${formatNumber(transition.lower)}, ${formatNumber(transition.upper)}]`;
}

function requestTimePoints(request: JsonObject): Array<{
  id: string;
  offset: number | null;
  observations: number;
  active: number;
}> {
  if (!Array.isArray(request.time_points)) return [];
  return request.time_points.flatMap((value, index) => {
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

function TransitionMark({ transition }: { transition: PhosphoTransition }) {
  const score = transition.score ?? 0;
  const lower = transition.lower ?? score;
  const upper = transition.upper ?? score;
  const bounded = (value: number) => Math.max(-2, Math.min(2, value));
  return (
    <div className="longitudinal-score-mark" aria-label={`Phosphosite transition score ${formatSigned(transition.score)}`}>
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

export function PhosphoTimeline({
  request,
  transitions,
}: {
  request: JsonObject;
  transitions: PhosphoTransition[];
}) {
  const points = requestTimePoints(request);
  return (
    <section className="result-panel longitudinal-timeline-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">ORDERED PHOSPHOSITE TRANSITIONS</p><h3>Raw phosphosite concordance timeline</h3></div>
        <span className="boundary-chip">interval-qualified · source recurrence direction</span>
      </div>
      <div className="longitudinal-timeline" aria-label="Longitudinal GBM phosphosite timeline">
        {points.map((point, index) => {
          const transition = transitions[index];
          return (
            <div className="longitudinal-timeline-segment" key={point.id}>
              <article className="longitudinal-time-point" data-phospho-time-point-id={point.id}>
                <span>P{index + 1}</span><b>{point.id}</b>
                <small>day {formatNumber(point.offset, 0)} · {point.active}/{point.observations} active</small>
              </article>
              {transition && (
                <article className="longitudinal-transition" data-phospho-timeline-transition={transition.id}>
                  <div><span>→</span><b>{formatSigned(transition.score)}</b></div>
                  <small>{interval(transition)}</small>
                  <span className={`support-badge ${transition.support}`}>{transition.support}</span>
                  <em>{label(transition.classification)}</em>
                </article>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function PhosphoTransitionTable({ transitions }: { transitions: PhosphoTransition[] }) {
  return (
    <section className="result-panel state-panel longitudinal-transition-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">PDC000515 FITTED AXIS</p><h3>Phosphosite scores, support, and uncertainty</h3></div>
        <span className="boundary-chip">90% deterministic full-model bootstrap interval</span>
      </div>
      <div className="state-table-wrap">
        <table className="state-table longitudinal-transition-table">
          <thead><tr><th>Transition</th><th>Score / interval</th><th>Classification</th><th>Support</th><th>Exact / censored</th><th>Weight / source coverage</th><th>ESS</th><th>Top phosphosite</th></tr></thead>
          <tbody>{transitions.map((transition) => (
            <tr key={transition.id} data-phospho-transition-id={transition.id}>
              <td><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{transition.id}</small></td>
              <td><span className="activity-value">{formatSigned(transition.score)}</span><TransitionMark transition={transition} /><small>{interval(transition)} · {transition.bootstrapReplicates} refits</small></td>
              <td><span className={`state-badge ${transition.classification}`}>{label(transition.classification)}</span></td>
              <td><span className={`support-badge ${transition.support}`}>{transition.support}</span>{transition.reasons[0] && <small className="warning-copy">{transition.reasons[0]}</small>}</td>
              <td className="mono-cell">{transition.exactFeatureCount} / {transition.censoredFeatureCount}<small>exact / one-sided bounds</small></td>
              <td className="mono-cell">{formatNumber((transition.coefficientCoverage ?? 0) * 100, 1)}%<small>source pair mean {formatNumber((transition.sourcePairCoverageMean ?? 0) * 100, 1)}%</small></td>
              <td className="mono-cell">{formatNumber(transition.effectiveSampleSize, 1)}</td>
              <td>{transition.drivers[0] ? <><b>{transition.drivers[0].geneSymbol}</b><small>{transition.drivers[0].phosphositeId} · {formatSigned(transition.drivers[0].contribution)}</small></> : "—"}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </section>
  );
}

export function PhosphoUncertaintyPanel({ transitions }: { transitions: PhosphoTransition[] }) {
  return (
    <section className="result-panel longitudinal-uncertainty-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">DIRECT FULL-MODEL PERTURBATION</p><h3>Measurement × coefficient × interaction closure</h3></div>
        <span className="boundary-chip">combined variance closes with three covariance terms</span>
      </div>
      <div className="longitudinal-uncertainty-grid">{transitions.map((transition) => {
        const interaction = transition.uncertaintyInteraction;
        return (
          <article key={transition.id} data-phospho-uncertainty-id={transition.id}>
            <header><div><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{label(interaction.method)}</small></div><span className={`support-badge ${transition.support}`}>{interaction.state}</span></header>
            <dl>
              <div><dt>measurement variance</dt><dd>{formatNumber(transition.measurementUncertainty.variance, 8)}</dd></div>
              <div><dt>coefficient variance</dt><dd>{formatNumber(transition.coefficientUncertainty.variance, 8)}</dd></div>
              <div><dt>interaction variance</dt><dd>{formatNumber(interaction.variance, 8)}</dd></div>
              <div><dt>measurement × coefficient</dt><dd>{formatSigned(interaction.measurementCoefficientCovariance, 8)}</dd></div>
              <div><dt>measurement × interaction</dt><dd>{formatSigned(interaction.measurementInteractionCovariance, 8)}</dd></div>
              <div><dt>coefficient × interaction</dt><dd>{formatSigned(interaction.coefficientInteractionCovariance, 8)}</dd></div>
              <div><dt>combined / decomposed</dt><dd>{formatNumber(interaction.combinedVariance, 8)} / {formatNumber(interaction.decomposedVariance, 8)}</dd></div>
              <div><dt>closure residual</dt><dd>{formatSigned(interaction.decompositionResidual, 8)}</dd></div>
            </dl>
            <small>{interaction.bootstrapReplicates} paired direct projections{interaction.reason ? ` · ${interaction.reason}` : " · quantized receipt identity"}</small>
          </article>
        );
      })}</div>
    </section>
  );
}

export function PhosphoExplanationPanels({ transitions }: { transitions: PhosphoTransition[] }) {
  return (
    <section className="result-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">PHOSPHOSITE EXPLANATION / SENSITIVITY</p><h3>Drivers, SPHINKS annotations, bounds, and ablations</h3></div>
        <span className="boundary-chip">identity annotation only · no kinase inference</span>
      </div>
      <div className="longitudinal-explanation-grid">{transitions.map((transition) => (
        <article key={transition.id} data-phospho-explanation-id={transition.id}>
          <header><div><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{label(transition.classification)} · {transition.support}</small></div><strong>{formatSigned(transition.score)}</strong></header>
          <div className="longitudinal-driver-list">
            {transition.drivers.length ? transition.drivers.map((driver) => (
              <div key={`${driver.phosphositeId}-${driver.fromObservationId}`}>
                <b>{driver.geneSymbol} · {driver.phosphositeId}</b><span>{formatSigned(driver.contribution)}</span>
                <small>{driver.composite ? `${driver.siteCardinality}-site indivisible group` : "single source site"} · Δz {formatSigned(driver.standardizedDelta)} · coefficient {formatSigned(driver.coefficient)} · source pairs {formatNumber(driver.sourcePairSupport, 0)} · bootstrap selection {formatNumber((driver.bootstrapStability ?? 0) * 100, 1)}%{driver.sphinksLabel ? ` · SPHINKS ${driver.sphinksLabel}` : " · no exact SPHINKS match"}{driver.sphinksKinases.length ? ` · signatures ${driver.sphinksKinases.join(", ")}` : ""}</small>
              </div>
            )) : <p>No ranked phosphosite driver claim; this transition abstained.</p>}
          </div>
          {transition.censoredBounds.length > 0 && (
            <div className="longitudinal-ablation-list" data-phospho-censored-bounds={transition.id}>
              {transition.censoredBounds.map((bound) => <div key={bound.phosphositeId}><b>{bound.geneSymbol} · {bound.semantics.replaceAll("_", " ")}</b><span>{formatSigned(bound.weightedBound)}</span><small>{bound.phosphositeId} · standardized bound {formatSigned(bound.standardizedBound)} · excluded from point projection</small></div>)}
            </div>
          )}
          <div className="longitudinal-ablation-list">
            {transition.ablations.map((ablation, index) => (
              <div key={`${ablation.kind}-${ablation.label}-${index}`} data-phospho-ablation-kind={ablation.kind}>
                <b>{ablation.kind === "feature_family" ? `omit ${label(ablation.label)}` : `omit driver ${ablation.label}`}</b><span>Δ {formatSigned(ablation.scoreDelta)}</span>
                <small>{ablation.omittedCount} omitted · score without {formatSigned(ablation.scoreWithout)} · {label(ablation.classification)} · {ablation.support}{ablation.reason ? ` · ${ablation.reason}` : ""}</small>
              </div>
            ))}
          </div>
        </article>
      ))}</div>
    </section>
  );
}

export function PhosphoEvidencePanel({
  request,
  result,
  transitions,
  profile,
  provenance,
}: {
  request: JsonObject;
  result: JsonObject;
  transitions: PhosphoTransition[];
  profile: JsonObject | null;
  provenance: JsonObject | null;
}) {
  const points = Array.isArray(request.time_points) ? request.time_points : [];
  const rows = points.flatMap((point, pointIndex) => {
    if (!isJsonObject(point) || !Array.isArray(point.observations)) return [];
    return point.observations.flatMap((observation) => isJsonObject(observation) ? [{
      point: textAt(point, ["time_point_id"], `P${pointIndex + 1}`),
      value: observation,
    }] : []);
  });
  const visibleRows = rows.slice(0, 256);
  const counts = profile ? objectAt(profile, ["counts"]) : null;
  const views = Array.isArray(result.model_views)
    ? result.model_views.filter(isJsonObject)
    : [];
  return (
    <div className="panel-stack">
      <section className="result-panel zero-fill-panel">
        <div className="panel-title-row"><div><p className="eyebrow">MODEL / CLAIM BOUNDARY</p><h3>Raw phosphosite transition only</h3></div><span className="boundary-chip">occupancy and protein fusion remain not fitted</span></div>
        <div className="zero-fill-explainer">
          <article><b>Source paired transitions</b><strong>{counts ? numberAt(counts, ["strict_pair_count"]) ?? 88 : 88}</strong><p>PDC000515 source-cohort T2−T1 phosphosite concordance.</p></article>
          <article><b>Release axis</b><strong>{counts ? numberAt(counts, ["selected_feature_count"]) ?? 32 : 32}</strong><p>Selected from 4,225 minimum-support aggregate sites.</p></article>
          <article><b>Active evidence</b><strong>{rows.filter((row) => row.value.state === "observed" || row.value.state === "left_censored").length}</strong><p>Missing and unsupported values remain non-numeric.</p></article>
          <article className="warning"><b>Limited transitions</b><strong>{transitions.filter((transition) => transition.support === "limited").length}</strong><p>Unstable feature selection and uncalibrated intervals cap support.</p></article>
        </div>
        <div className="model-view-grid">{views.map((view) => <article key={textAt(view, ["view"])}><b>{label(textAt(view, ["view"], "view"))}</b><span className={`support-badge ${textAt(view, ["support"]) === "fitted" ? "supported" : "abstained"}`}>{label(textAt(view, ["support"]))}</span><small>{textAt(view, ["reason"])}</small></article>)}</div>
      </section>
      <section className="result-panel">
        <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h3>Exact phosphosite evidence ledger</h3></div><span className="count-chip">{rows.length}</span></div>
        {rows.length > visibleRows.length && <p className="longitudinal-ledger-note">Showing the first {visibleRows.length} of {rows.length}; the request download retains every row.</p>}
        <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Time point</th><th>Observation</th><th>Gene / source site group</th><th>State</th><th>Log ratio ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
          {visibleRows.map(({ point, value }, index) => <tr key={textAt(value, ["observation_id"], String(index))}><td><b>{point}</b></td><td>{textAt(value, ["observation_id"], `observation-${index + 1}`)}</td><td><b>{textAt(value, ["gene_symbol"], "—")}</b><small>{textAt(value, ["phosphosite_id"], "—")}</small></td><td><span className="evidence-state">{textAt(value, ["state"], "—")}</span></td><td className="mono-cell">{formatNumber(numberAt(value, ["log_abundance_ratio"]), 3)} ± {formatNumber(numberAt(value, ["standard_error"]), 3)}</td><td className="mono-cell">{formatNumber(numberAt(value, ["quality_weight"]))}</td><td><code>{shortDigest(textAt(value, ["provenance_digest"]))}</code></td></tr>)}
        </tbody></table></div>
      </section>
      <section className="mechanism-grid">
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">INVARIANT PREPROCESSING</p><h3>Normalization reference</h3></div></div><pre>{JSON.stringify(objectAt(request, ["normalization_reference"]), null, 2)}</pre></section>
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">EXACT ASSAY CONTRACT</p><h3>Phosphoproteome compatibility</h3></div></div><pre>{JSON.stringify(objectAt(request, ["assay_compatibility"]), null, 2)}</pre></section>
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">PDC / HGNC / SPHINKS LOCKS</p><h3>Standalone provenance</h3></div></div>{provenance ? <pre>{JSON.stringify(provenance, null, 2)}</pre> : <p className="panel-empty">No provenance was returned.</p>}</section>
      </section>
      <PhosphoExplanationPanels transitions={transitions} />
    </div>
  );
}
