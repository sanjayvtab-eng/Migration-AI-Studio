import React, { useState, useEffect } from "react";
import {
  Settings,
  KeyRound,
  Download,
  Terminal,
  Database,
  CheckCircle2,
  AlertTriangle,
  ChevronRight,
  ChevronLeft,
  X,
  Sparkles,
  ExternalLink,
  Laptop,
} from "lucide-react";

interface ConnectorTourModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOpenConnectorAgent?: () => void;
  onProceedTestConnection?: () => void;
}

interface TourStepItem {
  step: number;
  title: string;
  subtitle: string;
  badge: string;
  icon: React.ReactNode;
  summary: string;
  details: string[];
  callout?: {
    type: "important" | "tip" | "info";
    text: string;
  };
  visualHint?: string;
  actionButton?: {
    label: string;
    onClick: () => void;
  };
}

export const ConnectorTourModal: React.FC<ConnectorTourModalProps> = ({
  isOpen,
  onClose,
  onOpenConnectorAgent,
  onProceedTestConnection,
}) => {
  const [activeStep, setActiveStep] = useState(1);

  // Keyboard navigation: ESC to close, Left/Right arrow keys to step
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      } else if (e.key === "ArrowRight") {
        setActiveStep((prev) => Math.min(prev + 1, 6));
      } else if (e.key === "ArrowLeft") {
        setActiveStep((prev) => Math.max(prev - 1, 1));
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const steps: TourStepItem[] = [
    {
      step: 1,
      title: "Step 1 – Open Connector Agent",
      subtitle: "Locate and open the connector registration settings",
      badge: "Action Required",
      icon: <Settings size={22} className="text-blue-500" />,
      summary: "Click the Connector Agent option to open the connector registration page.",
      details: [
        "In the Sources table, each registered database row has a dedicated 'Connector Agent' button under the Actions column.",
        "Clicking this button opens the local agent configuration modal specifically bound to that source instance.",
        "From here, you can manage tokens, inspect live heartbeat telemetry, and download execution bundles.",
      ],
      visualHint: "Actions Column → ⚙️ Connector Agent",
      actionButton: onOpenConnectorAgent
        ? {
            label: "Open Connector Agent Now",
            onClick: () => {
              onClose();
              onOpenConnectorAgent();
            },
          }
        : undefined,
    },
    {
      step: 2,
      title: "Step 2 – Generate a New Token",
      subtitle: "Create a cryptographic registration token",
      badge: "Authentication",
      icon: <KeyRound size={22} className="text-amber-500" />,
      summary: 'Click "Generate a New Token" to create a secure registration token for your Local Connector.',
      details: [
        "Clicking 'Generate New Token' creates a secure, AES-encrypted registration secret on the backend.",
        "The token authenticates the outbound agent heartbeat so no inbound firewall ports need to be exposed.",
        "You can copy the raw token directly or download the pre-configured agent.env file containing it.",
      ],
      visualHint: "Modal Button → [ Generate New Token ]",
    },
    {
      step: 3,
      title: "Step 3 – Download the Connector",
      subtitle: "Acquire the standalone executable & configuration",
      badge: "Download",
      icon: <Download size={22} className="text-emerald-500" />,
      summary: "Download the Local Connector EXE file and install it on your local machine.",
      details: [
        "Click 'Download Agent (.exe)' to get migration-agent.exe (~25MB self-contained executable).",
        "Click 'Download Configuration (agent.env)' to get the environment file pre-filled with your registration token and endpoints.",
        "Save both files in the same local directory (e.g., C:\\MigrationAgent\\ or your Downloads folder).",
      ],
      callout: {
        type: "tip",
        text: "If you already have migration-agent.exe installed, you do not need to redownload the EXE. Simply replace the agent.env file with the newly downloaded configuration.",
      },
      visualHint: "Downloads Folder → migration-agent.exe + agent.env",
    },
    {
      step: 4,
      title: "Step 4 – Register the Connector",
      subtitle: "Execute the agent binary on your computer",
      badge: "Execution",
      icon: <Terminal size={22} className="text-purple-500" />,
      summary: "Open the downloaded Local Connector application on your computer and complete the registration using the generated token.",
      details: [
        "Double-click migration-agent.exe to launch the Universal Agent in your local terminal/console.",
        "The agent automatically reads agent.env, connects over TLS 1.3 outbound HTTPS to the Studio Control Plane, and reports healthy status.",
        "Keep this terminal window running in the background during your migration session.",
      ],
      visualHint: "Terminal → Databricks Migration AI Studio – Universal Agent Online",
    },
    {
      step: 5,
      title: "Step 5 – Verify Your Data Sources",
      subtitle: "Check source sync in the local dashboard",
      badge: "Telemetry",
      icon: <Database size={22} className="text-cyan-500" />,
      summary: "Once registration is successful, open the Local Connector application. You should see the data sources you added in the web application.",
      details: [
        "Upon launch, the Local Connector automatically opens your browser to the local management hub at http://localhost:8585.",
        "Verify that your registered database profiles (e.g., PostgreSQL, SQL Server) appear active with 'ONLINE & STREAMING' status.",
        "The web application's status pill will synchronously turn green to reflect 'Connector Online (Ready)'.",
      ],
      visualHint: "Browser → http://localhost:8585 (Local Agent Hub)",
    },
    {
      step: 6,
      title: "Step 6 – Verify the Connection",
      subtitle: "Validate connectivity and proceed to Discovery",
      badge: "Final Step",
      icon: <CheckCircle2 size={22} className="text-green-500" />,
      summary: "Confirm that the newly added sources and their configurations are available in the Local Connector before proceeding with Test Connection.",
      details: [
        "Confirm that your source host, port, target database name, and credentials match between the web app and agent.env.",
        "Click 'Test Connection' on the source row to execute end-to-end TCP latency, authentication handshake, catalog read permissions, and schema query checks.",
        "Once tests pass, you are ready to proceed seamlessly to Stage 4: Discovery!",
      ],
      callout: {
        type: "important",
        text: "Important: Whenever you add a new data source, download and apply the latest ENV configuration so the Local Connector receives the updated source credentials.",
      },
      visualHint: "Source Row → [ Test Connection ] → [ Proceed to Discovery → ]",
      actionButton: onProceedTestConnection
        ? {
            label: "Proceed to Test Connection",
            onClick: () => {
              onClose();
              onProceedTestConnection();
            },
          }
        : undefined,
    },
  ];

  const currentStepData = steps[activeStep - 1];

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(15, 23, 42, 0.72)",
        backdropFilter: "blur(6px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 99999,
        padding: "16px",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          backgroundColor: "#ffffff",
          borderRadius: 16,
          boxShadow: "0 25px 50px -12px rgba(15, 23, 42, 0.35)",
          border: "1px solid #e2e8f0",
          width: "100%",
          maxWidth: 720,
          overflow: "hidden",
          display: "flex",
          flexDirection: "column",
          maxHeight: "90vh",
          animation: "mfFadeSlide 0.25s ease-out",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "20px 24px 16px 24px",
            borderBottom: "1px solid #e2e8f0",
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            background: "linear-gradient(180deg, #f8fafc 0%, #ffffff 100%)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div
              style={{
                width: 42,
                height: 42,
                borderRadius: 10,
                background: "#eff6ff",
                border: "1px solid #bfdbfe",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#2563eb",
              }}
            >
              <Sparkles size={22} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <h3
                  style={{
                    fontSize: "1.18rem",
                    fontWeight: 700,
                    color: "#0f172a",
                    margin: 0,
                  }}
                >
                  Local Connector Agent – Guided Tour
                </h3>
                <span
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    backgroundColor: "#e0f2fe",
                    color: "#0369a1",
                    padding: "2px 8px",
                    borderRadius: 999,
                    border: "1px solid #bae6fd",
                  }}
                >
                  Stage 3: Sources
                </span>
              </div>
              <p style={{ margin: "4px 0 0 0", fontSize: "0.85rem", color: "#64748b" }}>
                Step-by-step setup to connect on-premises & local databases with Migration Factory
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close Tour"
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              color: "#94a3b8",
              padding: 6,
              borderRadius: 8,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "#0f172a")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "#94a3b8")}
          >
            <X size={20} />
          </button>
        </div>

        {/* Step Progress Bar / Tabs */}
        <div
          style={{
            display: "flex",
            borderBottom: "1px solid #f1f5f9",
            backgroundColor: "#f8fafc",
            padding: "8px 16px",
            gap: 6,
            overflowX: "auto",
          }}
        >
          {steps.map((s) => {
            const isActive = s.step === activeStep;
            const isCompleted = s.step < activeStep;
            return (
              <button
                key={s.step}
                type="button"
                onClick={() => setActiveStep(s.step)}
                style={{
                  flex: 1,
                  minWidth: 90,
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 10px",
                  borderRadius: 8,
                  border: isActive
                    ? "1px solid #2563eb"
                    : isCompleted
                    ? "1px solid #cbd5e1"
                    : "1px solid transparent",
                  backgroundColor: isActive ? "#ffffff" : isCompleted ? "#f1f5f9" : "transparent",
                  color: isActive ? "#2563eb" : isCompleted ? "#334155" : "#64748b",
                  fontWeight: isActive ? 700 : 500,
                  fontSize: "0.78rem",
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                  transition: "all 0.15s ease",
                  boxShadow: isActive ? "0 2px 4px rgba(37,99,235,0.12)" : "none",
                }}
              >
                <span
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: "50%",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.72rem",
                    fontWeight: 700,
                    backgroundColor: isActive ? "#2563eb" : isCompleted ? "#10b981" : "#cbd5e1",
                    color: "#ffffff",
                  }}
                >
                  {isCompleted ? "✓" : s.step}
                </span>
                <span>Step {s.step}</span>
              </button>
            );
          })}
        </div>

        {/* Step Body */}
        <div
          style={{
            padding: "24px 28px",
            overflowY: "auto",
            flex: 1,
            display: "flex",
            flexDirection: "column",
            gap: 16,
          }}
        >
          {/* Step Header */}
          <div style={{ display: "flex", alignItems: "flex-start", gap: 14 }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 12,
                backgroundColor: "#f0fdf4",
                border: "1px solid #bbf7d0",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              {currentStepData.icon}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
                <span
                  style={{
                    fontSize: "0.7rem",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.5px",
                    color: "#2563eb",
                    background: "#eff6ff",
                    padding: "2px 8px",
                    borderRadius: 4,
                  }}
                >
                  {currentStepData.badge}
                </span>
                <span style={{ fontSize: "0.8rem", color: "#64748b" }}>
                  Step {currentStepData.step} of 6
                </span>
              </div>
              <h4
                style={{
                  fontSize: "1.15rem",
                  fontWeight: 700,
                  color: "#0f172a",
                  margin: "2px 0 4px 0",
                }}
              >
                {currentStepData.title}
              </h4>
              <p
                style={{
                  fontSize: "0.95rem",
                  fontWeight: 600,
                  color: "#1e293b",
                  margin: 0,
                  lineHeight: 1.45,
                }}
              >
                {currentStepData.summary}
              </p>
            </div>
          </div>

          {/* Step Explanatory Details */}
          <div
            style={{
              backgroundColor: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: 10,
              padding: "14px 18px",
            }}
          >
            <ul
              style={{
                margin: 0,
                paddingLeft: 20,
                fontSize: "0.88rem",
                color: "#334155",
                lineHeight: 1.6,
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              {currentStepData.details.map((detail, idx) => (
                <li key={idx}>{detail}</li>
              ))}
            </ul>
          </div>

          {/* Visual Hint Indicator */}
          {currentStepData.visualHint && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                fontSize: "0.82rem",
                color: "#475569",
                backgroundColor: "#f1f5f9",
                padding: "8px 14px",
                borderRadius: 8,
              }}
            >
              <Laptop size={15} color="#64748b" />
              <span>
                <strong>Target Area:</strong> <code>{currentStepData.visualHint}</code>
              </span>
            </div>
          )}

          {/* Step Alert / Important Callout if present */}
          {currentStepData.callout && (
            <div
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 12,
                borderRadius: 10,
                padding: "12px 16px",
                backgroundColor:
                  currentStepData.callout.type === "important" ? "#fef3c7" : "#ecfdf5",
                border:
                  currentStepData.callout.type === "important"
                    ? "1px solid #fde68a"
                    : "1px solid #a7f3d0",
                color:
                  currentStepData.callout.type === "important" ? "#92400e" : "#065f46",
              }}
            >
              <AlertTriangle size={18} style={{ flexShrink: 0, marginTop: 2 }} />
              <div style={{ fontSize: "0.86rem", lineHeight: 1.45, fontWeight: 500 }}>
                {currentStepData.callout.text}
              </div>
            </div>
          )}

          {/* Contextual Action Button */}
          {currentStepData.actionButton && (
            <div style={{ marginTop: 4 }}>
              <button
                type="button"
                onClick={currentStepData.actionButton.onClick}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  backgroundColor: "#2563eb",
                  color: "#ffffff",
                  fontWeight: 600,
                  fontSize: "0.88rem",
                  padding: "9px 18px",
                  borderRadius: 8,
                  border: "none",
                  cursor: "pointer",
                  boxShadow: "0 2px 4px rgba(37,99,235,0.2)",
                }}
              >
                <span>{currentStepData.actionButton.label}</span>
                <ChevronRight size={15} />
              </button>
            </div>
          )}
        </div>

        {/* Footer Navigation */}
        <div
          style={{
            padding: "14px 24px",
            borderTop: "1px solid #e2e8f0",
            backgroundColor: "#f8fafc",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: "0.82rem", color: "#64748b" }}>
              Keyboard: <kbd style={{ padding: "2px 5px", background: "#e2e8f0", borderRadius: 4, fontSize: "0.75rem" }}>←</kbd> / <kbd style={{ padding: "2px 5px", background: "#e2e8f0", borderRadius: 4, fontSize: "0.75rem" }}>→</kbd> to step
            </span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {activeStep > 1 && (
              <button
                type="button"
                onClick={() => setActiveStep((prev) => Math.max(prev - 1, 1))}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "7px 14px",
                  borderRadius: 6,
                  border: "1px solid #cbd5e1",
                  backgroundColor: "#ffffff",
                  color: "#334155",
                  fontSize: "0.84rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                <ChevronLeft size={14} />
                <span>Back</span>
              </button>
            )}

            {activeStep < 6 ? (
              <button
                type="button"
                onClick={() => setActiveStep((prev) => Math.min(prev + 1, 6))}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "7px 16px",
                  borderRadius: 6,
                  border: "none",
                  backgroundColor: "#2563eb",
                  color: "#ffffff",
                  fontSize: "0.84rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  boxShadow: "0 1px 3px rgba(37,99,235,0.3)",
                }}
              >
                <span>Next</span>
                <ChevronRight size={14} />
              </button>
            ) : (
              <button
                type="button"
                onClick={onClose}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "7px 18px",
                  borderRadius: 6,
                  border: "none",
                  backgroundColor: "#10b981",
                  color: "#ffffff",
                  fontSize: "0.84rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  boxShadow: "0 1px 3px rgba(16,185,129,0.3)",
                }}
              >
                <CheckCircle2 size={14} />
                <span>Complete Tour</span>
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
export default ConnectorTourModal;
