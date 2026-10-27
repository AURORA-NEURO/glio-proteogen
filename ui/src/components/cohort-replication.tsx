"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import {
  assertReplicationBinding, cohortLabel, effectFor, forestDomain, formatEffect, formatProbability,
  parseReplicationProfile, parseReplicationRequest, parseReplicationResult, parseReplicationVerification,
  replicationFetch, replicationReplayEnvelope, REPLICATION_INPUT_LIMIT, shortReceipt,
  type PooledEffect, type ReplicationCohort, type ReplicationFeature, type ReplicationProfile,
  type ReplicationRequest, type ReplicationResult, type ReplicationVerification,
} from "@/lib/cohort-replication";
import styles from "./cohort-replication.module.css";

type Source = "synthetic_demonstration" | "caller_supplied";
type Run = { request: ReplicationRequest; result: ReplicationResult; source: Source; verified: ReplicationVerification };
type Phase = "idle" | "loading" | "analyzing" | "verifying";

const TONE = { positive: "#6bd9bd", negative: "#dfb27e", missing: "#27333e" };
const sourceLabel = (source: Source) => source === "synthetic_demonstration" ? "Synthetic demonstration" : "Imported / caller-owned summaries";

function Arrow({ direction = "right" }: { direction?: "right" | "left" }) {
  return <span aria-hidden="true">{direction === "left" ? "↖" : "↗"}</span>;
}

function PanelHeading({ index, title, caption, aside }: { index: string; title: string; caption?: string; aside?: React.ReactNode }) {
  return <div className={styles.panelHeading}><div><span className={styles.sectionIndex}>{index}</span><h2>{title}</h2>{caption ? <p>{caption}</p> : null}</div>{aside}</div>;
}

function TickAxis({ domain, x, y, start = 0, end = 1 }: { domain: [number, number]; x: (value: number) => number; y: number; start?: number; end?: number }) {
  return <g className={styles.axis}>{Array.from({ length: 5 }, (_, i) => domain[0] + (domain[1] - domain[0]) * (start + (end - start) * i / 4)).map((tick) => <g key={tick}><line x1={x(tick)} x2={x(tick)} y1={y - 4} y2={y} /><text x={x(tick)} y={y + 19} textAnchor="middle">{formatEffect(tick)}</text></g>)}</g>;
}

function Interval({ estimate, x, y, pooled = false, color = TONE.positive }: { estimate: PooledEffect; x: (value: number) => number; y: number; pooled?: boolean; color?: string }) {
  return <g style={{ color }}><line x1={x(estimate.lower)} x2={x(estimate.upper)} y1={y} y2={y} stroke="currentColor" strokeWidth={pooled ? 2 : 1.5} />{pooled ? <polygon points={`${x(estimate.lower)},${y} ${x(estimate.estimate)},${y - 7} ${x(estimate.upper)},${y} ${x(estimate.estimate)},${y + 7}`} fill="currentColor" opacity=".85" /> : <><line x1={x(estimate.lower)} x2={x(estimate.lower)} y1={y - 4} y2={y + 4} stroke="currentColor" /><line x1={x(estimate.upper)} x2={x(estimate.upper)} y1={y - 4} y2={y + 4} stroke="currentColor" /><rect x={x(estimate.estimate) - 4.5} y={y - 4.5} width={9} height={9} fill="currentColor" /></>}</g>;
}

function ForestPlot({ feature, cohorts, effectScale }: { feature: ReplicationFeature; cohorts: ReplicationCohort[]; effectScale: string }) {
  const domain = forestDomain(feature);
  const x = (value: number) => 218 + (value - domain[0]) / (domain[1] - domain[0]) * 335;
  const height = 150 + cohorts.length * 43 + (feature.prediction_interval ? 36 : 0);
  const pooledY = 44 + cohorts.length * 43;
  return <div className={styles.forestWrap}>
    <svg viewBox={`0 0 730 ${height}`} className={styles.forest} role="img" aria-labelledby="replication-forest-title replication-forest-description">
      <title id="replication-forest-title">Cohort effects and pooled estimates for {feature.label}</title>
      <desc id="replication-forest-description">Horizontal intervals show nominal 95% confidence intervals. Missing and unsupported measurements have no numerical mark. Diamonds are pooled estimates. The dotted amber interval is an approximate prediction interval.</desc>
      <text x={0} y={17} className={styles.svgEyebrow}>COHORT / ESTIMATOR</text><text x={712} y={17} textAnchor="end" className={styles.svgEyebrow}>EFFECT [95% CI]</text>
      <line x1={x(0)} x2={x(0)} y1={27} y2={height - 43} className={styles.zeroLine} />
      {cohorts.map((cohort, index) => {
        const effect = effectFor(feature, cohort.cohort_id); const y = 47 + index * 43;
        const observed = effect?.state === "observed" && typeof effect.estimate === "number" && typeof effect.standard_error === "number";
        const estimate = observed ? { estimate: effect.estimate!, standard_error: effect.standard_error!, lower: effect.estimate! - 1.959963984540054 * effect.standard_error!, upper: effect.estimate! + 1.959963984540054 * effect.standard_error!, p_value: 0 } : null;
        return <g key={cohort.cohort_id}><line x1={0} x2={730} y1={y + 20} y2={y + 20} className={styles.rowRule} /><text x={0} y={y + 4} className={styles.svgLabel}>{cohortLabel(cohort).slice(0, 28)}</text>{estimate ? <><Interval estimate={estimate} x={x} y={y} color={estimate.estimate < 0 ? TONE.negative : TONE.positive} /><text x={712} y={y + 4} textAnchor="end" className={styles.svgNumber}>{formatEffect(estimate.estimate)} [{formatEffect(estimate.lower)}, {formatEffect(estimate.upper)}]</text></> : <text x={712} y={y + 4} textAnchor="end" className={styles.svgMissing}>{(effect?.state ?? "missing").replaceAll("_", " ")}</text>}</g>;
      })}
      {[{ name: "Fixed effect", estimate: feature.fixed_effect, y: pooledY }, { name: "Random effects", estimate: feature.random_effect, y: pooledY + 33 }].map(({ name, estimate, y }) => <g key={name}><text x={0} y={y + 4} className={styles.svgPooledLabel}>{name}</text>{estimate ? <><Interval estimate={estimate} x={x} y={y} pooled color={name === "Fixed effect" ? "#8b9ba9" : TONE.positive} /><text x={712} y={y + 4} textAnchor="end" className={styles.svgNumber}>{formatEffect(estimate.estimate)} [{formatEffect(estimate.lower)}, {formatEffect(estimate.upper)}]</text></> : <text x={712} y={y + 4} textAnchor="end" className={styles.svgMissing}>Abstained</text>}</g>)}
      {feature.prediction_interval ? <g><text x={0} y={pooledY + 70} className={styles.svgMuted}>Approx. prediction interval</text><line x1={x(feature.prediction_interval.lower)} x2={x(feature.prediction_interval.upper)} y1={pooledY + 66} y2={pooledY + 66} className={styles.predictionLine} /><text x={712} y={pooledY + 70} textAnchor="end" className={styles.svgNumber}>[{formatEffect(feature.prediction_interval.lower)}, {formatEffect(feature.prediction_interval.upper)}]</text></g> : null}
      <TickAxis domain={domain} x={x} y={height - 35} />
    </svg>
    <div className={styles.plotLegend}><span><i style={{ background: TONE.positive }} />Positive estimate</span><span><i style={{ background: TONE.negative }} />Negative estimate</span><span className={styles.scaleLabel}>{effectScale.replaceAll("_", " ")} · null = 0</span></div>
    <details className={styles.dataDetails}><summary>View accessible numerical table</summary><div className={styles.tableScroll}><table><caption>Cohort effects for {feature.label}; intervals are nominal 95% CIs</caption><thead><tr><th>Cohort</th><th>State</th><th>Estimate</th><th>SE</th><th>Lower CI</th><th>Upper CI</th></tr></thead><tbody>{cohorts.map((cohort) => { const e = effectFor(feature, cohort.cohort_id); const observed = e?.state === "observed"; return <tr key={cohort.cohort_id}><th>{cohortLabel(cohort)}</th><td>{e?.state ?? "missing"}</td><td>{observed ? formatEffect(e.estimate) : "—"}</td><td>{observed ? e.standard_error?.toFixed(3) : "—"}</td><td>{observed ? formatEffect(e.estimate! - 1.959963984540054 * e.standard_error!) : "—"}</td><td>{observed ? formatEffect(e.estimate! + 1.959963984540054 * e.standard_error!) : "—"}</td></tr>; })}{[{ label: "Fixed effect", e: feature.fixed_effect }, { label: "Random effects", e: feature.random_effect }].map(({ label, e }) => <tr key={label}><th>{label}</th><td>{e ? "pooled" : "abstained"}</td><td>{formatEffect(e?.estimate)}</td><td>{e?.standard_error.toFixed(3) ?? "—"}</td><td>{formatEffect(e?.lower)}</td><td>{formatEffect(e?.upper)}</td></tr>)}</tbody></table></div></details>
  </div>;
}

function CoverageMatrix({ features, cohorts, selected, onSelect }: { features: ReplicationFeature[]; cohorts: ReplicationCohort[]; selected: string; onSelect: (id: string) => void }) {
  const max = Math.max(0.25, ...features.flatMap((f) => f.effects.filter((e) => e.state === "observed").map((e) => Math.abs(e.estimate ?? 0))));
  return <div className={styles.matrixScroll}><table className={styles.matrix}><caption className={styles.srOnly}>Feature by cohort coverage and direction. Select a feature to update all linked plots.</caption><thead><tr><th>FEATURE</th>{cohorts.map((cohort) => <th key={cohort.cohort_id} title={cohortLabel(cohort)}>{cohort.cohort_id}</th>)}<th>OBSERVED</th><th>BH q</th><th>BY q</th></tr></thead><tbody>{features.map((feature) => <tr key={feature.feature_id} className={selected === feature.feature_id ? styles.selectedRow : ""}><th><button type="button" onClick={() => onSelect(feature.feature_id)} aria-pressed={selected === feature.feature_id}><span>{feature.label}</span><small>{feature.feature_id}</small></button></th>{cohorts.map((cohort) => { const effect = effectFor(feature, cohort.cohort_id); const observed = effect?.state === "observed"; const value = observed ? effect.estimate ?? 0 : null; const state = effect?.state ?? "missing"; return <td key={cohort.cohort_id}><button type="button" onClick={() => onSelect(feature.feature_id)} aria-label={`${feature.label}, ${cohortLabel(cohort)}: ${observed ? `effect ${formatEffect(value)}` : state}`} title={`${cohortLabel(cohort)} · ${observed ? `effect ${formatEffect(value)}, SE ${effect?.standard_error?.toFixed(3)}` : `${state}${effect?.reason ? `: ${effect.reason}` : ""}`}`} className={`${styles.matrixCell} ${observed ? "" : styles.missingCell}`} style={observed ? { background: value === 0 ? "rgba(175,195,205,.16)" : value! > 0 ? `rgba(107,217,189,${.18 + .65 * Math.abs(value!) / max})` : `rgba(223,178,126,${.18 + .65 * Math.abs(value!) / max})` } : undefined}>{observed ? value === 0 ? "0" : formatEffect(value) : state === "unsupported" ? "×" : "—"}</button></td>; })}<td className={styles.coverageCount}>{feature.observed_count}<span>/{feature.total_count}</span></td><td className={styles.qValue}>{formatProbability(feature.adjusted_p_value)}</td><td className={styles.qValue}>{formatProbability(feature.dependence_robust_adjusted_p_value)}</td></tr>)}</tbody></table>{features.length === 0 ? <p className={styles.noMatches}>No features match the current search and coverage filter.</p> : null}</div>;
}

function HeterogeneityPlot({ features, selected, onSelect }: { features: ReplicationFeature[]; selected: string; onSelect: (id: string) => void }) {
  const admitted = features.filter((feature) => feature.random_effect && feature.heterogeneity);
  const maxPrecision = Math.max(1, ...admitted.map((feature) => 1 / feature.random_effect!.standard_error));
  const x = (precision: number) => 49 + precision / maxPrecision * 380;
  const y = (iSquared: number) => 224 - iSquared / 100 * 180;
  return <><svg viewBox="0 0 480 280" className={styles.scatter} role="img" aria-labelledby="replication-heterogeneity-title"><title id="replication-heterogeneity-title">Heterogeneity and precision overview. Use the feature list or matrix to change selection.</title>{[0, 25, 50, 75, 100].map((tick) => <g key={tick}><line x1={49} x2={440} y1={y(tick)} y2={y(tick)} className={styles.gridLine} /><text x={37} y={y(tick) + 4} textAnchor="end" className={styles.svgMuted}>{tick}%</text></g>)}<text x={49} y={22} className={styles.svgEyebrow}>HETEROGENEITY · I²</text><text x={440} y={267} textAnchor="end" className={styles.svgMuted}>Precision (1 / pooled SE) →</text>{admitted.map((feature) => <g key={feature.feature_id} role="button" tabIndex={0} aria-label={`Select ${feature.label}, I squared ${feature.heterogeneity!.i_squared_percent.toFixed(1)} percent`} onClick={() => onSelect(feature.feature_id)} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(feature.feature_id); } }} className={styles.scatterPoint}><title>{feature.label}: I² {feature.heterogeneity!.i_squared_percent.toFixed(1)}%, precision {(1 / feature.random_effect!.standard_error).toFixed(2)}</title>{selected === feature.feature_id ? <circle cx={x(1 / feature.random_effect!.standard_error)} cy={y(feature.heterogeneity!.i_squared_percent)} r={13} fill="none" stroke={TONE.positive} opacity=".5" /> : null}<circle cx={x(1 / feature.random_effect!.standard_error)} cy={y(feature.heterogeneity!.i_squared_percent)} r={selected === feature.feature_id ? 6 : 5} fill={feature.random_effect!.estimate < 0 ? TONE.negative : TONE.positive} opacity={selected === feature.feature_id ? 1 : .55} />{selected === feature.feature_id ? <text x={Math.min(350, x(1 / feature.random_effect!.standard_error) + 15)} y={Math.max(39, y(feature.heterogeneity!.i_squared_percent) - 14)} className={styles.svgSelected}>{feature.label}</text> : null}</g>)}{admitted.length === 0 ? <text x={240} y={135} textAnchor="middle" className={styles.svgMuted}>No estimable feature pairs.</text> : null}</svg><p className={styles.chartNote}>Precision and I² describe the submitted summaries. They do not establish transportability or control confounding.</p></>;
}

function LeaveOneOut({ feature, cohorts }: { feature: ReplicationFeature; cohorts: ReplicationCohort[] }) {
  const domain = forestDomain(feature); const x = (value: number) => 190 + (value - domain[0]) / (domain[1] - domain[0]) * 255;
  const height = Math.max(130, feature.leave_one_out.length * 37 + 66);
  return <><svg viewBox={`0 0 520 ${height}`} className={styles.loco} role="img" aria-labelledby="replication-loco-title"><title id="replication-loco-title">Leave-one-cohort-out sensitivity for {feature.label}. Each row refits random effects after omitting one observed cohort.</title><line x1={x(0)} x2={x(0)} y1={15} y2={height - 34} className={styles.zeroLine} />{feature.random_effect ? <line x1={x(feature.random_effect.estimate)} x2={x(feature.random_effect.estimate)} y1={15} y2={height - 34} className={styles.referenceLine} /> : null}{feature.leave_one_out.map((entry, index) => { const y = 30 + index * 37; return <g key={entry.omitted_cohort_id}><text x={0} y={y + 4} className={styles.svgLabel}>− {cohortLabel(cohorts.find((c) => c.cohort_id === entry.omitted_cohort_id) ?? { cohort_id: entry.omitted_cohort_id }).slice(0, 23)}</text>{entry.random_effect ? <><Interval estimate={entry.random_effect} x={x} y={y} /><text x={510} y={y + 4} textAnchor="end" className={styles.svgNumber}>{formatEffect(entry.delta_estimate)}</text></> : <text x={510} y={y + 4} textAnchor="end" className={styles.svgMissing}>Abstained</text>}</g>; })}{feature.leave_one_out.length === 0 ? <text x={260} y={66} textAnchor="middle" className={styles.svgMuted}>No leave-one-out estimates available.</text> : null}<TickAxis domain={domain} x={x} y={height - 29} /></svg><div className={styles.plotLegend}><span><i style={{ background: TONE.positive }} />95% CI after omission</span><span className={styles.scaleLabel}>Right column: Δ from full estimate</span></div><details className={styles.dataDetails}><summary>View sensitivity values</summary><div className={styles.tableScroll}><table><thead><tr><th>Omitted cohort</th><th>Remaining</th><th>Estimate</th><th>95% CI</th><th>Δ</th></tr></thead><tbody>{feature.leave_one_out.map((entry) => <tr key={entry.omitted_cohort_id}><th>{entry.omitted_cohort_id}</th><td>{entry.observed_count}</td><td>{formatEffect(entry.random_effect?.estimate)}</td><td>{entry.random_effect ? `[${formatEffect(entry.random_effect.lower)}, ${formatEffect(entry.random_effect.upper)}]` : "abstained"}</td><td>{formatEffect(entry.delta_estimate)}</td></tr>)}</tbody></table></div></details></>;
}

function downloadJson(value: unknown, name: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }));
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = name; document.body.appendChild(anchor); anchor.click(); anchor.remove(); setTimeout(() => URL.revokeObjectURL(url), 0);
}

export default function CohortReplication() {
  const [profile, setProfile] = useState<ReplicationProfile | null>(null);
  const [editor, setEditor] = useState("");
  const [source, setSource] = useState<Source>("synthetic_demonstration");
  const [sourceName, setSourceName] = useState("Synthetic service demonstration");
  const [run, setRun] = useState<Run | null>(null);
  const [phase, setPhase] = useState<Phase>("loading");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [query, setQuery] = useState("");
  const [coverageFilter, setCoverageFilter] = useState("all");
  const [selectedId, setSelectedId] = useState("");
  const [editorOpen, setEditorOpen] = useState(false);
  const [provenanceOpen, setProvenanceOpen] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [verifyStatus, setVerifyStatus] = useState("");
  const epoch = useRef(0); const controller = useRef<AbortController | null>(null); const fileInput = useRef<HTMLInputElement | null>(null);

  const reset = useCallback(() => { epoch.current += 1; controller.current?.abort(); controller.current = null; setRun(null); setVerifyStatus(""); setError(""); setNotice(""); setPhase("idle"); return epoch.current; }, []);

  const analyze = useCallback(async (request: ReplicationRequest, activeSource: Source, activeProfile: ReplicationProfile, token: number, signal: AbortSignal) => {
    setPhase("analyzing");
    const result = parseReplicationResult(await replicationFetch("analyze", signal, request));
    if (token !== epoch.current) return;
    assertReplicationBinding(request, activeProfile, result);
    setPhase("verifying");
    const verified = parseReplicationVerification(await replicationFetch("verify", signal, { request, result }), result);
    if (!verified.valid) throw new Error("Deterministic replay failed. The result has been withheld.");
    if (token !== epoch.current) return;
    setRun({ request, result, source: activeSource, verified }); setSelectedId((result.features.find((feature) => feature.random_effect) ?? result.features[0])?.feature_id ?? ""); setVerifyStatus("Replay verified"); setPhase("idle"); setNotice("Analysis complete. Linked views reflect the same verified service result.");
  }, []);

  const loadDemo = useCallback(async () => {
    const token = reset(); const nextController = new AbortController(); controller.current = nextController; setPhase("loading"); setSource("synthetic_demonstration"); setSourceName("Synthetic service demonstration"); setEditor("");
    setQuery(""); setCoverageFilter("all");
    try {
      const [nextProfile, request] = await Promise.all([replicationFetch("profile", nextController.signal), replicationFetch("demo", nextController.signal)]);
      if (token !== epoch.current) return;
      const admitted = parseReplicationProfile(nextProfile);
      parseReplicationRequest(JSON.stringify(request)); setProfile(admitted); setEditor(JSON.stringify(request, null, 2));
      await analyze(request, "synthetic_demonstration", admitted, token, nextController.signal);
    } catch (cause) { if (token === epoch.current && !nextController.signal.aborted) { setError(cause instanceof Error ? cause.message : "Unable to load the service demonstration."); setPhase("idle"); } }
  }, [reset, analyze]);

  useEffect(() => { void loadDemo(); return () => { epoch.current += 1; controller.current?.abort(); }; }, [loadDemo]);

  const runAnalysis = async () => {
    const token = reset(); const nextController = new AbortController(); controller.current = nextController;
    try {
      const request = parseReplicationRequest(editor); setPhase("loading");
      const nextProfile = await replicationFetch("profile", nextController.signal);
      if (token !== epoch.current) return;
      const admitted = parseReplicationProfile(nextProfile); setProfile(admitted); await analyze(request, source, admitted, token, nextController.signal);
    } catch (cause) { if (token === epoch.current && !nextController.signal.aborted) { setError(cause instanceof Error ? cause.message : "Unable to analyze this request."); setPhase("idle"); } }
  };

  const importFile = async (file: File | undefined) => {
    if (!file) return;
    const token = reset(); setSource("caller_supplied"); setSourceName(file.name.slice(0, 140)); setEditor(""); setPhase("loading");
    setQuery(""); setCoverageFilter("all");
    try {
      if (file.size > REPLICATION_INPUT_LIMIT) throw new Error("Choose a JSON request no larger than 2 MiB.");
      const text = await file.text(); if (token !== epoch.current) return; parseReplicationRequest(text); setEditor(text); setEditorOpen(true); setNotice("Imported request ready. Confirm the cohort independence declaration, then analyze.");
    } catch (cause) { if (token === epoch.current) setError(cause instanceof Error ? cause.message : "Unable to read the input file."); }
    finally { if (token === epoch.current) setPhase("idle"); if (fileInput.current) fileInput.current.value = ""; }
  };

  const onEditorChange = (event: ChangeEvent<HTMLTextAreaElement>) => {
    reset(); setSource("caller_supplied"); setSourceName("Edited request"); setEditor(event.target.value); setNotice("Input changed. Previous results were cleared; analyze to refresh the linked views.");
  };

  const verifyReplay = async () => {
    if (!run) return;
    const frozen = run; const token = epoch.current; const nextController = new AbortController(); controller.current?.abort(); controller.current = nextController; setPhase("verifying"); setError(""); setVerifyStatus("");
    try {
      const verified = parseReplicationVerification(await replicationFetch("verify", nextController.signal, { request: frozen.request, result: frozen.result }), frozen.result);
      if (token !== epoch.current) return;
      if (!verified.valid) { setRun(null); throw new Error("Replay did not reproduce the result. Charts were cleared."); }
      setRun({ ...frozen, verified }); setVerifyStatus("Replay verified again"); setNotice("The service reproduced this request and result. Replay checks consistency; it does not validate the study design.");
    } catch (cause) { if (token === epoch.current && !nextController.signal.aborted) { setRun(null); setError(cause instanceof Error ? cause.message : "Replay could not be verified. Charts were cleared."); } }
    finally { if (token === epoch.current) setPhase("idle"); }
  };

  const result = run?.result; const busy = phase !== "idle";
  const features = useMemo(() => (result?.features ?? []).filter((feature) => `${feature.label} ${feature.feature_id}`.toLowerCase().includes(query.toLowerCase()) && (coverageFilter === "all" || (coverageFilter === "complete" ? feature.observed_count === feature.total_count : feature.observed_count < feature.total_count))), [result, query, coverageFilter]);
  const selected = result?.features.find((feature) => feature.feature_id === selectedId) ?? result?.features[0];
  const observedCells = result?.features.reduce((sum, feature) => sum + feature.observed_count, 0) ?? 0;
  const totalCells = (result?.features.length ?? 0) * (result?.cohorts.length ?? 0);
  const missingCells = totalCells - observedCells;
  const incompleteFeatures = result?.features.filter((feature) => feature.observed_count < feature.total_count).length ?? 0;
  const phaseLabel = phase === "loading" ? "Reading source contract" : phase === "analyzing" ? "Computing cohort synthesis" : phase === "verifying" ? "Verifying deterministic replay" : "Ready for analysis";

  return <main className={styles.observatory}>
    <div className={styles.ambient} aria-hidden="true" />
    <header className={styles.topbar}><a href="/" className={styles.brand}><span className={styles.brandMark}>g<span>p</span></span><span>GLIO<span className={styles.brandSlash}> / </span>PROTEOGEN<small>RESEARCH OBSERVATORY</small></span></a><nav aria-label="Primary navigation"><a href="/">Workbench <Arrow direction="left" /></a><a href="#source">Source & contract</a><span className={styles.researchTag}><i />Research use only</span></nav></header>
    <section className={styles.hero} aria-labelledby="replication-heading"><div><div className={styles.eyebrow}><span>REPLICATION LAB</span><span className={styles.eyebrowRule} />CROSS-COHORT EVIDENCE</div><h1 id="replication-heading">Does the signal<br /><em>travel?</em></h1><p>One signal. Independent cohorts. A transparent view of effect, uncertainty, and the evidence that fails to carry across.</p><div className={styles.heroMeta}><span>01 / CROSS-COHORT REPLICATION</span><span>SUMMARY-STATISTIC SYNTHESIS</span></div></div><div className={styles.heroDiagram} aria-hidden="true"><svg viewBox="0 0 420 255"><defs><linearGradient id="replication-hero-gradient" x1="0" x2="1"><stop offset="0%" stopColor="#6bd9bd" stopOpacity=".1" /><stop offset="100%" stopColor="#6bd9bd" stopOpacity=".8" /></linearGradient></defs>{[53, 100, 147, 194].map((y, i) => <g key={y}><path d={`M 48 ${y} C 160 ${y}, 188 127, 310 127`} fill="none" stroke="url(#replication-hero-gradient)" strokeWidth="1.3" /><circle cx="48" cy={y} r="15" fill="#102b2c" stroke="#6bd9bd" strokeOpacity=".45" /><text x="48" y={y + 4} textAnchor="middle" fill="#a7d7cd" fontSize="9">C{i + 1}</text></g>)}<circle cx="315" cy="127" r="46" fill="#122526" stroke="#6bd9bd" strokeOpacity=".6" /><circle cx="315" cy="127" r="62" fill="none" stroke="#6bd9bd" strokeOpacity=".1" strokeDasharray="3 6" /><line x1="286" x2="344" y1="127" y2="127" stroke="#6bd9bd" /><polygon points="299,127 315,116 331,127 315,138" fill="#6bd9bd" /><text x="315" y="219" textAnchor="middle" fill="#829d9d" fontSize="8" letterSpacing="2">SHARED EFFECT · HONEST UNCERTAINTY</text></svg><span>Independent inputs → pooled estimate</span></div></section>

    <section id="source" className={styles.sourceBar} onDragOver={(event) => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={(event) => { event.preventDefault(); setDragging(false); void importFile(event.dataTransfer.files[0]); }} data-dragging={dragging} aria-label="Analysis source">
      <div className={styles.sourceIdentity}><span className={`${styles.sourceBadge} ${source === "caller_supplied" ? styles.importBadge : ""}`}>{source === "synthetic_demonstration" ? "SYNTHETIC" : "CALLER SUPPLIED"}</span><div><strong>{sourceLabel(source)}</strong><p>{sourceName} <span>· no participant-level data</span></p></div></div>
      <div className={styles.sourceActions}><button type="button" onClick={() => void loadDemo()} disabled={busy}>Load demo</button><button type="button" onClick={() => fileInput.current?.click()} disabled={busy}>Import JSON <span aria-hidden="true">↑</span></button><button type="button" onClick={() => setEditorOpen(!editorOpen)} aria-expanded={editorOpen}>{editorOpen ? "Close" : "Edit"} request <span aria-hidden="true">{editorOpen ? "−" : "+"}</span></button><button type="button" className={styles.primaryButton} onClick={() => void runAnalysis()} disabled={busy || !editor.trim()}>{busy ? <span className={styles.spinner} /> : null}{busy ? "Working" : "Analyze"}<span aria-hidden="true">→</span></button></div>
      <input ref={fileInput} className={styles.srOnly} type="file" accept=".json,application/json" onChange={(event) => void importFile(event.target.files?.[0])} aria-label="Import a cross-cohort request JSON file" />
      {dragging ? <div className={styles.dropOverlay}>Drop a request JSON · maximum 2 MiB</div> : null}
    </section>

    {editorOpen ? <section className={styles.editorPanel}><div><h2>The submitted contract</h2><p>Caller-owned, compatible effect estimates and standard errors; declared independent cohorts. Missing and unsupported states stay explicit. Maximum input: 2 MiB.</p><button type="button" onClick={() => { try { setEditor(JSON.stringify(parseReplicationRequest(editor), null, 2)); setError(""); } catch (cause) { setError(cause instanceof Error ? cause.message : "Invalid JSON."); } }}>Format JSON</button></div><textarea aria-label="Cross-cohort request JSON" value={editor} onChange={onEditorChange} spellCheck={false} wrap="off" maxLength={REPLICATION_INPUT_LIMIT} /><p className={styles.editorFootnote}>Editing a request clears its existing result. Import source ownership and cohort independence remain the caller&apos;s responsibility.</p></section> : null}
    <div className={styles.statusArea} aria-live="polite">{error ? <div className={styles.errorBox} role="alert"><b>Analysis unavailable</b><p>{error}</p><span>Check the service connection and request contract, then retry.</span></div> : busy ? <p className={styles.loadingStatus}><span className={styles.spinner} />{phaseLabel}<span className={styles.loadingLine} /><button type="button" className={styles.cancelButton} onClick={() => { reset(); setNotice("Operation cancelled. Current input is preserved; no result is active."); }}>Cancel</button></p> : notice ? <p className={styles.notice}><span>✓</span>{notice}</p> : null}</div>

    {result && selected ? <>
      <section className={styles.metrics} aria-label="Analysis overview"><article><span>INDEPENDENT COHORTS</span><strong>{result.cohorts.length.toString().padStart(2, "0")}</strong><p>Declared by the input source</p></article><article><span>PREDECLARED FEATURES</span><strong>{result.family_size.toString().padStart(2, "0")}</strong><p>One BH / BY multiplicity family</p></article><article><span>OBSERVED SUMMARIES</span><strong>{observedCells}<small> / {totalCells}</small></strong><p>{totalCells ? (100 * observedCells / totalCells).toFixed(0) : "0"}% feature–cohort coverage</p></article><article className={styles.amberMetric}><span>UNOBSERVED / EXCLUDED</span><strong>{missingCells.toString().padStart(2, "0")}</strong><p>Across {incompleteFeatures} incomplete features · never zero-filled</p></article></section>
      <div className={styles.resultsTop}><div><span className={styles.eyebrow}>LIVE LINKED VIEWS</span><h2>The replication landscape</h2></div><div className={styles.resultActions}><span className={styles.verifiedMark}>✓ {verifyStatus || "Replay verified"}</span><button type="button" onClick={() => downloadJson({ export_schema: "glio-replication-report/1.0.0", source_classification: run.source, source_name: sourceName, request: run.request, result: run.result, verification: run.verified }, `glio-replication-${result.analysis_id.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 60)}.json`)}>Export report <span aria-hidden="true">↓</span></button></div></div>
      <section className={`${styles.panel} ${styles.coveragePanel}`}><PanelHeading index="01" title="Evidence across cohorts" caption="Select a feature to trace its effects, heterogeneity, and sensitivity below." aside={<div className={styles.filters}><label><span className={styles.srOnly}>Search features</span><span aria-hidden="true">⌕</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find a feature…" /></label><select aria-label="Filter by cohort coverage" value={coverageFilter} onChange={(event) => setCoverageFilter(event.target.value)}><option value="all">All coverage</option><option value="complete">Complete coverage</option><option value="incomplete">Incomplete coverage</option></select></div>} /><CoverageMatrix features={features} cohorts={result.cohorts} selected={selected.feature_id} onSelect={setSelectedId} /><div className={styles.matrixFooter}><div className={styles.gradientLegend}><span>Negative</span><i /><span>Positive</span></div><span><b>0</b> observed zero</span><span><b>—</b> missing</span><span><b>×</b> unsupported</span><span className={styles.matrixFilterCount}>{features.length} of {result.features.length} features</span></div></section>
      <section className={styles.selectedHeading}><div><span className={styles.eyebrow}>SELECTED FEATURE</span><h2>{selected.label}<span>{selected.feature_id}</span></h2></div><div><span className={styles.supportBadge}>{selected.support === "abstained" ? "Estimator abstained" : "Limited research support"}</span><span className={styles.coveragePill}>{selected.observed_count} / {selected.total_count} cohorts observed</span></div></section>
      <div className={styles.analysisGrid}><section className={`${styles.panel} ${styles.forestPanel}`}><PanelHeading index="02" title="Effect & uncertainty" caption="Cohort estimates, two pooling assumptions, one visible null." aside={<span className={styles.panelChip}>NOMINAL 95% CI</span>} /><ForestPlot feature={selected} cohorts={result.cohorts} effectScale={result.effect_scale} /><div className={styles.statStrip}><div><span>RANDOM EFFECT</span><b>{formatEffect(selected.random_effect?.estimate)}</b></div><div><span>ADJUSTED q · BH / BY</span><b className={styles.dualValue}>{formatProbability(selected.adjusted_p_value)}<small> / {formatProbability(selected.dependence_robust_adjusted_p_value)}</small></b></div><div><span>I² HETEROGENEITY</span><b>{selected.heterogeneity ? `${selected.heterogeneity.i_squared_percent.toFixed(1)}%` : "—"}</b></div><div><span>BETWEEN-COHORT τ²</span><b>{selected.heterogeneity?.tau_squared.toFixed(3) ?? "—"}</b></div></div>{selected.reasons.length > 0 ? <div className={styles.reasonBox}>{selected.reasons.map((reason) => <p key={reason}>{reason.replaceAll("_", " ")}</p>)}</div> : null}<p className={styles.chartNote}>The approximate prediction interval describes dispersion of a hypothetical cohort effect under the random-effects assumptions. A narrow interval is not proof of replication.</p></section>
      <section className={`${styles.panel} ${styles.overviewPanel}`}><PanelHeading index="03" title="Where the evidence varies" caption="All estimable features. Click a point to follow its signal." /><HeterogeneityPlot features={result.features} selected={selected.feature_id} onSelect={setSelectedId} /><div className={styles.directionBlock}><div><span>DIRECTION AGREEMENT</span><b>{selected.direction_agreement.majority_fraction === null ? "—" : `${(100 * selected.direction_agreement.majority_fraction).toFixed(0)}%`}<small> sign majority</small></b></div><div className={styles.directionBar} aria-label={`${selected.direction_agreement.positive_count} positive, ${selected.direction_agreement.negative_count} negative, ${selected.direction_agreement.zero_count} zero estimates`}><i style={{ flex: selected.direction_agreement.positive_count, background: TONE.positive }} /><i style={{ flex: selected.direction_agreement.negative_count, background: TONE.negative }} /><i style={{ flex: selected.direction_agreement.zero_count, background: "#8296a4" }} /></div><p>{selected.direction_agreement.positive_count} positive · {selected.direction_agreement.negative_count} negative · {selected.direction_agreement.zero_count} zero <span>{selected.direction_agreement.classification.replaceAll("_", " ")}</span></p></div></section>
      <section className={`${styles.panel} ${styles.sensitivityPanel}`}><PanelHeading index="04" title="Would one cohort change it?" caption="Each omission refits the random-effects model." aside={<span className={styles.panelChip}>LEAVE ONE OUT</span>} /><LeaveOneOut feature={selected} cohorts={result.cohorts} /><p className={styles.chartNote}>The dotted vertical line marks the full pooled estimate. Fewer than two remaining observations cause abstention.</p></section>
      <section className={`${styles.panel} ${styles.contextPanel}`}><PanelHeading index="05" title="Keep the question intact" caption="The estimand is part of the evidence, not just metadata." /><dl className={styles.contextList}><div><dt>Disease context</dt><dd>{result.disease_context.replaceAll("_", " ")}</dd></div><div><dt>Shared estimand</dt><dd>{result.estimand_id.replaceAll("_", " ")}</dd></div><div><dt>Effect scale</dt><dd>{result.effect_scale.replaceAll("_", " ")}</dd></div><div><dt>Contrast</dt><dd>{typeof result.contrast === "string" ? result.contrast : JSON.stringify(result.contrast)}</dd></div><div><dt>Independence basis</dt><dd>{typeof result.independence_basis === "string" ? result.independence_basis : JSON.stringify(result.independence_basis)}</dd></div></dl><div className={styles.contextCaution}><span aria-hidden="true">↗</span><p>Compatible summaries are a prerequisite. Shared samples, different contrasts, and unmodeled confounding can invalidate a synthesis.</p></div></section></div>
      <section className={`${styles.panel} ${styles.provenancePanel}`}><PanelHeading index="06" title="A result you can retrace" caption="Exact request, active profile, deterministic replay, and source receipts." aside={<div className={styles.provenanceActions}><button type="button" disabled={busy} onClick={() => void verifyReplay()}>{phase === "verifying" ? "Verifying…" : "Verify replay"}<span aria-hidden="true">⟳</span></button><button type="button" onClick={() => downloadJson(replicationReplayEnvelope(run.request, run.result), `glio-replication-replay-${result.analysis_id.replace(/[^a-zA-Z0-9_-]/g, "").slice(0, 60)}.json`)}>Export replay envelope<span aria-hidden="true">↓</span></button><button type="button" onClick={() => setProvenanceOpen(!provenanceOpen)} aria-expanded={provenanceOpen}>{provenanceOpen ? "Close" : "Inspect"} provenance {provenanceOpen ? "−" : "+"}</button></div>} /><div className={styles.receiptGrid}>{[{ label: "SCIENTIFIC PROFILE", value: result.profile_id }, { label: "REQUEST DIGEST", value: result.request_digest }, { label: "RESULT DIGEST", value: result.result_digest }, { label: "SOURCE CLASS", value: sourceLabel(run.source) }].map(({ label, value }) => <div key={label}><span>{label}</span><code title={value}>{shortReceipt(value)}</code></div>)}</div>{provenanceOpen ? <div className={styles.provenanceBody}><div className={styles.cohortReceipts}>{result.cohorts.map((cohort) => <article key={cohort.cohort_id}><h3>{cohortLabel(cohort)}</h3><pre>{JSON.stringify(cohort, null, 2)}</pre></article>)}</div><details><summary>Full scientific profile</summary><pre>{JSON.stringify(profile, null, 2)}</pre></details><details><summary>Frozen request submitted for this result</summary><pre>{JSON.stringify(run.request, null, 2)}</pre></details><details><summary>Replay verification receipt</summary><pre>{JSON.stringify(run.verified, null, 2)}</pre></details></div> : null}</section>
      <section className={styles.limitations}><span className={styles.eyebrow}>INTERPRETATION BOUNDARY</span><h2>Evidence has conditions.</h2><div>{result.limitations.map((limitation, index) => <p key={index}><span>{(index + 1).toString().padStart(2, "0")}</span>{limitation.replaceAll("_", " ")}</p>)}</div></section>
    </> : <section className={styles.emptyState} aria-label="No active analysis"><div className={styles.emptyGlyph} aria-hidden="true">∴</div><span className={styles.eyebrow}>{busy ? "CONNECTING THE EVIDENCE" : "NO ACTIVE RESULT"}</span><h2>{busy ? "Following the signal across cohorts." : "An honest result starts with a declared input."}</h2><p>{busy ? "The research service computes every estimate and verifies the exact request before admitting linked views." : "Load the synthetic demonstration, or import compatible caller-owned cohort summaries. New input clears every previous chart."}</p>{!busy ? <button type="button" className={styles.primaryButton} onClick={() => void loadDemo()}>Load synthetic demonstration <Arrow /></button> : null}</section>}
    <footer className={styles.footer}><div>GLIO / PROTEOGEN<span>Cross-cohort replication observatory</span></div><p>Exploratory research use · no clinical decisions · no patient predictions</p><a href="/">Back to workbench <Arrow direction="left" /></a></footer>
  </main>;
}
