import {
  ReactomeTransitionEvidencePanel,
  ReactomeTransitionResultPanels,
} from "./longitudinal-gbm-reactome-transition-panels";
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
import {
  factorGraphRequestStats,
  type FactorGraphBlock,
  type FactorGraphTopology,
  type KinaseSignatureAblation,
  type KinaseTransition,
  type NormalizedFactorGraphResult,
} from "@/lib/gbm-factor-graph";

const BLOCK_ORDER: FactorGraphBlock[] = ["protein_reactome", "phosphosite_sphinks"];

function percent(value: number | null, digits = 0): string {
  return value === null ? "—" : `${(value * 100).toFixed(digits)}%`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

function interval(lower: number | null, upper: number | null): string {
  return lower === null || upper === null
    ? "interval not estimable"
    : `[${formatNumber(lower)}, ${formatNumber(upper)}]`;
}

function blockTitle(block: FactorGraphBlock): string {
  switch (block) {
    case "protein_reactome":
      return "Protein / Reactome block";
    case "phosphosite_sphinks":
      return "Phosphosite / SPHINKS block";
  }
}

function kindLabel(kind: string): string {
  switch (kind) {
    case "global_recurrence_factor":
      return "global";
    case "reactome_pathway_factor":
      return "pathway";
    case "kinase_signature_factor":
      return "kinase";
    case "subtype_signature_factor":
      return "subtype";
    case "computation_block":
      return "block";
    default:
      return "factor";
  }
}

export function FactorGraphBoundary({ result }: { result?: JsonObject | null }) {
  const provenance = result ? objectAt(result, ["provenance"]) : null;
  const noFusion = result
    ? result.cross_modal_fusion_performed === false
      && result.numerical_cross_block_edge_count === 0
      && provenance?.no_numerical_cross_block_edges === true
    : true;
  return (
    <section className="factor-graph-boundary" aria-label="No-fusion composition boundary">
      <div>
        <p className="eyebrow">COMPOSITION / PRESENTATION SURFACE · NOT AN ADDITIONAL FITTED MODEL</p>
        <h3>Two independent source-cohort concordance blocks</h3>
        <p>The protein/Reactome and phosphosite/SPHINKS children are semantically independent, are executed deterministically in sequence—not concurrently—and retain their exact child receipts. Containment lines annotate inventory only; no value, score, uncertainty, or evidence crosses between blocks.</p>
      </div>
      <dl>
        <div><dt>cross-modal fusion</dt><dd className={noFusion ? "ok" : "warn"}>{noFusion ? "not performed" : "receipt mismatch"}</dd></div>
        <div><dt>numerical cross-block edges</dt><dd className={noFusion ? "ok" : "warn"}>{result ? String(numberAt(result, ["numerical_cross_block_edge_count"]) ?? "—") : "0 maximum"}</dd></div>
        <div><dt>claim ceiling</dt><dd>independent source-cohort coordinates only</dd></div>
      </dl>
    </section>
  );
}

export function FactorGraphTopologyPanel({ topology }: { topology: FactorGraphTopology | null }) {
  if (!topology) {
    return (
      <section className="result-panel factor-topology-panel">
        <div className="panel-title-row"><div><p className="eyebrow">LOCKED ANNOTATION TOPOLOGY</p><h3>Factor inventory unavailable</h3></div><span className="support-badge abstained">fail closed</span></div>
        <p className="panel-empty">The profile did not contain the exact, internally consistent 41-node / 39-edge annotation topology. No substitute graph is drawn.</p>
      </section>
    );
  }
  const edgeByTarget = new Map(topology.containmentEdges.map((edge) => [edge.targetNodeId, edge]));
  return (
    <section className="result-panel factor-topology-panel">
      <div className="panel-title-row">
        <div><p className="eyebrow">LOCKED FACTOR INVENTORY / ANNOTATION-ONLY CONTAINMENT</p><h3>Two-block KNCC GBM factor topology</h3></div>
        <span className="boundary-chip">41 nodes · 39 containment edges · 0 cross-block edges</span>
      </div>
      <div className="factor-topology-notice">
        <b>No edge joins these columns.</b>
        <span>Each short line below means “contained in this child result block.” It has no numerical weight and never represents biological, statistical, or cross-modal coupling.</span>
      </div>
      <div className="factor-topology" data-factor-topology-id={topology.id}>
        {BLOCK_ORDER.map((block) => {
          const blockNode = topology.nodes.find((node) => node.block === block && node.kind === "computation_block");
          const factors = topology.nodes.filter((node) => node.block === block && node.kind !== "computation_block");
          return (
            <section className={`factor-block factor-block-${block}`} key={block} data-factor-block={block}>
              {blockNode && (
                <header data-factor-node-id={blockNode.id} data-factor-node-kind={blockNode.kind}>
                  <span>{blockTitle(block)}</span>
                  <b>{blockNode.label}</b>
                  <small>{blockNode.childProfileId}</small>
                </header>
              )}
              <div className="factor-node-grid">
                {factors.map((node) => {
                  const edge = edgeByTarget.get(node.id);
                  return (
                    <article key={node.id} data-factor-node-id={node.id} data-factor-node-kind={node.kind}>
                      {edge && <i data-factor-edge-id={edge.id} data-computational-role={edge.computationalRole} title="annotation-only containment; numerical weight null" />}
                      <div><span>{kindLabel(node.kind)}</span><b>{node.biologicalIdentifier}</b></div>
                      <small>{node.label}</small>
                    </article>
                  );
                })}
              </div>
            </section>
          );
        })}
      </div>
      <p className="factor-topology-digest">Topology receipt {shortDigest(topology.digest)} · annotation-only inventory; the fitted semantics live entirely inside the two child results.</p>
    </section>
  );
}

function KinaseTransitionOverview({ transitions }: { transitions: KinaseTransition[] }) {
  const allKinases = transitions.flatMap((transition) => transition.kinaseSignatures);
  const estimable = allKinases.filter((kinase) => kinase.score !== null).length;
  const selectedCore = allKinases.filter((kinase) => kinase.selectionState === "selected_core").length;
  const censoredFamilies = transitions.reduce((sum, transition) => sum + transition.censoredFamilies, 0);
  return (
    <>
      <div className="summary-grid factor-kinase-summary">
        <article><span>TRANSITIONS</span><b>{transitions.length}</b><small>consecutive phosphosite child time-point pairs</small></article>
        <article><span>ESTIMABLE SIGNATURES</span><b>{estimable} / {allKinases.length}</b><small>all estimates remain LIMITED; others explicitly abstain</small></article>
        <article><span>CORE SELECTIONS</span><b>{selectedCore}</b><small>source-fitted selection state, repeated per transition</small></article>
        <article><span>CENSORED FAMILIES</span><b>{censoredFamilies}</b><small>retained as bounds and excluded from point scores</small></article>
      </div>
      <section className="result-panel factor-kinase-timeline">
        <div className="panel-title-row"><div><p className="eyebrow">PDC000515 / SPHINKS CHILD RESULT</p><h3>Signature-transition concordance timeline</h3></div><span className="support-badge limited">source-cohort only</span></div>
        <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Transition</th><th>Coordinate</th><th>90% interval</th><th>Classification</th><th>Families</th><th>Kinases</th><th>Support</th></tr></thead><tbody>
          {transitions.map((transition) => <tr key={transition.id} data-factor-kinase-transition-id={transition.id}>
            <td><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{transition.id}</small></td>
            <td className="mono-cell"><b>{formatSigned(transition.score)}</b><small>signature coordinate only</small></td>
            <td className="mono-cell">{interval(transition.uncertainty.lower, transition.uncertainty.upper)}<small>{transition.uncertainty.bootstrapReplicates} bootstrap refits</small></td>
            <td>{humanize(transition.classification)}</td>
            <td className="mono-cell">{transition.exactFamilies.toLocaleString("en-US")}<small>{transition.censoredFamilies} censored · {transition.exactSourceRows.toLocaleString("en-US")} rows</small></td>
            <td className="mono-cell">{transition.estimableKinases} estimable<small>{transition.selectedKinases} selected / 24 fixed</small></td>
            <td><span className={`support-badge ${transition.support}`}>{transition.support}</span><small className="warning-copy">{transition.reasons[0]}</small></td>
          </tr>)}
        </tbody></table></div>
      </section>
    </>
  );
}

function KinaseSignatureTables({ transitions }: { transitions: KinaseTransition[] }) {
  return (
    <section className="result-panel factor-signature-panel">
      <div className="panel-title-row"><div><p className="eyebrow">FIXED 24-HYPOTHESIS FAMILY</p><h3>Master-kinase signature coordinates</h3></div><span className="boundary-chip">not biochemical kinase activity</span></div>
      <div className="factor-transition-stack">
        {transitions.map((transition) => <article key={transition.id}>
          <header><div><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{transition.id} · {transition.estimableKinases} estimable of 24</small></div><strong>{formatSigned(transition.score)}</strong></header>
          <div className="state-table-wrap"><table className="state-table factor-signature-table"><thead><tr><th>Kinase</th><th>Source subtype / selection</th><th>Transition coordinate</th><th>90% interval</th><th>Source enrichment / q</th><th>Coverage</th><th>Bootstrap stability</th><th>Support</th></tr></thead><tbody>
            {transition.kinaseSignatures.map((kinase) => <tr key={kinase.kinase} data-factor-kinase-signature={kinase.kinase} data-factor-kinase-transition={transition.id}>
              <td><b>{kinase.kinase}</b><small>{humanize(kinase.sourceDirection)}</small></td>
              <td>{kinase.subtype}<small>{humanize(kinase.selectionState)}</small></td>
              <td className="mono-cell"><b>{formatSigned(kinase.score)}</b><small>{humanize(kinase.classification)}</small></td>
              <td className="mono-cell">{interval(kinase.uncertainty.lower, kinase.uncertainty.upper)}<small>SE {formatNumber(kinase.uncertainty.standardError)}</small></td>
              <td className="mono-cell">{formatSigned(kinase.sourceEnrichment)}<small>p {formatNumber(kinase.sourcePValue, 4)} · q {formatNumber(kinase.sourceQValue, 4)}</small></td>
              <td className="mono-cell">{kinase.observedFamilies} / {kinase.mappedFamilies}<small>{percent(kinase.sourceWeightCoverage)} source weight</small></td>
              <td className="mono-cell">{percent(kinase.bootstrapSelectionFrequency)}<small>outer {percent(kinase.outerSelectionFrequency)} · direction {percent(kinase.bootstrapDirectionConsistency)}</small></td>
              <td><span className={`support-badge ${kinase.support}`}>{kinase.support}</span><small className="warning-copy">{kinase.reasons[0]}</small></td>
            </tr>)}
          </tbody></table></div>
        </article>)}
      </div>
    </section>
  );
}

function KinaseSubtypePanels({ transitions }: { transitions: KinaseTransition[] }) {
  return (
    <section className="result-panel factor-subtype-panel">
      <div className="panel-title-row"><div><p className="eyebrow">EQUAL KINASES WITHIN SUBTYPE / EQUAL SUBTYPES</p><h3>SPHINKS subtype signature summaries</h3></div><span className="boundary-chip">GPM · MTC · NEU · PPR are source families, not patient labels</span></div>
      <div className="factor-subtype-grid">
        {transitions.flatMap((transition) => transition.subtypeSignatures.map((subtype) => <article key={`${transition.id}-${subtype.subtype}`} data-factor-subtype={subtype.subtype}>
          <header><div><b>{subtype.subtype}</b><small>{transition.fromTimePointId} → {transition.toTimePointId}</small></div><span className={`support-badge ${subtype.support}`}>{subtype.support}</span></header>
          <strong>{formatSigned(subtype.score)}</strong>
          <p>{humanize(subtype.classification)} · {interval(subtype.uncertainty.lower, subtype.uncertainty.upper)}</p>
          <small>{subtype.estimableKinases} estimable / {subtype.selectedKinases} selected · {subtype.reasons[0]}</small>
        </article>))}
      </div>
    </section>
  );
}

const ABLATION_LABELS: Record<KinaseSignatureAblation["kind"], string> = {
  equal_kinase_instead_of_equal_subtype: "equal kinase instead of equal subtype",
  omit_composite_source_groups: "omit composite source groups",
  omit_inverse_multiplicity_correction: "omit inverse multiplicity correction",
};

function KinaseDriversAndAblations({ transitions }: { transitions: KinaseTransition[] }) {
  return (
    <section className="result-panel factor-kinase-explanation">
      <div className="panel-title-row"><div><p className="eyebrow">LOCAL NUMERICAL EXPLANATION / STRUCTURAL SENSITIVITY</p><h3>Family drivers and signature ablations</h3></div><span className="boundary-chip">never causal targets or independent evidence</span></div>
      <div className="factor-explanation-grid">
        {transitions.map((transition) => {
          const drivers = transition.kinaseSignatures.flatMap((kinase) => kinase.drivers.map((driver) => ({ kinase: kinase.kinase, driver })))
            .sort((left, right) => Math.abs(right.driver.contribution) - Math.abs(left.driver.contribution))
            .slice(0, 10);
          return <article key={transition.id}>
            <header><div><b>{transition.fromTimePointId} → {transition.toTimePointId}</b><small>{transition.id}</small></div><strong>{formatSigned(transition.score)}</strong></header>
            <div className="factor-driver-list">
              {drivers.length ? drivers.map(({ kinase, driver }, index) => <div key={`${kinase}-${driver.sourceSiteLabel}-${index}`}>
                <b>{kinase} · {driver.sourceSiteLabel}</b><span>{formatSigned(driver.contribution)}</span>
                <small>{driver.stratum} · rank {formatSigned(driver.standardizedRank)} · adjusted source weight {formatNumber(driver.adjustedSourceWeight)} · paired support {driver.pairedSourceSupport}{driver.composite ? " · indivisible composite source group" : ""}</small>
              </div>) : <p>No estimable family driver was returned.</p>}
            </div>
            <div className="factor-ablation-list">
              {transition.ablations.map((ablation) => <div key={ablation.kind} data-factor-kinase-ablation={ablation.kind}>
                <b>{ABLATION_LABELS[ablation.kind]}</b><span>Δ {formatSigned(ablation.scoreDelta)}</span>
                <small>score {formatSigned(ablation.score)} · {humanize(ablation.classification)} · {ablation.support} · {ablation.reason}</small>
              </div>)}
            </div>
          </article>;
        })}
      </div>
    </section>
  );
}

export function FactorGraphResultPanels({
  request,
  result,
  normalized,
  topology,
}: {
  request: JsonObject;
  result: JsonObject;
  normalized: NormalizedFactorGraphResult;
  topology: FactorGraphTopology | null;
}) {
  const reactomeRequest = objectAt(request, ["reactome_request"]);
  return (
    <div className="panel-stack">
      <FactorGraphBoundary result={result} />
      <FactorGraphTopologyPanel topology={topology} />
      <section className="factor-child-section factor-child-reactome" aria-label="Independent protein Reactome child result">
        <div className="factor-child-heading"><div><p className="eyebrow">CHILD BLOCK 1 / INDEPENDENT PROTEIN MODEL</p><h3>Reactome conditional-transition result family</h3></div><span>exact nested child receipt</span></div>
        {reactomeRequest ? (
          <ReactomeTransitionResultPanels request={reactomeRequest} transitions={normalized.reactomeTransitions} evaluation={null} />
        ) : <p className="panel-empty">The nested Reactome request is unavailable.</p>}
      </section>
      <section className="factor-child-section factor-child-kinase" aria-label="Independent phosphosite SPHINKS child result">
        <div className="factor-child-heading"><div><p className="eyebrow">CHILD BLOCK 2 / INDEPENDENT PHOSPHOSITE MODEL</p><h3>SPHINKS kinase-transition result family</h3></div><span>exact nested child receipt</span></div>
        <KinaseTransitionOverview transitions={normalized.kinaseTransitions} />
        <KinaseSignatureTables transitions={normalized.kinaseTransitions} />
        <KinaseSubtypePanels transitions={normalized.kinaseTransitions} />
        <KinaseDriversAndAblations transitions={normalized.kinaseTransitions} />
      </section>
    </div>
  );
}

function KinaseRequestLedger({ request }: { request: JsonObject }) {
  const points = arrayAt(request, ["time_points"]);
  const rows = points.flatMap((point, pointIndex) => !isJsonObject(point)
    ? []
    : arrayAt(point, ["observations"]).flatMap((observation) => isJsonObject(observation)
      ? [{ pointId: textAt(point, ["time_point_id"], `T${pointIndex + 1}`), observation }]
      : []));
  const visibleRows = rows.slice(0, 256);
  const assay = objectAt(request, ["assay_compatibility"]);
  const reference = objectAt(request, ["normalization_reference"]);
  return (
    <div className="panel-stack">
      <section className="result-panel">
        <div className="panel-title-row"><div><p className="eyebrow">EXECUTED KINASE CHILD REQUEST</p><h3>Exact phosphosite evidence ledger</h3></div><span className="count-chip">{rows.length}</span></div>
        {rows.length > visibleRows.length && <p className="longitudinal-ledger-note">Showing the first {visibleRows.length} of {rows.length} rows; the request download retains every observation.</p>}
        <div className="state-table-wrap"><table className="state-table"><thead><tr><th>Time point</th><th>Observation</th><th>Exact site group</th><th>Gene</th><th>State</th><th>Log2 ratio ± SE</th><th>Quality</th><th>Provenance</th></tr></thead><tbody>
          {visibleRows.map(({ pointId, observation }, index) => <tr key={textAt(observation, ["observation_id"], String(index))} data-factor-kinase-observation>
            <td><b>{pointId}</b></td>
            <td>{textAt(observation, ["observation_id"], `observation-${index + 1}`)}</td>
            <td><b>{textAt(observation, ["phosphosite_id"], "—")}</b></td>
            <td>{textAt(observation, ["gene_symbol"], "—")}</td>
            <td><span className="evidence-state">{textAt(observation, ["state"], "—")}</span></td>
            <td className="mono-cell">{formatNumber(numberAt(observation, ["log_abundance_ratio"]), 3)} ± {formatNumber(numberAt(observation, ["standard_error"]), 3)}</td>
            <td className="mono-cell">{formatNumber(numberAt(observation, ["quality_weight"]))}</td>
            <td><code>{shortDigest(textAt(observation, ["provenance_digest"]))}</code></td>
          </tr>)}
        </tbody></table></div>
      </section>
      <section className="mechanism-grid">
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">PDC000515 FITTED SCALE</p><h3>Phosphoproteome compatibility</h3></div></div>{assay ? <pre>{JSON.stringify(assay, null, 2)}</pre> : <p className="panel-empty">No attestation was supplied.</p>}</section>
        <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">INVARIANT PREPROCESSING</p><h3>Kinase child normalization reference</h3></div></div>{reference ? <pre>{JSON.stringify(reference, null, 2)}</pre> : <p className="panel-empty">No normalization reference was supplied.</p>}</section>
      </section>
    </div>
  );
}

export function FactorGraphEvidencePanels({
  request,
  result,
  normalized,
}: {
  request: JsonObject;
  result: JsonObject;
  normalized: NormalizedFactorGraphResult;
}) {
  const reactomeRequest = objectAt(request, ["reactome_request"]);
  const kinaseRequest = objectAt(request, ["kinase_request"]);
  const stats = factorGraphRequestStats(request);
  return (
    <div className="panel-stack">
      <FactorGraphBoundary result={result} />
      <section className="result-panel factor-child-request-summary">
        <div className="panel-title-row"><div><p className="eyebrow">TWO INDEPENDENT EXECUTED CHILD REQUESTS</p><h3>Evidence remains assay-specific</h3></div><span className="boundary-chip">no shared feature matrix · no cross-assay normalization</span></div>
        <div className="zero-fill-explainer">
          <article><b>Reactome child</b><strong>{stats.reactomeTimePoints}</strong><p>protein time points · {stats.reactomeActive.toLocaleString("en-US")} active protein observations · PDC000514 source-fitted coordinates.</p></article>
          <article><b>SPHINKS child</b><strong>{stats.kinaseTimePoints}</strong><p>phosphosite time points · {stats.kinaseActive.toLocaleString("en-US")} active exact source-site observations · PDC000515 source-fitted coordinates.</p></article>
          <article className="warning"><b>Composition boundary</b><strong>0</strong><p>numerical cross-block edges. Different point counts and assays remain independent; neither child supplies evidence to the other.</p></article>
        </div>
      </section>
      {reactomeRequest && (
        <section className="factor-child-section factor-child-reactome" aria-label="Independent Reactome child evidence">
          <div className="factor-child-heading"><div><p className="eyebrow">CHILD BLOCK 1 / PROTEIN EVIDENCE</p><h3>Reactome input and result provenance</h3></div><span>PDC000514 · source-cohort only</span></div>
          <ReactomeTransitionEvidencePanel
            request={reactomeRequest}
            transitions={normalized.reactomeTransitions}
            profile={null}
            provenance={objectAt(normalized.reactomeResult, ["provenance"])}
          />
        </section>
      )}
      {kinaseRequest && (
        <section className="factor-child-section factor-child-kinase" aria-label="Independent SPHINKS child evidence">
          <div className="factor-child-heading"><div><p className="eyebrow">CHILD BLOCK 2 / PHOSPHOSITE EVIDENCE</p><h3>SPHINKS input and result provenance</h3></div><span>PDC000515 · same source cohort · not independent validation</span></div>
          <KinaseRequestLedger request={kinaseRequest} />
          <KinaseDriversAndAblations transitions={normalized.kinaseTransitions} />
          <section className="result-panel json-panel"><div className="panel-title-row"><div><p className="eyebrow">EXACT NESTED CHILD RECEIPT</p><h3>Kinase-transition provenance</h3></div></div><pre>{JSON.stringify(objectAt(normalized.kinaseResult, ["provenance"]), null, 2)}</pre></section>
        </section>
      )}
    </div>
  );
}
