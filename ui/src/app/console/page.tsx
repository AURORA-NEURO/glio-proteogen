"use client";

import { useEffect, useState } from "react";

type Account = { email: string };

type Pairing = {
  pairingUrl: string;
  expiresAt: string;
};

export default function ConsolePage() {
  const [account, setAccount] = useState<Account | null>(null);
  const [consoleUrl, setConsoleUrl] = useState("");
  const [status, setStatus] = useState("Preparing the GLIO Agent Console…");
  const [error, setError] = useState("");

  async function prepareConsole() {
    setError("");
    setStatus("Issuing a short-lived T3 Code pairing credential…");
    const response = await fetch("/api/pairing/token", { method: "POST" });
    const data = (await response.json()) as { error?: string; pairing?: Pairing };
    if (!response.ok || !data.pairing) throw new Error(data.error ?? "Unable to pair the console.");
    setConsoleUrl(data.pairing.pairingUrl);
    setStatus(`Paired for ${account?.email ?? "your account"} · credential expires ${new Date(data.pairing.expiresAt).toLocaleTimeString()}.`);
  }

  useEffect(() => {
    async function load() {
      try {
        const response = await fetch("/api/auth/me", { cache: "no-store" });
        if (!response.ok) throw new Error("Sign in to open the GLIO Agent Console.");
        const data = (await response.json()) as { account: Account };
        setAccount(data.account);
        setStatus("Account verified. Preparing the GLIO Agent Console…");
        const pendingPairing = sessionStorage.getItem("glio_pending_pairing");
        if (pendingPairing) {
          sessionStorage.removeItem("glio_pending_pairing");
          const pairing = JSON.parse(pendingPairing) as Pairing;
          if (!pairing.pairingUrl || !pairing.expiresAt) throw new Error("The pending pairing credential is invalid.");
          setConsoleUrl(pairing.pairingUrl);
          setStatus(`Secure GLIO session ready · credential expires ${new Date(pairing.expiresAt).toLocaleTimeString()}.`);
          return;
        }
        const pairingResponse = await fetch("/api/pairing/token", { method: "POST" });
        const pairingData = (await pairingResponse.json()) as { error?: string; pairing?: Pairing };
        if (!pairingResponse.ok || !pairingData.pairing) throw new Error(pairingData.error ?? "Unable to pair the console.");
        setConsoleUrl(pairingData.pairing.pairingUrl);
        setStatus(`Secure GLIO session ready · credential expires ${new Date(pairingData.pairing.expiresAt).toLocaleTimeString()}.`);
      } catch (loadError) {
        setError(loadError instanceof Error ? loadError.message : "Unable to open the console.");
        setStatus("");
      }
    }
    void load();
  }, []);

  async function signOut() {
    sessionStorage.removeItem("glio_pending_pairing");
    await fetch("/api/auth/logout", { method: "POST" });
    window.location.href = "/register";
  }

  return (
    <main className="console-shell">
      <header className="console-topbar">
        <a className="brand-lockup" href="/">
          <div className="brand-mark">G</div>
          <div><p className="eyebrow accent">GLIO / PROTEOGEN</p><h1>Agent Console</h1></div>
        </a>
        <div className="console-actions"><span className="environment-chip">GLIO RUNTIME</span>{account ? <span className="console-account">ACCOUNT ACTIVE</span> : null}<button className="quiet-button" onClick={() => void signOut()}>Sign out</button></div>
      </header>
      <section className="console-heading">
        <div><p className="eyebrow accent">MODEL OPERATIONS / AGENT WORKSPACE</p><h2>GLIO Proteogen, in motion.</h2><p>Run coding agents against the live research workspace through the T3 Code runtime.</p></div>
        <div className="console-status"><span className={`status-pill ${error ? "offline" : "online"}`}><i /> {error ? "Offline" : "Connected"}</span><span>{status}</span></div>
      </section>
      {error ? <section className="console-error"><p>{error}</p><div><a className="execute-button link-button" href="/register">Register or sign in <span>↗</span></a><button className="quiet-button" onClick={() => void prepareConsole()}>Retry pairing</button></div></section> : consoleUrl ? <section className="agent-frame-wrap"><div className="agent-frame-bar"><span className="frame-led" /><span>GLIO PROTEOGEN / T3 CODE AGENT SURFACE</span><a href={consoleUrl} target="_blank" rel="noreferrer">Open in new tab ↗</a></div><iframe className="agent-frame" src={consoleUrl} title="GLIO Proteogen Agent Console" /></section> : <section className="console-loading"><span className="spinner" /><p>{status}</p></section>}
      <footer className="footer"><span>GLIO / PROTEOGEN</span><span>Authenticated agent workspace</span><a href="/">Back to control room</a></footer>
    </main>
  );
}
