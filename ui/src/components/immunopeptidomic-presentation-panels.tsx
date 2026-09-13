import { formatNumber, formatSigned, type JsonObject } from "@/lib/research-state";
import {
  normalizePresentationCandidates,
  presentationProvenance,
} from "@/lib/immunopeptidomic-presentation";

function supportClass(value: string): string {
  return value === "supported" ? "supported" : value === "limited" ? "limited" : "abstained";
}

export function ImmunopeptidomicPresentationResultPanels({ result }: { result: JsonObject }) {
  const candidates = normalizePresentationCandidates(result);
  const supported = candidates.filter((candidate) => candidate.support === "supported");
  return (
    <div className="panel-stack">
      <section className="result-panel">
        <div className="panel-title-row"><div><p className="eyebrow">ALLELE-AWARE PRESENTATION</p><h3>Ranked peptide candidates</h3></div><span className={`support-badge ${supportClass(String(result.support ?? "abstained"))}`}>{String(result.support ?? "abstained")}</span></div>
        <div className="metric-strip">
          <article><span>SUPPORTED PEPTIDES</span><b>{String(result.supported_peptide_count ?? supported.length)}</b><small>minimum three for release</small></article>
          <article><span>SUPPORTED ALLELES</span><b>{String(result.supported_allele_count ?? 0)}</b><small>caller models with exact HLA IDs</small></article>
          <article><span>BOOTSTRAP</span><b>{String(result.bootstrap_replicates ?? 0)}</b><small>digest-seeded perturbations</small></article>
        </div>
        <div className="table-wrap"><table><thead><tr><th>Rank</th><th>Peptide / gene</th><th>Probability</th><th>90% interval</th><th>Alleles</th><th>Drivers</th></tr></thead><tbody>
          {candidates.map((candidate) => <tr key={candidate.id}><td className="mono-cell">{candidate.rank ?? "—"}</td><td><b className="mono-cell">{candidate.sequence}</b><small>{candidate.id} · {candidate.gene}</small></td><td className="mono-cell">{candidate.probability === null ? "—" : formatNumber(candidate.probability, 4)}</td><td className="mono-cell">{candidate.low === null || candidate.high === null ? "—" : `[${formatNumber(candidate.low, 4)}, ${formatNumber(candidate.high, 4)}]`}</td><td className="mono-cell">{candidate.alleles || "—"}</td><td>{candidate.drivers.slice(0, 3).join(" · ") || candidate.reason || "No supported model"}</td></tr>)}
        </tbody></table></div>
      </section>
      <section className="result-panel">
        <div className="panel-title-row"><div><p className="eyebrow">MODEL SENSITIVITY</p><h3>Binding, processing, expression, and variant ablations</h3></div><span className="boundary-chip">probability deltas · not T-cell recognition</span></div>
        <div className="driver-grid">{supported.map((candidate) => <article key={candidate.id}><header><div><b>{candidate.sequence}</b><small>{candidate.gene} · P={candidate.probability === null ? "—" : formatNumber(candidate.probability, 4)}</small></div><strong>{candidate.rank ? `#${candidate.rank}` : "—"}</strong></header><div className="master-ablation-list">{candidate.ablations.map((ablation) => <div key={ablation.component}><b>omit {ablation.component}</b><span>Δ {ablation.delta === null ? "—" : formatSigned(ablation.delta)}</span></div>)}</div></article>)}</div>
      </section>
    </div>
  );
}

export function ImmunopeptidomicPresentationEvidencePanel({ request }: { request: JsonObject }) {
  return <section className="result-panel"><div className="panel-title-row"><div><p className="eyebrow">CALLER-OWNED INPUT</p><h3>HLA and peptide evidence</h3></div><span className="boundary-chip">licensed model coefficients remain external</span></div><div className="metric-strip"><article><span>PEPTIDES</span><b>{String(Array.isArray(request.peptides) ? request.peptides.length : 0)}</b><small>candidate sequences</small></article><article><span>HLA ALLELES</span><b>{String(Array.isArray(request.hla_alleles) ? request.hla_alleles.length : 0)}</b><small>exact identifiers</small></article><article><span>MODEL DIGESTS</span><b>{String(Array.isArray(request.models) ? request.models.length : 0)}</b><small>caller-supplied PSSMs</small></article></div><pre>{JSON.stringify({ source_digests: request.source_digests, provenance_note: request.provenance_note }, null, 2)}</pre></section>;
}

export function ImmunopeptidomicPresentationAuditPanels({ result, profile, verification }: { result: JsonObject; profile: JsonObject | null; verification: JsonObject | null }) {
  return <div className="panel-stack audit-grid"><section className="result-panel receipt-panel"><div className="panel-title-row"><div><p className="eyebrow">DETERMINISTIC REPLAY</p><h3>Presentation receipt verification</h3></div></div>{verification ? <><div className={`verification-banner ${verification.verified === true ? "verified" : "mismatch"}`}><i />{verification.verified === true ? "Replay verified" : "Replay mismatch detected"}</div><pre>{JSON.stringify(verification, null, 2)}</pre></> : <p className="panel-empty">Recompute this exact caller-owned HLA request to verify the request and result digests.</p>}</section><section className="result-panel"><div className="panel-title-row"><div><p className="eyebrow">MODEL PROVENANCE</p><h3>Caller model and source binding</h3></div></div><pre>{JSON.stringify({ model_digests: result.model_digests, profile: profile ? { profile_id: profile.profile_id, profile_digest: profile.profile_digest, execution_scope: profile.execution_scope } : null, provenance: presentationProvenance(result), limitations: result.limitations }, null, 2)}</pre></section></div>;
}

