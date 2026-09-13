import {
  FUNCTIONAL_PROTEOTYPE_AXES,
  type FunctionalProteotypeAxis,
  type FunctionalProteotypeAxisEvidence,
} from "@/lib/gbm-functional-proteotype";
import { formatNumber, formatSigned } from "@/lib/research-state";

const AXIS_LABELS: Record<FunctionalProteotypeAxis, string> = {
  GPM: "glycolytic / plurimetabolic",
  MTC: "mitochondrial",
  NEU: "neuronal",
  PPR: "proliferative / progenitor",
};

function classificationClass(value: string): string {
  if (value === "source_aligned") return "activated";
  if (value === "source_opposed") return "suppressed";
  if (value === "neutral") return "neutral";
  return "indeterminate";
}

function ClassificationBadge({ value }: { value: string }) {
  return <span className={`state-badge ${classificationClass(value)}`}>{value.replaceAll("_", " ")}</span>;
}

function AxisScoreMark({ evidence }: { evidence: FunctionalProteotypeAxisEvidence }) {
  const score = evidence.estimate ?? 0;
  const lower = evidence.lower ?? score;
  const upper = evidence.upper ?? score;
  const bounded = (value: number) => Math.max(-3, Math.min(3, value));
  return (
    <div className="master-kinase-score-mark" aria-label={`${evidence.axis} constrained coordinate ${formatSigned(evidence.estimate)}`}>
      <span className="master-kinase-score-zero" />
      {evidence.lower !== null && evidence.upper !== null && (
        <span
          className="master-kinase-score-interval"
          style={{
            left: `${50 + bounded(lower) * (50 / 3)}%`,
            width: `${Math.max(0, bounded(upper) - bounded(lower)) * (50 / 3)}%`,
          }}
        />
      )}
      <i style={{ left: `${50 + bounded(score) * (50 / 3)}%` }} />
    </div>
  );
}

export function FunctionalProteotypeAxisTable({
  axes,
}: {
  axes: FunctionalProteotypeAxisEvidence[];
}) {
  return (
    <section className="result-panel state-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">MIGLIOZZI TABLE 2D / CONSTRAINED CONCORDANCE</p>
          <h3>Four constrained source-axis coordinates</h3>
        </div>
        <span className="boundary-chip">Σ z = 0 · not subtype probabilities</span>
      </div>
      <div className="zero-fill-notice">
        <b>Interpretation boundary</b>
        <span>Each coordinate is bulk-protein concordance with one source-selected GBM signature. Coordinates are jointly fitted and must not be ranked into a patient subtype, winner, probability, diagnosis, or treatment assignment.</span>
      </div>
      {axes.length === 0 ? <p className="panel-empty">No valid source-axis evidence was returned.</p> : (
        <div className="state-table-wrap">
          <table className="state-table">
            <thead>
              <tr>
                <th>Source axis</th>
                <th>Coordinate / 90% interval</th>
                <th>Support / classification</th>
                <th>Independent rank evidence</th>
                <th>p / q</th>
                <th>Signature evidence / ESS</th>
                <th>Stability / discordance</th>
                <th>Top driver</th>
              </tr>
            </thead>
            <tbody>{axes.map((axis) => (
              <tr key={axis.axis} data-functional-axis-id={axis.axis}>
                <td><b>{axis.axis}</b><small>{AXIS_LABELS[axis.axis]}</small></td>
                <td>
                  <span className="activity-value">{formatSigned(axis.estimate)}</span>
                  <AxisScoreMark evidence={axis} />
                  <small>{axis.lower === null || axis.upper === null ? "interval not estimable" : `[${formatNumber(axis.lower)}, ${formatNumber(axis.upper)}]`} · bootstrap {axis.bootstrapReplicates}</small>
                </td>
                <td>
                  <ClassificationBadge value={axis.classification} />
                  <small><span className={`support-badge ${axis.support}`}>{axis.support}</span></small>
                  {axis.reasons[0] && <small className="warning-copy">{axis.reasons[0]}</small>}
                </td>
                <td className="mono-cell">
                  r<sub>rb</sub> {formatSigned(axis.rankBiserial)}
                  <small>U {formatNumber(axis.uStatistic, 1)} · {axis.signatureObservedCount} signature / {axis.complementObservedCount} background</small>
                </td>
                <td className="mono-cell">{formatNumber(axis.pValue, 4)} / {formatNumber(axis.qValue, 4)}<small>{axis.permutationReplicates} stratified permutations</small></td>
                <td className="mono-cell">{axis.counts.observed} observed + {axis.counts.leftCensored} censored<small>{formatNumber(axis.counts.activeFraction * 100, 1)}% of 150 · ESS {formatNumber(axis.effectiveSampleSize, 1)}</small></td>
                <td className="mono-cell">{formatNumber(axis.stability)} / {formatNumber(axis.discordance)}</td>
                <td>{axis.drivers[0] ? <><b>{axis.drivers[0].geneSymbol}</b><small>{formatSigned(axis.drivers[0].signedContribution)} contribution · Q{axis.drivers[0].sourceRankQuartile}</small></> : "—"}</td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}

export function FunctionalProteotypeExplanationPanels({
  axes,
}: {
  axes: FunctionalProteotypeAxisEvidence[];
}) {
  return (
    <section className="result-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">PROTEIN-LEVEL EXPLANATION / SENSITIVITY</p><h3>Top drivers and evidence-conserving ablations</h3></div>
        <span className="boundary-chip">Huber score contribution · not causal attribution</span>
      </div>
      <div className="master-explanation-grid">{axes.map((axis) => (
        <article key={axis.axis} data-functional-explanation-id={axis.axis}>
          <header>
            <div><b>{axis.axis} · {AXIS_LABELS[axis.axis]}</b><small>{axis.classification.replaceAll("_", " ")} · {axis.support}</small></div>
            <strong>{formatSigned(axis.estimate)}</strong>
          </header>
          <div className="master-driver-list">
            {axis.drivers.length ? axis.drivers.map((driver) => (
              <div key={driver.observationId}>
                <b>{driver.geneSymbol}</b><span>{formatSigned(driver.signedContribution)}</span>
                <small>{driver.evidenceState.replaceAll("_", " ")} · source rank {driver.sourceRank} / quartile {driver.sourceRankQuartile} · effect {formatSigned(driver.effect)} · loading {formatSigned(driver.sourceLoading)} · reliability {formatNumber(driver.reliabilityWeight)}</small>
              </div>
            )) : <p>No driver claim; this source axis abstained or lacked estimable evidence.</p>}
          </div>
          <div className="master-ablation-list">{axis.ablations.map((ablation) => (
            <div key={`${ablation.kind}-${ablation.target}`}>
              <b>omit {ablation.kind.replaceAll("_", " ")} · {ablation.target}</b><span>{ablation.proteinsRemoved} proteins</span>
              <small>{ablation.support} · {ablation.classification.replaceAll("_", " ")} · {formatSigned(ablation.baselineEstimate)} → {formatSigned(ablation.estimate)} · Δ {formatSigned(ablation.delta)}{ablation.reason ? ` · ${ablation.reason}` : ""}</small>
            </div>
          ))}</div>
        </article>
      ))}</div>
    </section>
  );
}

export function FunctionalProteotypePathwayContextPanel({
  axes,
}: {
  axes: FunctionalProteotypeAxisEvidence[];
}) {
  const pathways = FUNCTIONAL_PROTEOTYPE_AXES.flatMap((axis) => axes.find((item) => item.axis === axis)?.pathways ?? []);
  return (
    <section className="result-panel state-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">MIGLIOZZI TABLE 2E / SOURCE COHORT ONLY</p><h3>Source-cohort pathway context</h3></div>
        <span className="boundary-chip">sample inference: not evaluated</span>
      </div>
      <div className="zero-fill-notice">
        <b>No sample pathway scoring</b>
        <span>These published logitNES, p-values, and q-values annotate the source cohort. Table 2e does not provide pathway memberships, so this lane never converts them into pathway activity for the submitted sample.</span>
      </div>
      {pathways.length === 0 ? <p className="panel-empty">No valid source-cohort pathway context was returned.</p> : (
        <div className="state-table-wrap">
          <table className="state-table">
            <thead><tr><th>Axis</th><th>Source rank</th><th>Published pathway</th><th>Source logitNES</th><th>Source p / q</th><th>Sample inference</th></tr></thead>
            <tbody>{pathways.map((pathway) => (
              <tr key={`${pathway.axis}-${pathway.sourceRank}-${pathway.pathwayName}`} data-functional-pathway-axis={pathway.axis}>
                <td><b>{pathway.axis}</b></td>
                <td className="mono-cell">{pathway.sourceRank}</td>
                <td>{pathway.pathwayName}</td>
                <td className="mono-cell">{formatNumber(pathway.sourceLogitNes, 4)}</td>
                <td className="mono-cell">{formatNumber(pathway.sourcePValue, 4)} / {formatNumber(pathway.sourceQValue, 4)}</td>
                <td><span className="support-badge limited">not evaluated</span><small>source context only</small></td>
              </tr>
            ))}</tbody>
          </table>
        </div>
      )}
    </section>
  );
}
