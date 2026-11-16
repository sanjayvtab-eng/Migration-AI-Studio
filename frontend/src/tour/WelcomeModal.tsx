import React from "react";
import { Sparkles, ArrowRight, X } from "lucide-react";

interface WelcomeModalProps {
  isOpen: boolean;
  onStart: () => void;
  onSkip: () => void;
}

export function WelcomeModal({ isOpen, onStart, onSkip }: WelcomeModalProps) {
  if (!isOpen) return null;

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 99999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        backgroundColor: "rgba(15, 23, 42, 0.72)",
        backdropFilter: "blur(4px)",
        WebkitBackdropFilter: "blur(4px)",
        padding: "16px",
      }}
    >
      <div
        style={{
          background: "#ffffff",
          borderRadius: "16px",
          width: "100%",
          maxWidth: "440px",
          boxShadow: "0 25px 50px -12px rgba(15, 23, 42, 0.35), 0 0 0 1px rgba(226, 232, 240, 0.8)",
          padding: "26px 28px",
          position: "relative",
          animation: "mfWelcomePop 0.22s cubic-bezier(0.16, 1, 0.3, 1)",
          boxSizing: "border-box",
        }}
      >
        <button
          onClick={onSkip}
          aria-label="Close"
          style={{
            position: "absolute",
            top: "18px",
            right: "18px",
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "#94a3b8",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            padding: "4px",
            borderRadius: "6px",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = "#475569")}
          onMouseLeave={(e) => (e.currentTarget.style.color = "#94a3b8")}
        >
          <X size={18} />
        </button>

        <div
          style={{
            width: "44px",
            height: "44px",
            borderRadius: "12px",
            background: "linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)",
            color: "#2563eb",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "16px",
            border: "1px solid #bfdbfe",
          }}
        >
          <Sparkles size={22} />
        </div>

        <h3
          style={{
            margin: "0 0 8px 0",
            fontSize: "18px",
            fontWeight: 700,
            color: "#0f172a",
            letterSpacing: "-0.2px",
          }}
        >
          Welcome to Migration Factory
        </h3>

        <p
          style={{
            margin: "0 0 24px 0",
            fontSize: "14px",
            lineHeight: 1.55,
            color: "#64748b",
          }}
        >
          Want a quick 1-minute tour? We'll spotlight the essential controls across <strong>Projects</strong>, <strong>Sources</strong>, and <strong>Discovery</strong> to get your migration pipeline up and running.
        </p>

        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "flex-end",
            gap: "10px",
          }}
        >
          <button
            onClick={onSkip}
            style={{
              background: "transparent",
              border: "1px solid #e2e8f0",
              color: "#64748b",
              borderRadius: "8px",
              padding: "9px 16px",
              fontSize: "13.5px",
              fontWeight: 600,
              cursor: "pointer",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = "#f8fafc";
              e.currentTarget.style.color = "#0f172a";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "transparent";
              e.currentTarget.style.color = "#64748b";
            }}
          >
            Skip for now
          </button>

          <button
            onClick={onStart}
            style={{
              background: "#2563eb",
              border: "1px solid #1d4ed8",
              color: "#ffffff",
              borderRadius: "8px",
              padding: "9px 18px",
              fontSize: "13.5px",
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: "6px",
              boxShadow: "0 2px 4px rgba(37, 99, 235, 0.25)",
              transition: "all 0.15s ease",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.backgroundColor = "#1d4ed8";
              e.currentTarget.style.transform = "translateY(-0.5px)";
              e.currentTarget.style.boxShadow = "0 4px 10px rgba(37, 99, 235, 0.35)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.backgroundColor = "#2563eb";
              e.currentTarget.style.transform = "translateY(0)";
              e.currentTarget.style.boxShadow = "0 2px 4px rgba(37, 99, 235, 0.25)";
            }}
          >
            <span>Start tour</span>
            <ArrowRight size={15} />
          </button>
        </div>
      </div>
    </div>
  );
}
