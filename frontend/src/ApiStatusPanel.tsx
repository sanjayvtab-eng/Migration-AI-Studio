import React, { useState, useEffect, useMemo } from "react";
import { Activity, RefreshCw, Zap, Server, Cpu, CheckCircle2, AlertTriangle, XCircle, AlertCircle } from "lucide-react";
import { api } from "./api";

interface HealthData {
  status: "operational" | "quota_exceeded" | "failed" | "degraded" | string;
  backend: {
    status: string;
    latencyMs?: number;
  };
  databricks?: {
    status: string;
    error?: string | null;
  };
  gemini: {
    status: string;
    model: string;
    latencyMs?: number;
    error?: string | null;
  };
  failureReason?: string | null;
  checkedAt: string;
}

interface ApiStatusPanelProps {
  projectId?: string | null;
  runtimeError?: string | null;
  deploymentFailed?: boolean;
}

export function ApiStatusPanel({ projectId, runtimeError, deploymentFailed }: ApiStatusPanelProps) {
  const [data, setData] = useState<HealthData | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastCheckTime, setLastCheckTime] = useState<string>("-");

  const fetchHealth = async () => {
    setLoading(true);
    try {
      const url = projectId ? `/public/health?project_id=${projectId}` : "/public/health";
      const res: any = await api(url);
      setData(res);
      const now = new Date();
      setLastCheckTime(`${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`);
    } catch (err: any) {
      setData({
        status: "failed",
        backend: { status: "unavailable" },
        databricks: { status: "error", error: err.message },
        gemini: { status: "error", model: "unknown", error: err.message },
        failureReason: err.message || "Failed to reach backend",
        checkedAt: new Date().toISOString(),
      });
      const now = new Date();
      setLastCheckTime(`${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    // Auto-refresh every 5 minutes
    const interval = setInterval(() => {
      fetchHealth();
    }, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [projectId]);

  // Combine backend-reported error with live runtime client error (e.g. from terminal or deployment)
  const activeFailureReason = useMemo(() => {
    return runtimeError || data?.failureReason || data?.databricks?.error || data?.gemini?.error || null;
  }, [runtimeError, data]);

  const isQuotaExceeded = useMemo(() => {
    const s = (activeFailureReason || "").toLowerCase();
    return s.includes("quota_exceeded") || (s.includes("quota") && s.includes("exceeded")) || (s.includes("limit") && s.includes("500"));
  }, [activeFailureReason]);

  const isPortOrGatewayError = useMemo(() => {
    const s = (activeFailureReason || "").toLowerCase();
    return s.includes("404") || s.includes("504") || s.includes("gateway") || s.includes("port") || s.includes("timeout") || s.includes("connect");
  }, [activeFailureReason]);

  const isFailed = deploymentFailed || Boolean(activeFailureReason) || data?.status === "failed" || data?.status === "quota_exceeded";
  const isOperational = !isFailed && data?.status === "operational";

  return (
    <div className="api-status-panel">
      {/* Panel Header */}
      <div className="api-status-header">
        <div className="api-status-title-row">
          <Zap size={13} className={isFailed ? "api-status-icon text-rose-400" : "api-status-icon"} />
          <span className="api-status-title">AI & BACKEND STATUS</span>
        </div>
        <div
          className={`api-status-badge ${
            isQuotaExceeded
              ? "error"
              : isFailed
              ? "error"
              : isOperational
              ? "operational"
              : "degraded"
          }`}
        >
          <span className="status-dot-pulse" />
          <span>
            {isQuotaExceeded
              ? "Quota Exceeded"
              : isFailed
              ? "Failed"
              : isOperational
              ? "Operational"
              : "Degraded"}
          </span>
        </div>
      </div>

      {/* 3 Micro Cards Grid: Backend API, Databricks UC, Gemini AI */}
      <div className="api-status-grid">
        {/* Card 1: Backend API */}
        <div className="api-micro-card">
          <div className="api-card-label">BACKEND API</div>
          <div className="api-card-value">
            {data?.backend?.status === "connected" ? (
              <span className="status-text connected">
                <span className="dot dot-green" />
                Connected
              </span>
            ) : (
              <span className="status-text error">
                <span className="dot dot-red" />
                Unavailable
              </span>
            )}
          </div>
          {data?.backend?.latencyMs != null && (
            <div className="api-card-sub">{data.backend.latencyMs}ms</div>
          )}
        </div>

        {/* Card 2: Databricks / DEV Environment */}
        <div className="api-micro-card">
          <div className="api-card-label">DATABRICKS DEV</div>
          <div className="api-card-value">
            {isQuotaExceeded ? (
              <span className="status-text error" title="Metastore Quota: 500 table limit reached">
                <span className="dot dot-red" />
                Quota Exceeded
              </span>
            ) : isPortOrGatewayError ? (
              <span className="status-text error" title={activeFailureReason || "Port/Gateway Timeout"}>
                <span className="dot dot-red" />
                Gateway Error
              </span>
            ) : isFailed || data?.databricks?.status === "failed" ? (
              <span className="status-text error" title={activeFailureReason || "Execution Failed"}>
                <span className="dot dot-red" />
                Failed
              </span>
            ) : (
              <span className="status-text connected">
                <span className="dot dot-green" />
                Connected
              </span>
            )}
          </div>
          <div className={`api-card-sub ${isQuotaExceeded || isFailed ? "text-rose-400" : ""}`}>
            {isQuotaExceeded ? "Limit 500 reached" : "Unity Catalog"}
          </div>
        </div>

        {/* Card 3: Gemini AI */}
        <div className="api-micro-card">
          <div className="api-card-label">GEMINI AI</div>
          <div className="api-card-value">
            {data?.gemini?.status === "connected" ? (
              <span className="status-text connected">
                <span className="dot dot-green" />
                Connected
              </span>
            ) : (
              <span className="status-text error" title={data?.gemini?.error || "Auth or Quota Error"}>
                <span className="dot dot-red" />
                {data?.gemini?.error?.includes("quota") ? "Quota Limit" : "Error"}
              </span>
            )}
          </div>
          <div className="api-card-sub model-tag" title={data?.gemini?.model || "gemini-3.5-flash"}>
            {data?.gemini?.model ? (
              data.gemini.model.length > 12 ? `${data.gemini.model.slice(0, 10)}...` : data.gemini.model
            ) : (
              "gemini-3.5-flash"
            )}
          </div>
        </div>
      </div>

      {/* Error Reason Banner (Explicitly shows WHY it failed / quota reached) */}
      {isFailed && activeFailureReason && (
        <div className="api-status-error-alert">
          <AlertCircle size={13} className="api-error-alert-icon" />
          <div className="api-error-alert-body">
            <div className="api-error-alert-title">
              {isQuotaExceeded
                ? "Metastore Quota Exceeded (Limit: 500 reached)"
                : isPortOrGatewayError
                ? "Port / Gateway Error (404/504 Timeout)"
                : "Execution Failure Detected"}
            </div>
            <div className="api-error-alert-detail" title={activeFailureReason}>
              {activeFailureReason.length > 140
                ? `${activeFailureReason.slice(0, 137)}...`
                : activeFailureReason}
            </div>
          </div>
        </div>
      )}

      {/* Action Footer */}
      <div className="api-status-footer">
        <button
          type="button"
          className="api-refresh-btn"
          onClick={(e) => {
            e.stopPropagation();
            fetchHealth();
          }}
          disabled={loading}
          title="Probe backend, Databricks, and Gemini status"
        >
          <RefreshCw size={11} className={loading ? "spin" : ""} />
          <span>{loading ? "Checking..." : "Check connection"}</span>
        </button>

        <div className="api-refresh-info">
          <span>Last checked: {lastCheckTime}</span>
          <span className="auto-refresh-tag">• Auto-refreshes every 5 min</span>
        </div>
      </div>
    </div>
  );
}
