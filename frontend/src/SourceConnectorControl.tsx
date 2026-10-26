import { useEffect, useRef, useState } from "react";
import { api } from "./api";
import { Settings } from "lucide-react";

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
  const defaultPorts: Record<string, number> = { SQLSERVER: 1433, MYSQL: 3306, POSTGRESQL: 5432, ORACLE: 1521 };
  const command = `python scripts/local_connector.py --url ${quote(connectorApplicationUrl)} --source ${quote(source.id)} --engine ${quote(engine)} --server ${quote(source.server_name)} --database ${quote(source.database_name)}${engine === "SQLSERVER" ? ` --driver ${quote(driver)}${certificateOption}` : ""}`;

  const downloadEnvFile = () => {
    if (!registration) return;
    const content = [
      "# Databricks Migration AI Studio - Agent Configuration",
      `# Source: ${source.id} (${source.server_name} / ${source.database_name} - ${engine})`,
      `CONNECTOR_URL=${connectorApplicationUrl}`,
      `CONNECTOR_SOURCE=${source.id}`,
      `CONNECTOR_ENGINE=${engine}`,
      `CONNECTOR_SERVER=${source.server_name}`,
      `CONNECTOR_PORT=${defaultPorts[engine] || 3306}`,
      `CONNECTOR_DATABASE=${source.database_name}`,
      `CONNECTOR_TOKEN=${registration.token}`,
      engine === "SQLSERVER" ? `CONNECTOR_DRIVER=${driver}` : "",
      engine === "SQLSERVER" ? `CONNECTOR_TRUST_CERT=${trustCert ? "true" : "false"}` : "",
      "# Credentials for local desktop database (leave blank for Windows Auth on SQL Server)",
      "CONNECTOR_USERNAME=",
      "CONNECTOR_PASSWORD=",
    ].filter(Boolean).join("\n");
    const blob = new Blob([content], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "agent.env";
    a.click();
    URL.revokeObjectURL(url);
  };

  const downloadAgent = (pkgType: "exe" | "zip" = "exe") => {
    const downloadUrl = `${connectorApplicationUrl}/api/connector/download?package_type=${pkgType}`;
    window.open(downloadUrl, "_blank");
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
        setError("");
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
        <h2>Local {engine} Connector</h2>
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
                <span>⭐ Quick Start: Standalone Agent Executable (.exe)</span>
              </div>
              <p
                style={{
                  margin: "0 0 12px 0",
                  fontSize: "0.9rem",
                  color: "#42526e",
                }}
              >
                Download and run <code>migration-agent.exe</code> on your local computer. Place <code>agent.env</code> next to it to connect automatically.
              </p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
                <button
                  type="button"
                  onClick={() => downloadAgent("exe")}
                  style={{
                    background: "#0052cc",
                    color: "white",
                    border: "none",
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
                  ⬇ Download Agent (.exe)
                </button>
                <button
                  type="button"
                  onClick={downloadEnvFile}
                  style={{
                    background: "#091e420f",
                    color: "#0052cc",
                    border: "1px solid #0052cc",
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
                  📄 Download Configuration (agent.env)
                </button>
              </div>
              <p
                style={{
                  margin: "12px 0 0 0",
                  fontSize: "0.84rem",
                  color: "#5e6c84",
                }}
              >
                💡 <strong>Instructions:</strong> Save <code>agent.env</code> into the same folder as <code>migration-agent.exe</code>, enter your local database username and password in <code>agent.env</code>, and double-click the exe!
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
              disabled={busy}
              onClick={() => mutate("POST")}
              style={{
                background: "#0052cc",
                color: "white",
                border: "none",
                borderRadius: 4,
                padding: "8px 16px",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              {status === "DIRECT" ? "Register Connector Agent" : "Generate New Token"}
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
              setError("");
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
