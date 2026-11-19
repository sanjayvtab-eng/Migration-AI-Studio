import { useEffect, useRef, useState } from "react";
import { api, downloadApi } from "./api";
import { AlertTriangle, CheckCircle2, Download, FileText, KeyRound, Lock, Settings } from "lucide-react";

type Props = {
  projectId: string;
  source: { id: string; server_name: string; database_name: string; engine?: string };
  onlyStatus?: boolean;
  onlyButton?: boolean;
};

export default function SourceConnectorControl({
  projectId,
  source,
  onlyStatus,
  onlyButton,
}: Props) {
  const connectorSupported = true;
  const [status, setStatus] = useState("Loading");
  const [registration, setRegistration] = useState<{ token: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const [hasDownloadedEnv, setHasDownloadedEnv] = useState(false);
  const [hasDownloadedExe, setHasDownloadedExe] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const path = `/projects/${projectId}/sources/${source.id}/connector`;

  useEffect(() => {
    if (open) dialog.current?.showModal();
  }, [open]);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const result = await api<{ status: string }>(path);
        if (active) setStatus(result.status);
      } catch {
        if (active) setStatus("Unavailable");
      }
    };
    void refresh();
    const timer = window.setInterval(refresh, 15000);
    return () => { active = false; window.clearInterval(timer); };
  }, [path]);

  const mutate = async (method: string) => {
    setBusy(true);
    setError("");
    try {
      const result = await api<{ token: string }>(path, { method });
      setRegistration(method === "POST" ? result : null);
      setStatus(method === "POST" ? "OFFLINE" : "REVOKED");
      if (method === "POST") {
        setHasDownloadedEnv(false);
        setHasDownloadedExe(false);
        window.dispatchEvent(new CustomEvent("connector-tour-event", { detail: { event: "connector:token-generated" } }));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Connector update failed");
    } finally { setBusy(false); }
  };
  const [driver, setDriver] = useState("ODBC Driver 17 for SQL Server");
  const [trustCert, setTrustCert] = useState(true);
  const quote = (value: string) => "'" + value.replaceAll("'", "''") + "'";
  const certificateOption = trustCert ? " --trust-server-certificate" : "";
  const configuredApi = import.meta.env.VITE_API_URL || "/api";
  const connectorApplicationUrl = new URL(configuredApi, window.location.origin).origin;
  const engine = source.engine || "SQLSERVER";
  const command = `python scripts/local_connector.py --url ${quote(connectorApplicationUrl)} --source ${quote(source.id)} --engine ${quote(engine)} --server ${quote(source.server_name)} --database ${quote(source.database_name)}${engine === "SQLSERVER" ? ` --driver ${quote(driver)}${certificateOption}` : ""}`;

  const downloadEnvFile = async () => {
    if (!registration) return;
    setError("");
    try {
      const query = new URLSearchParams({
        token: registration.token,
        driver,
        trust_cert: String(trustCert),
      });
      await downloadApi(`${path}/config?${query.toString()}`, "agent.env");
      setHasDownloadedEnv(true);
      window.dispatchEvent(new CustomEvent("connector-tour-event", { detail: { event: "connector:env-downloaded" } }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to download agent.env");
    }
  };

  const downloadAgent = (pkgType: "exe" | "zip" = "exe") => {
    const downloadUrl = `${connectorApplicationUrl}/api/connector/download?package_type=${pkgType}`;
    window.open(downloadUrl, "_blank");
  };

  const handleDownloadExe = () => {
    if (!hasDownloadedEnv) return;
    downloadAgent("exe");
    setHasDownloadedExe(true);
    window.dispatchEvent(new CustomEvent("connector-tour-event", { detail: { event: "connector:exe-downloaded" } }));
  };

  const isOnline = status === "DIRECT" || status === "ONLINE";
  const isBlocked = status === "REVOKED" || status === "UNAVAILABLE";
  const pillClass = isOnline ? "active" : isBlocked ? "blocked" : "review";
  const statusText =
    status === "DIRECT"
      ? "Native Driver (Direct)"
      : status === "ONLINE"
      ? "Connector Online (Ready)"
      : status === "OFFLINE"
      ? "Connector Offline (Standby)"
      : `Connector: ${status.toLowerCase()}`;

  const statusPill = (
    <span className={`status-pill ${pillClass}`}>
      <span className="status-dot" />
      {statusText}
    </span>
  );

  const dialogElement = open && (
    <dialog
      ref={dialog}
      aria-label={`Local ${engine} connector`}
      onCancel={() => {
        setOpen(false);
        setRegistration(null);
        setHasDownloadedEnv(false);
        setHasDownloadedExe(false);
        setError("");
        window.dispatchEvent(new CustomEvent("connector-agent-closed"));
      }}
      style={{
        border: "1px solid #d6dce5",
        borderRadius: 12,
        padding: 0,
        width: "min(680px, 90vw)",
        maxHeight: "85vh",
      }}
    >
      <div
        style={{
          background: "white",
          color: "#172b4d",
          padding: 24,
          overflowY: "auto",
          whiteSpace: "normal",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h2 style={{ margin: 0 }}>Local {engine} Connector</h2>
        </div>
        <p>
          Run the connector on your local machine to connect your local {engine} instance ({source.server_name} / {source.database_name}) with Migration AI Studio. It connects outward over HTTPS; your database credentials stay local on your computer.
        </p>
        <p>
          Status: <strong>{status}</strong>
        </p>
        {error && <p role="alert" style={{ color: "#de350b" }}>{error}</p>}
        {registration ? (
          <>
            <p>
              Registration token generated. Copy it below or download the pre-configured <code>agent.env</code>:
            </p>
            <textarea
              aria-label="Registration token"
              readOnly
              value={registration.token}
              rows={3}
              style={{ width: "100%", boxSizing: "border-box" }}
            />
            {engine === "SQLSERVER" && (
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  alignItems: "center",
                  gap: 16,
                  margin: "14px 0 8px 0",
                }}
              >
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    fontSize: "0.9rem",
                  }}
                >
                  <span>
                    <strong>ODBC Driver:</strong>
                  </span>
                  <select
                    value={driver}
                    onChange={(e) => setDriver(e.target.value)}
                    style={{
                      padding: "4px 8px",
                      borderRadius: 4,
                      border: "1px solid #c1c7d0",
                    }}
                  >
                    <option value="ODBC Driver 17 for SQL Server">
                      ODBC Driver 17 for SQL Server (Recommended)
                    </option>
                    <option value="ODBC Driver 18 for SQL Server">
                      ODBC Driver 18 for SQL Server
                    </option>
                  </select>
                </label>
                <label
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                    fontSize: "0.9rem",
                    cursor: "pointer",
                  }}
                >
                  <input
                    type="checkbox"
                    checked={trustCert}
                    onChange={(e) => setTrustCert(e.target.checked)}
                  />
                  <span>
                    Trust Server Certificate (
                    <code>--trust-server-certificate</code>)
                  </span>
                </label>
              </div>
            )}

            <div
              style={{
                background: "#f4f5f7",
                borderRadius: 8,
                padding: 16,
                margin: "16px 0",
                border: "1px solid #dfe1e6",
              }}
            >
              <div
                style={{
                  fontWeight: 600,
                  color: "#172b4d",
                  marginBottom: 8,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                }}
              >
                <span>⭐ Quick Start: Standalone Agent Configuration & Executable</span>
              </div>
              <p
                style={{
                  margin: "0 0 12px 0",
                  fontSize: "0.9rem",
                  color: "#42526e",
                }}
              >
                First download <code>agent.env</code> containing your source configuration. Next download <code>migration-agent.exe</code> into the exact same folder and launch it.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                <button
                  type="button"
                  data-tour="download-agent-env-btn"
                  onClick={downloadEnvFile}
                  title="Download pre-configured agent.env configuration"
                  style={{
                    background: hasDownloadedEnv ? "#ecfdf5" : "#0052cc",
                    color: hasDownloadedEnv ? "#166534" : "white",
                    border: hasDownloadedEnv ? "1px solid #86efac" : "1px solid #0052cc",
                    borderRadius: 4,
                    padding: "9px 18px",
                    fontSize: "0.95rem",
                    fontWeight: 600,
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  {hasDownloadedEnv ? <CheckCircle2 size={16} /> : <FileText size={16} />}
                  {hasDownloadedEnv ? "Downloaded Configuration (agent.env)" : "Download Configuration (agent.env)"}
                </button>
                <button
                  type="button"
                  data-tour="download-agent-exe-btn"
                  onClick={handleDownloadExe}
                  disabled={!hasDownloadedEnv}
                  title={!hasDownloadedEnv ? "Download the configuration (agent.env) before downloading the executable" : "Download standalone migration-agent.exe"}
                  style={{
                    background: !hasDownloadedEnv ? "#f1f5f9" : hasDownloadedExe ? "#ecfdf5" : "#0052cc",
                    color: !hasDownloadedEnv ? "#94a3b8" : hasDownloadedExe ? "#166534" : "white",
                    border: `1px solid ${!hasDownloadedEnv ? "#cbd5e1" : hasDownloadedExe ? "#86efac" : "#0052cc"}`,
                    borderRadius: 4,
                    padding: "9px 18px",
                    fontSize: "0.95rem",
                    fontWeight: 600,
                    cursor: hasDownloadedEnv ? "pointer" : "not-allowed",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  {!hasDownloadedEnv ? <Lock size={14} /> : hasDownloadedExe ? <CheckCircle2 size={16} /> : <Download size={16} />}
                  {hasDownloadedExe ? "Downloaded Agent (.exe)" : `Download Agent (.exe)${!hasDownloadedEnv ? " (Locked)" : ""}`}
                </button>
                <button
                  type="button"
                  disabled
                  title="Download Agent Bundle (.zip) is locked in this edition."
                  style={{
                    background: "#f1f5f9",
                    color: "#94a3b8",
                    border: "1px solid #cbd5e1",
                    borderRadius: 4,
                    padding: "9px 18px",
                    fontSize: "0.95rem",
                    fontWeight: 600,
                    cursor: "not-allowed",
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    opacity: 0.75,
                  }}
                >
                  <Lock size={14} />
                  <span>Download Agent Bundle (.zip) (Locked)</span>
                </button>
              </div>
              <div
                role="alert"
                style={{
                  marginTop: 14,
                  background: "#fffbeb",
                  border: "1.5px solid #f59e0b",
                  borderRadius: 8,
                  padding: "12px 16px",
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-start",
                }}
              >
                <AlertTriangle size={20} color="#d97706" style={{ marginTop: 2, flexShrink: 0 }} />
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: "#92400e", display: "flex", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
                    <span>CRITICAL: Keep Connector Agent Console Open!</span>
                    <span style={{ display: "inline-flex", alignItems: "center", gap: 5, background: "#fef3c7", color: "#b45309", fontSize: 11, padding: "2px 8px", borderRadius: 12, border: "1px solid #fde68a" }}>
                      <span className="connector-live-pulse" /> Active Tunnel Required
                    </span>
                  </div>
                  <p style={{ margin: "4px 0 0", fontSize: 12, color: "#78350f", lineHeight: 1.45 }}>
                    Do <strong>not</strong> close the <code>migration-agent.exe</code> command prompt while testing or running migrations. Closing it disconnects your database immediately.
                  </p>
                </div>
              </div>
              <p
                style={{
                  margin: "12px 0 0 0",
                  fontSize: "0.84rem",
                  color: "#5e6c84",
                }}
              >
                💡 <strong>Instructions:</strong> Save the pre-configured <code>agent.env</code> into the same folder as <code>migration-agent.exe</code> (or unzip the bundle), then run the executable. The Agent opens <code>http://localhost:8585</code> for real-time telemetry.
              </p>
              <p
                style={{
                  margin: "8px 0 0 0",
                  fontSize: "0.84rem",
                  color: "#b45309",
                  background: "#fef3c7",
                  padding: "8px 12px",
                  borderRadius: 6,
                  border: "1px solid #fde68a",
                }}
              >
                ⚠️ <strong>Important:</strong> Whenever you add a new data source, download and apply the latest ENV configuration so the Local Connector receives the updated source credentials.
              </p>
            </div>

            <details style={{ margin: "16px 0" }}>
              <summary
                style={{
                  cursor: "pointer",
                  fontWeight: 600,
                  color: "#0052cc",
                  padding: "4px 0",
                }}
              >
                🐍 Python CLI / Developer Instructions
              </summary>
              <div
                style={{
                  padding: "10px 0",
                  fontSize: "0.88rem",
                  color: "#42526e",
                }}
              >
                <p>Alternatively run the connector via Python:</p>
                <pre
                  style={{
                    background: "#172b4d",
                    color: "#f4f5f7",
                    padding: 10,
                    borderRadius: 4,
                    overflowX: "auto",
                    whiteSpace: "pre-wrap",
                  }}
                >
                  {command} --token {quote(registration.token)}
                </pre>
              </div>
            </details>
          </>
        ) : (
          <p>
            Register this source to generate a token for the Local Connector Agent.
          </p>
        )}

        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            marginTop: 20,
            gap: 10,
          }}
        >
          <div style={{ display: "flex", gap: 10 }}>
            <button
              type="button"
              data-tour="generate-connector-token-btn"
              disabled={busy}
              onClick={() => mutate("POST")}
              className={!registration ? "btn-connector-token-highlight" : ""}
              style={{
                background: "#0052cc",
                color: "white",
                border: "none",
                borderRadius: 4,
                padding: "9px 18px",
                fontWeight: 700,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <KeyRound size={15} />
              <span>{status === "DIRECT" ? "Register Connector Agent" : "Generate New Token"}</span>
            </button>
            {status !== "DIRECT" && (
              <button
                type="button"
                disabled={busy}
                onClick={() => mutate("DELETE")}
                style={{
                  background: "#de350b",
                  color: "white",
                  border: "none",
                  borderRadius: 4,
                  padding: "8px 16px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Revoke Connector
              </button>
            )}
          </div>
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              setRegistration(null);
              setHasDownloadedEnv(false);
              setHasDownloadedExe(false);
              setError("");
              window.dispatchEvent(new CustomEvent("connector-agent-closed"));
            }}
            style={{
              background: "#dfe1e6",
              border: "none",
              borderRadius: 4,
              padding: "8px 16px",
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </div>
      </div>
    </dialog>
  );

  if (onlyStatus) return statusPill;
  if (onlyButton) {
    return (
      <>
        <button
          type="button"
          data-tour="connector-agent-btn"
          onClick={() => setOpen(true)}
          title={`Configure Local ${engine} Connector`}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            background: "none",
            border: "1px solid #dfe1e6",
            borderRadius: 6,
            padding: "4px 8px",
            fontSize: "0.85rem",
            color: "#42526e",
            cursor: "pointer",
          }}
        >
          <Settings size={14} />
          <span>Connector Agent</span>
        </button>
        {dialogElement}
      </>
    );
  }

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
      {statusPill}
      <button
        type="button"
        onClick={() => setOpen(true)}
        title={`Configure Local ${engine} Connector`}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 4,
          background: "none",
          border: "none",
          color: "#0052cc",
          cursor: "pointer",
          fontSize: "0.85rem",
          fontWeight: 500,
        }}
      >
        <Settings size={14} />
        <span>Manage Agent</span>
      </button>
      {dialogElement}
    </div>
  );
}
