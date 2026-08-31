"use client";

import { FormEvent, useState } from "react";

type Pairing = {
  credential: string;
  expiresAt: string;
  pairingUrl: string;
};

type Account = {
  email: string;
};

export default function RegisterPage() {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [account, setAccount] = useState<Account | null>(null);
  const [pairing, setPairing] = useState<Pairing | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");
    setPairing(null);
    try {
      const response = await fetch(`/api/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = (await response.json()) as { error?: string; account?: Account; pairing?: Pairing | null; message?: string };
      if (!response.ok) throw new Error(data.error ?? "Unable to continue.");
      setAccount(data.account ?? null);
      setPairing(data.pairing ?? null);
      setMessage(data.message ?? "Signed in. Generate a fresh console pairing when you are ready.");
      setPassword("");
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Unable to continue.");
    } finally {
      setSubmitting(false);
    }
  }

  async function copyToken() {
    if (pairing) await navigator.clipboard.writeText(pairing.credential);
    setMessage("Pairing token copied to the clipboard.");
  }

  return (
    <main className="auth-shell">
      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />
      <div className="auth-card">
        <div className="auth-brand">
          <div className="brand-mark">G</div>
          <div>
            <p className="eyebrow accent">AURORA / RESEARCH SYSTEMS</p>
            <h1>GLIO Proteogen</h1>
          </div>
        </div>
        <div className="auth-copy">
          <p className="eyebrow accent">SECURE AGENT ACCESS</p>
          <h2>{mode === "register" ? "Create your research workspace." : "Return to your workspace."}</h2>
          <p>One GLIO account links your main site identity to a short-lived T3 Code pairing credential for the agent console.</p>
        </div>
        {!account ? (
          <form className="auth-form" onSubmit={submit}>
            <label><span>Email</span><input type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="email" required /></label>
            <label><span>Password</span><input type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete={mode === "register" ? "new-password" : "current-password"} minLength={10} required /></label>
            <button className="execute-button auth-submit" type="submit" disabled={submitting}>{submitting ? "Working…" : mode === "register" ? "Create account" : "Sign in"}<span>↗</span></button>
            <button className="quiet-button" type="button" onClick={() => { setMode(mode === "register" ? "login" : "register"); setError(""); setMessage(""); }}>{mode === "register" ? "Already have an account? Sign in" : "Need an account? Register"}</button>
          </form>
        ) : (
          <div className="pairing-result">
            <div className="success-badge"><i /> Account active</div>
            <p className="account-email">{account.email}</p>
            <p className="pairing-message">{message}</p>
            {pairing ? (
              <>
                <label className="token-field"><span>ONE-TIME PAIRING TOKEN</span><input value={pairing.credential} readOnly /></label>
                <div className="pairing-actions"><button className="execute-button" onClick={() => void copyToken()}>Copy token <span>⧉</span></button><a className="execute-button link-button" href="/console">Open GLIO Agent Console <span>↗</span></a></div>
                <p className="token-note">Expires {new Date(pairing.expiresAt).toLocaleString()}. This token is single-use and is never stored by the GLIO site.</p>
              </>
            ) : <a className="execute-button link-button" href="/console">Open account console <span>↗</span></a>}
          </div>
        )}
        {(error || message) && !account && <p className={`auth-feedback ${error ? "error" : "success"}`}>{error || message}</p>}
        <a className="back-link" href="/">← Back to control room</a>
      </div>
    </main>
  );
}
