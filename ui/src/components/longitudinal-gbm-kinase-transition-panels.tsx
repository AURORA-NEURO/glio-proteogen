"use client";

import {
  formatNumber,
  formatSigned,
  isJsonObject,
  numberAt,
  shortDigest,
  textAt,
  type JsonObject,
} from "@/lib/research-state";
import type { KinaseTransition } from "@/lib/longitudinal-gbm-kinase-transition";

function label(value: string): string {
  return value.replaceAll("_", " ");
}

function interval(transition: KinaseTransition): string {
  const { lower, upper } = transition.uncertainty;
  return lower === null || upper === null
    ? "not estimable"
    : `[${formatSigned(lower)}, ${formatSigned(upper)}]`;
}

export function KinaseTransitionResultPanels({
  transitions,
}: {
  transitions: KinaseTransition[];
}) {
  return (
    <div className="panel-stack">
      <section className="result-panel zero-fill-panel">
        <div className="panel-title-row">
          <div><p className="eyebrow">SPHINKS SIGNATURE TRANSITION RECEIPT</p><h3>Source-cohort concordance, not kinase activity</h3></div>
          <span className="boundary-chip">LIMITED or abstained only · no causal claim</span>
        </div>
        <div className="zero-fill-explainer">
          <article><b>Transitions</b><strong>{transitions.length}</strong><p>Consecutive ordered phosphosite contrasts.</p></article>
          <article><b>Locked hypotheses</b><strong>24</strong><p>Fixed SPHINKS master-kinase family with BH correction.</p></article>
          <article><b>Selected per transition</b><strong>12</strong><p>Eleven core-stable plus unstable CHEK2.</p></article>
          <article className="warning"><b>Supported claims</b><strong>0</strong><p>Same-assay source evidence cannot independently validate activity.</p></article>
        </div>
      </section>
      <section className="result-panel state-panel longitudinal-transition-panel">
        <div className="panel-title-row">
          <div><p className="eyebrow">ORDERED SIGNATURE COORDINATES</p><h3>Transition score and interval</h3></div>
          <span className="boundary-chip">interval-qualified at ±0.05</span>
        </div>
        <div className="state-table-wrap"><table className="state-table longitudinal-transition-table">
          <thead><tr><th>Transition</th><th>Score / interval</th><th>Classification</th><th>Support</th><th>Source rows / families</th><th>Estimable kinases</th><th>Top family driver</th></tr></thead>
          <tbody>{transitions.map((transition) => {
            const top = transition.kinases.flatMap((kinase) => kinase.drivers.map((driver) => ({ kinase: kinase.kinase, driver })))
              .sort((left, right) => Math.abs(right.driver.contribution ?? 0) - Math.abs(left.driver.contribution ?? 0))[0];
            return <tr key={transition.id} data-kinase-transition-id={transition.id}>
              <td><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{transition.id}</small></td>
              <td><span className="activity-value">{formatSigned(transition.score)}</span><small>{interval(transition)} · {transition.uncertainty.bootstrapReplicates} refits</small></td>
              <td><span className={`state-badge ${transition.classification}`}>{label(transition.classification)}</span></td>
              <td><span className={`support-badge ${transition.support}`}>{transition.support}</span><small className="warning-copy">{transition.reasons[0]}</small></td>
              <td className="mono-cell">{transition.exactSourceRows} / {transition.exactFamilies}<small>{transition.censoredFamilies} censored families</small></td>
              <td className="mono-cell">{transition.estimableKinases} / {transition.selectedKinases}</td>
              <td>{top ? <><b>{top.kinase}</b><small>{top.driver.sourceSiteLabel} · {formatSigned(top.driver.contribution)}</small></> : "—"}</td>
            </tr>;
          })}</tbody>
        </table></div>
      </section>
      {transitions.map((transition) => (
        <section className="result-panel" key={transition.id} data-kinase-signatures={transition.id}>
          <div className="panel-title-row">
            <div><p className="eyebrow">{transition.fromTimePointId} → {transition.toTimePointId}</p><h3>Locked kinase family and subtype aggregates</h3></div>
            <span className="boundary-chip">CHEK2 remains selection-unstable</span>
          </div>
          <div className="state-table-wrap"><table className="state-table">
            <thead><tr><th>Kinase</th><th>Source subtype / direction</th><th>Selection</th><th>Score / interval</th><th>Source q</th><th>Coverage</th><th>Support</th></tr></thead>
            <tbody>{transition.kinases.map((kinase) => <tr key={kinase.kinase} data-kinase={kinase.kinase}>
              <td><b>{kinase.kinase}</b></td>
              <td>{kinase.subtype}<small>{label(kinase.sourceDirection)}</small></td>
              <td>{label(kinase.selectionState)}<small>bootstrap {formatNumber((kinase.bootstrapSelectionFrequency ?? 0) * 100, 1)}%</small></td>
              <td><b>{formatSigned(kinase.score)}</b><small>{kinase.uncertainty.lower === null ? "not estimable" : `[${formatSigned(kinase.uncertainty.lower)}, ${formatSigned(kinase.uncertainty.upper)}]`}</small></td>
              <td className="mono-cell">{formatNumber(kinase.sourceQValue, 4)}</td>
              <td className="mono-cell">{formatNumber((kinase.sourceWeightCoverage ?? 0) * 100, 1)}%<small>{kinase.observedFamilies}/{kinase.mappedSourceFamilies} families</small></td>
              <td><span className={`support-badge ${kinase.support}`}>{kinase.support}</span></td>
            </tr>)}</tbody>
          </table></div>
          <div className="longitudinal-ablation-list">
            {transition.ablations.map((ablation) => <div key={ablation.kind} data-kinase-ablation={ablation.kind}><b>{label(ablation.kind)}</b><span>Δ {formatSigned(ablation.scoreDelta)}</span><small>{formatSigned(ablation.score)} · {label(ablation.classification)} · {ablation.support} · {ablation.reason}</small></div>)}
          </div>
        </section>
      ))}
    </div>
  );
}

export function KinaseTransitionEvidencePanel({
  request,
  transitions,
  profile,
  provenance,
}: {
  request: JsonObject;
  transitions: KinaseTransition[];
  profile: JsonObject | null;
  provenance: JsonObject | null;
}) {
  const rows = Array.isArray(request.time_points) ? request.time_points.flatMap((point, pointIndex) => {
    if (!isJsonObject(point) || !Array.isArray(point.observations)) return [];
    return point.observations.flatMap((observation) => isJsonObject(observation) ? [{
      point: textAt(point, ["time_point_id"], `P${pointIndex + 1}`),
      observation,
    }] : []);
  }) : [];
  const counts = profile && isJsonObject(profile.counts) ? profile.counts : null;
  return (
    <div className="panel-stack">
      <section className="result-panel zero-fill-panel">
        <div className="panel-title-row"><div><p className="eyebrow">MODEL / CLAIM BOUNDARY</p><h3>Signature-transition concordance only</h3></div><span className="boundary-chip">not activity · not biochemical function · not causality</span></div>
        <div className="zero-fill-explainer">
          <article><b>Strict source pairs</b><strong>{counts ? numberAt(counts, ["strict_patient_pairs"]) ?? 88 : 88}</strong><p>Same-cohort patient-grouped evaluation.</p></article>
          <article><b>Source families</b><strong>{counts ? numberAt(counts, ["unique_signature_families"]) ?? 572 : 572}</strong><p>Exact SPHINKS signature families projected through PDC000515.</p></article>
          <article><b>Executed evidence</b><strong>{rows.length}</strong><p>Missing and unsupported rows remain non-numeric.</p></article>
          <article className="warning"><b>LIMITED transitions</b><strong>{transitions.filter((item) => item.support === "limited").length}</strong><p>Stability and interval-calibration gates remain failed.</p></article>
        </div>
      </section>
      <section className="result-panel">
        <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h3>Phosphosite evidence ledger</h3></div><span className="count-chip">{rows.length}</span></div>
        <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Point</th><th>Observation</th><th>Gene / exact source group</th><th>State</th><th>Log ratio ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
          {rows.slice(0, 256).map(({ point, observation }, index) => <tr key={textAt(observation, ["observation_id"], String(index))}><td><b>{point}</b></td><td>{textAt(observation, ["observation_id"], `observation-${index + 1}`)}</td><td><b>{textAt(observation, ["gene_symbol"], "—")}</b><small>{textAt(observation, ["phosphosite_id"], "—")}</small></td><td>{textAt(observation, ["state"], "—")}</td><td className="mono-cell">{formatNumber(numberAt(observation, ["log_abundance_ratio"]), 3)} ± {formatNumber(numberAt(observation, ["standard_error"]), 3)}</td><td>{formatNumber(numberAt(observation, ["quality_weight"]))}</td><td><code>{shortDigest(textAt(observation, ["provenance_digest"]))}</code></td></tr>)}
        </tbody></table></div>
      </section>
      <section className="mechanism-grid">
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">EXACT ASSAY CONTRACT</p><h3>PDC000515 phosphoproteome</h3></div></div><pre>{JSON.stringify(request.assay_compatibility ?? null, null, 2)}</pre></section>
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">SOURCE / NUMERICAL LOCKS</p><h3>Authenticated provenance</h3></div></div><pre>{JSON.stringify(provenance ?? null, null, 2)}</pre></section>
      </section>
    </div>
  );
}
