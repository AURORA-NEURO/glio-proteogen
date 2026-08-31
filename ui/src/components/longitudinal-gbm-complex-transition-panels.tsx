import {
  complexEstimatedCount,
  complexResultCount,
  complexSupportedCount,
  complexTransitionRequestStats,
  type ComplexEvaluationSummary,
  type ComplexMemberConcordance,
  type ComplexTransition,
} from "@/lib/longitudinal-gbm-complex-transition";
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

function percent(value: number | null, digits = 1): string {
  return value === null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function interval(item: ComplexMemberConcordance): string {
  return item.lower === null || item.upper === null
    ? "interval unavailable"
    : `[${formatSigned(item.lower)}, ${formatSigned(item.upper)}]`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

export function ComplexLockedEvaluationPanel({
  evaluation,
}: {
  evaluation: ComplexEvaluationSummary | null;
}) {
  return (
    <section className="result-panel reactome-evaluation-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">PATIENT-GROUPED HELD-MEMBER EVALUATION</p>
          <h3>Fitted participant-set evidence ceiling</h3>
        </div>
        <span className="support-badge limited">same cohort · not external validation</span>
      </div>
      {!evaluation ? (
        <p className="panel-empty">The locked fitted-model evaluation was not returned.</p>
      ) : (
        <>
          <div className="zero-fill-notice">
            <b>What was actually evaluated</b>
            <span>
              Held-patient, held-member reconstruction tests whether a robust one-factor
              participant coordinate predicts omitted protein transitions better than a
              training-center baseline. It does not validate complex assembly or activity.
            </span>
          </div>
          <div className="zero-fill-explainer reactome-evaluation-grid">
            <article>
              <b>Patient-grouped design</b>
              <strong>{evaluation.patientCount}</strong>
              <p>{evaluation.evaluationCount.toLocaleString("en-US")} held-member evaluations.</p>
            </article>
            <article>
              <b>Factor-model mean MAE</b>
              <strong>{formatNumber(evaluation.factorModelMeanMae, 4)}</strong>
              <p>
                training center {formatNumber(evaluation.trainingCenterMeanMae, 4)} · zero
                transition {formatNumber(evaluation.zeroTransitionMeanMae, 4)}
              </p>
            </article>
            <article>
              <b>Mean relative gain</b>
              <strong>{percent(evaluation.meanRelativeGain, 2)}</strong>
              <p>Aggregate held-member improvement over the training-center baseline.</p>
            </article>
            <article>
              <b>Patient-cluster 90% interval</b>
              <strong>
                {percent(evaluation.patientClusterInterval[0], 2)} – {percent(evaluation.patientClusterInterval[1], 2)}
              </strong>
              <p>Descriptive same-cohort patient bootstrap.</p>
            </article>
            <article>
              <b>Direction accuracy</b>
              <strong>{percent(evaluation.directionAccuracy, 2)}</strong>
              <p>Held-member transition direction on evaluable records.</p>
            </article>
            <article className="warning">
              <b>Convergence / validation</b>
              <strong>
                {evaluation.nonconvergedReferenceFitCount + evaluation.nonconvergedOuterFitCount === 0
                  ? "all fitted"
                  : "review failures"}
              </strong>
              <p>{evaluation.validationScope}; external validation: {evaluation.externalValidationPerformed ? "yes" : "no"}.</p>
            </article>
          </div>
        </>
      )}
    </section>
  );
}

function ComplexTable({ transitions }: { transitions: ComplexTransition[] }) {
  return (
    <section className="result-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">28 REACTOME PARTICIPANT SETS / 11 PILOT DOMAINS</p>
          <h3>Robust member-transition coordinates</h3>
        </div>
        <span className="boundary-chip">concordance · never assembly or activity</span>
      </div>
      <div className="state-table-wrap">
        <table className="state-table">
          <thead>
            <tr>
              <th>Transition / domain</th>
              <th>Reactome participant set</th>
              <th>Coordinate / 90% interval</th>
              <th>Evidence</th>
              <th>Stability / discordance</th>
              <th>Support</th>
            </tr>
          </thead>
          <tbody>
            {transitions.flatMap((transition) =>
              transition.complexes.map((item) => (
                <tr key={`${transition.id}-${item.reactomeId}`}>
                  <td>
                    <b>{transition.fromTimePointId} → {transition.toTimePointId}</b>
                    <small>{humanize(item.domainId)}</small>
                  </td>
                  <td>
                    <b>{item.complexName}</b>
                    <small>{item.reactomeId} · family {item.familyId}</small>
                  </td>
                  <td className="mono-cell">
                    <b>{formatSigned(item.score)}</b>
                    <small>{interval(item)} · {humanize(item.classification)}</small>
                  </td>
                  <td>
                    <b>{item.activeMemberCount} active</b>
                    <small>
                      {item.observedMemberCount} observed · {item.leftCensoredMemberCount} censored · {percent(item.coefficientMassCoverage)} mass
                    </small>
                  </td>
                  <td>
                    <b>{percent(item.stability)} / {percent(item.discordance)}</b>
                    <small>coherence {percent(item.coherence)} · ESS {formatNumber(item.effectiveSampleSize, 2)}</small>
                  </td>
                  <td>
                    <span className={`support-badge ${item.support}`}>{item.support}</span>
                    {item.reasons[0] && <small className="warning-copy">{item.reasons[0]}</small>}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function ExplanationPanels({ transitions }: { transitions: ComplexTransition[] }) {
  const rows = transitions.flatMap((transition) =>
    transition.complexes.map((item) => ({ transition, item })),
  );
  return (
    <section className="result-panel reactome-contribution-panel">
      <div className="panel-title-row">
        <div>
          <p className="eyebrow">MEMBER EVIDENCE / SOURCE / TOPOLOGY SENSITIVITY</p>
          <h3>Numerical drivers and ablations</h3>
        </div>
        <span className="boundary-chip">local decomposition · never causal drivers</span>
      </div>
      <div className="longitudinal-explanation-grid reactome-contribution-grid">
        {rows.map(({ transition, item }) => (
          <article key={`${transition.id}-${item.reactomeId}-explanations`}>
            <header>
              <div>
                <b>{item.complexName}</b>
                <small>{transition.fromTimePointId} → {transition.toTimePointId}</small>
              </div>
              <strong>{formatSigned(item.score)}</strong>
            </header>
            <div className="longitudinal-driver-list">
              {item.contributions.slice(0, 4).map((contribution) => (
                <div key={`${item.reactomeId}-${contribution.geneSymbol}`}>
                  <b>{contribution.geneSymbol}</b>
                  <span>{formatSigned(contribution.contribution)}</span>
                  <small>
                    Δz {formatSigned(contribution.standardizedDelta)} · loading {formatSigned(contribution.memberLoading)} · reliability {formatNumber(contribution.reliabilityWeight)}
                  </small>
                </div>
              ))}
              {!item.contributions.length && <p>No exact observed-member contribution was rankable.</p>}
            </div>
            <div className="longitudinal-ablation-list">
              {item.ablations.map((ablation) => (
                <div key={`${item.reactomeId}-${ablation.kind}`}>
                  <b>{humanize(ablation.kind)}</b>
                  <span>Δ {formatSigned(ablation.scoreDelta)}</span>
                  <small>
                    without {formatSigned(ablation.scoreWithout)} · removed {ablation.removedMemberCount} · {ablation.support}{ablation.reason ? ` · ${ablation.reason}` : ""}
                  </small>
                </div>
              ))}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}

export function ComplexTransitionResultPanels({
  transitions,
  evaluation,
}: {
  request: JsonObject;
  transitions: ComplexTransition[];
  evaluation: ComplexEvaluationSummary | null;
}) {
  const total = complexResultCount(transitions);
  const estimated = complexEstimatedCount(transitions);
  const supported = complexSupportedCount(transitions);
  const meanCoverage = total
    ? transitions.reduce(
      (sum, transition) =>
        sum
        + transition.complexes.reduce(
          (inner, item) => inner + item.coefficientMassCoverage,
          0,
        ),
      0,
    ) / total
    : null;
  const censored = transitions.reduce(
    (sum, transition) =>
      sum
      + transition.complexes.reduce(
        (inner, item) => inner + item.leftCensoredMemberCount,
        0,
      ),
    0,
  );
  return (
    <div className="panel-stack">
      <div className="summary-grid">
        <article>
          <span>FULL SUPPORT</span><b>{supported} / {total}</b>
          <small>{estimated} estimable participant coordinates</small>
        </article>
        <article>
          <span>MEAN COEFFICIENT MASS</span><b>{percent(meanCoverage)}</b>
          <small>active fitted member evidence</small>
        </article>
        <article>
          <span>ONE-SIDED BOUNDS</span><b>{censored}</b>
          <small>censored member-pairs retained without negative imputation</small>
        </article>
        <article>
          <span>CLAIM CEILING</span><b className="warn">concordance</b>
          <small>not assembly, activity, stoichiometry, essentiality, or causality</small>
        </article>
      </div>
      <ComplexTable transitions={transitions} />
      <ExplanationPanels transitions={transitions} />
      <ComplexLockedEvaluationPanel evaluation={evaluation} />
    </div>
  );
}

export function ComplexTransitionEvidencePanel({
  request,
  transitions,
  profile,
  provenance,
}: {
  request: JsonObject;
  transitions: ComplexTransition[];
  profile: JsonObject | null;
  provenance: JsonObject | null;
}) {
  const stats = complexTransitionRequestStats(request);
  const points = arrayAt(request, ["time_points"]);
  const rows = points.flatMap((point, pointIndex) =>
    !isJsonObject(point)
      ? []
      : arrayAt(point, ["observations"]).flatMap((observation) =>
        isJsonObject(observation)
          ? [{
            pointId: textAt(point, ["time_point_id"], `T${pointIndex + 1}`),
            observation,
          }]
          : [],
      ),
  );
  const visibleRows = rows.slice(0, 256);
  const counts = profile ? objectAt(profile, ["counts"]) : null;
  const digests = profile ? objectAt(profile, ["digests"]) : null;
  return (
    <div className="panel-stack">
      <section className="result-panel zero-fill-panel">
        <div className="panel-title-row">
          <div>
            <p className="eyebrow">INTERPRETATION BOUNDARY</p>
            <h3>KNCC protein transitions on exact Reactome participant sets</h3>
          </div>
          <span className="boundary-chip">participant-set concordance · not complex activity</span>
        </div>
        <div className="zero-fill-explainer">
          <article><b>Source cohort</b><strong>{counts ? numberAt(counts, ["strict_patient_pair_count"]) ?? 104 : 104}</strong><p>Strict paired-patient PDC000514 source groups.</p></article>
          <article><b>Participant sets</b><strong>{counts ? numberAt(counts, ["complex_count"]) ?? 28 : 28}</strong><p>Repository-authored Reactome V97 sets across 11 source-paper-informed domains; outcome independence is not established.</p></article>
          <article><b>Ordered request</b><strong>{stats.timePoints}</strong><p>{stats.transitions} transitions · {stats.genes} exact gene symbols.</p></article>
          <article className="warning"><b>Active observations</b><strong>{stats.active}</strong><p>Observed plus left-censored; missing and unsupported stay non-numeric.</p></article>
        </div>
      </section>
      <section className="result-panel">
        <div className="panel-title-row"><div><p className="eyebrow">EXECUTED REQUEST</p><h3>Ordered protein evidence ledger</h3></div><span className="count-chip">{rows.length}</span></div>
        {rows.length > visibleRows.length && <p className="longitudinal-ledger-note">Showing the first {visibleRows.length} of {rows.length}; the request receipt retains every row.</p>}
        <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Time point</th><th>Observation</th><th>Gene</th><th>State</th><th>Log abundance ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
          {visibleRows.map(({ pointId, observation }, index) => <tr key={textAt(observation, ["observation_id"], String(index))}>
            <td><b>{pointId}</b></td><td>{textAt(observation, ["observation_id"], `observation-${index + 1}`)}</td><td><b>{textAt(observation, ["gene_symbol"], "—")}</b></td><td><span className="evidence-state">{textAt(observation, ["state"], "—")}</span></td><td className="mono-cell">{formatNumber(numberAt(observation, ["log_abundance"]), 3)} ± {formatNumber(numberAt(observation, ["standard_error"]), 3)}</td><td className="mono-cell">{formatNumber(numberAt(observation, ["quality_weight"]))}</td><td><code>{shortDigest(textAt(observation, ["provenance_digest"]))}</code></td>
          </tr>)}
        </tbody></table></div>
      </section>
      <section className="result-panel reactome-coverage-panel">
        <div className="panel-title-row"><div><p className="eyebrow">MEASUREMENT × FITTED-SOURCE UNCERTAINTY</p><h3>Complex-coordinate uncertainty ledger</h3></div><span className="boundary-chip">deterministic request-derived bootstrap</span></div>
        <div className="reactome-coverage-grid">
          {transitions.flatMap((transition) => transition.complexes.map((item) => <article key={`${transition.id}-${item.reactomeId}-uncertainty`}>
            <header><div><b>{item.complexName}</b><small>{transition.fromTimePointId} → {transition.toTimePointId}</small></div><span className={`support-badge ${item.support}`}>{item.support}</span></header>
            <dl>
              <div><dt>measurement SE</dt><dd>{formatNumber(item.uncertainty.measurementStandardError)}</dd></div>
              <div><dt>fitted-model SE</dt><dd>{formatNumber(item.uncertainty.fittedModelStandardError)}</dd></div>
              <div><dt>covariance</dt><dd>{formatSigned(item.uncertainty.measurementModelCovariance, 6)}</dd></div>
              <div><dt>combined SE</dt><dd>{formatNumber(item.uncertainty.combinedStandardError)}</dd></div>
            </dl>
            <small>{item.uncertainty.bootstrapReplicates} replicates · closure residual {formatNumber(item.uncertainty.varianceClosureResidual, 6)}</small>
          </article>))}
        </div>
      </section>
      <section className="result-panel reactome-provenance-panel">
        <div className="panel-title-row"><div><p className="eyebrow">CONTENT-BOUND SOURCE / MODEL</p><h3>PDC000514, Reactome V97, and fitted-factor provenance</h3></div><span className="boundary-chip">aggregate model · no patient-level rows packaged</span></div>
        <div className="mechanism-list">
          <article><div><b>Source attribution</b><span>104 paired source patients</span></div><strong>{provenance ? textAt(provenance, ["source_attribution"], "not reported") : "not reported"}</strong><small>{provenance ? arrayAt(provenance, ["source_licenses"]).filter((value): value is string => typeof value === "string").join(" · ") : "licenses not reported"}</small></article>
          <article><div><b>Reactome source catalog</b><span>release 97 · exact member sets</span></div><strong><code>{shortDigest(digests ? textAt(digests, ["source_catalog_content_digest"]) : "")}</code></strong><small>membership {shortDigest(digests ? textAt(digests, ["participant_membership_digest"]) : "")} · selection {shortDigest(digests ? textAt(digests, ["panel_selection_digest"]) : "")}</small></article>
          <article><div><b>Fitted factor model</b><span>28 robust participant coordinates</span></div><strong><code>{shortDigest(digests ? textAt(digests, ["fitted_content_digest"]) : "")}</code></strong><small>loadings {shortDigest(digests ? textAt(digests, ["reference_loading_digest"]) : "")} · ensemble {shortDigest(digests ? textAt(digests, ["bootstrap_ensemble_digest"]) : "")}</small></article>
        </div>
      </section>
    </div>
  );
}
