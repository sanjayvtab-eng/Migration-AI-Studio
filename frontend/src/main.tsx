import React from 'react';
import { createRoot } from 'react-dom/client';
import './styles.css';
import App from './App';

class RootErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: any }
> {
  constructor(props: any) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error: any) {
    return { hasError: true, error };
  }
  componentDidCatch(error: any, errorInfo: any) {
    console.error("RootErrorBoundary caught an unhandled error:", error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "#0f172a",
          padding: 24,
          fontFamily: "system-ui, -apple-system, sans-serif",
          color: "#f8fafc"
        }}>
          <div style={{
            maxWidth: 600,
            width: "100%",
            background: "#1e293b",
            borderRadius: 12,
            padding: 32,
            boxShadow: "0 20px 25px -5px rgba(0,0,0,0.5)",
            border: "1px solid #334155",
            textAlign: "center"
          }}>
            <div style={{ fontSize: 40, marginBottom: 16 }}>⚠️</div>
            <h2 style={{ fontSize: 20, fontWeight: 700, margin: "0 0 12px 0", color: "#f87171" }}>
              Something went wrong in the view
            </h2>
            <p style={{ fontSize: 13, color: "#94a3b8", margin: "0 0 20px 0" }}>
              An unexpected render error occurred. The details have been caught safely:
            </p>
            <div style={{
              background: "#0f172a",
              padding: 16,
              borderRadius: 8,
              textAlign: "left",
              fontFamily: "monospace",
              fontSize: 12,
              color: "#fbbf24",
              overflowX: "auto",
              marginBottom: 24,
              maxHeight: 200
            }}>
              {String(this.state.error?.message || this.state.error || "Unknown error")}
            </div>
            <button
              onClick={() => {
                this.setState({ hasError: false, error: null });
                window.location.reload();
              }}
              style={{
                background: "#2563eb",
                color: "#fff",
                border: "none",
                padding: "10px 24px",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer"
              }}
            >
              Reload Application
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <App />
    </RootErrorBoundary>
  </React.StrictMode>
);
