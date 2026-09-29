import React from "react";
import { Check, Lock, ChevronRight } from "lucide-react";

export interface WorkspacePhaseStepperProps {
  currentStage: number;
  setPage: (page: string) => void;
  phase1Active: boolean;
  phase1Completed: boolean;
  phase2Active: boolean;
  phase2Completed: boolean;
  phase3Active: boolean;
  phase3Completed: boolean;
  phase3Locked: boolean;
  stageConfig: Record<number, { page: string; label: string; phase: number; phaseName: string }>;
}

export const WorkspacePhaseStepper: React.FC<WorkspacePhaseStepperProps> = ({
  currentStage,
  setPage,
  phase1Active,
  phase1Completed,
  phase2Active,
  phase2Completed,
  phase3Active,
  phase3Completed,
  phase3Locked,
  stageConfig,
}) => {
  return (
    <div className="workspace-phase-stepper-wrap" role="navigation" aria-label="Migration Phases">
      <div className="workspace-phase-stepper">
        {/* Phase 1: Connect & Discover */}
        <div
          className={`workspace-phase-card ${phase1Active ? "active" : ""} ${phase1Completed ? "completed" : ""}`}
          onClick={() => {
            if (phase1Active) {
              setPage("Projects");
            } else {
              setPage("Discovery");
            }
          }}
          title="Phase 1: Connect & Discover (Stages 1–4: Projects, Environment, Sources, Discovery)"
        >
          <div className="phase-card-left">
            <div className={`workspace-phase-pip ${phase1Completed ? "completed" : phase1Active ? "active" : ""}`}>
              {phase1Completed ? <Check size={14} strokeWidth={3} /> : phase1Active ? <span className="pip-dot" /> : "1"}
            </div>
            <div className="workspace-phase-meta">
              <div className="phase-eyebrow">PHASE 1 · CONNECT &amp; DISCOVER</div>
              <div className="phase-primary-title">
                {phase1Completed
                  ? "Connect & Discovery"
                  : phase1Active
                  ? `Stage ${currentStage}: ${stageConfig[currentStage]?.label || "Projects"}`
                  : "Connect & Discover"}
              </div>
              <div className="phase-scope-desc">
                {phase1Completed ? "✓ Stages 1–4 Completed" : "Stages 1–4 · Sources & Catalog"}
              </div>
            </div>
          </div>
          <ChevronRight size={14} className="phase-card-arrow" />
        </div>

        {/* Connector Line 1 */}
        <div className={`workspace-connector ${phase1Completed ? "completed" : ""}`}>
          <div className="connector-bar" />
        </div>

        {/* Phase 2: Classify & Studio */}
        <div
          className={`workspace-phase-card ${phase2Active ? "active" : ""} ${phase2Completed ? "completed" : ""}`}
          onClick={() => {
            if (phase2Active) {
              setPage(stageConfig[currentStage]?.page || "Migration Workflow");
            } else {
              setPage("Migration Workflow");
            }
          }}
          title="Phase 2: Classify & Studio (Stages 5–7: Inventory, Layer Classification, Migration Studio)"
        >
          <div className="phase-card-left">
            <div className={`workspace-phase-pip ${phase2Completed ? "completed" : phase2Active ? "active" : ""}`}>
              {phase2Completed ? <Check size={14} strokeWidth={3} /> : phase2Active ? <span className="pip-dot" /> : "2"}
            </div>
            <div className="workspace-phase-meta">
              <div className="phase-eyebrow">PHASE 2 · CLASSIFY &amp; STUDIO</div>
              <div className="phase-primary-title">
                {phase2Completed
                  ? "Classify & Studio"
                  : phase2Active
                  ? `Stage ${currentStage}: ${stageConfig[currentStage]?.label || "Studio"}`
                  : "Classify & Studio"}
              </div>
              <div className="phase-scope-desc">
                {phase2Completed ? "✓ Stages 5–7 Completed" : "Stages 5–7 · Inventory & Migration Studio"}
              </div>
            </div>
          </div>
          <ChevronRight size={14} className="phase-card-arrow" />
        </div>

        {/* Connector Line 2 */}
        <div className={`workspace-connector ${phase2Completed ? "completed" : ""}`}>
          <div className="connector-bar" />
        </div>

        {/* Phase 3: Deploy & Cutover */}
        <div
          className={`workspace-phase-card ${phase3Active ? "active" : ""} ${phase3Completed ? "completed" : ""} ${phase3Locked ? "locked" : ""}`}
          onClick={() => {
            if (!phase3Locked) {
              setPage("Deployments");
            }
          }}
          title={
            phase3Locked
              ? "Phase 3 is locked until Stage 7 artifacts are generated and approved"
              : "Phase 3: Deploy & Cutover (Stages 8–9: Deployment, Lifecycle)"
          }
        >
          <div className="phase-card-left">
            <div className={`workspace-phase-pip ${phase3Completed ? "completed" : phase3Active ? "active" : phase3Locked ? "locked" : ""}`}>
              {phase3Completed ? (
                <Check size={14} strokeWidth={3} />
              ) : phase3Active ? (
                <span className="pip-dot" />
              ) : phase3Locked ? (
                <Lock size={12} />
              ) : (
                "3"
              )}
            </div>
            <div className="workspace-phase-meta">
              <div className="phase-eyebrow">PHASE 3 · DEPLOY &amp; CUTOVER</div>
              <div className="phase-primary-title">
                {phase3Completed
                  ? "Production Cutover Ready"
                  : phase3Active
                  ? `Stage ${currentStage}: ${stageConfig[currentStage]?.label || "Deployments"}`
                  : phase3Locked
                  ? "Deploy & Cutover (Locked)"
                  : "Deploy & Cutover"}
              </div>
              <div className="phase-scope-desc">
                {phase3Locked ? "🔒 Requires Studio Artifact Approval" : "Stages 8–9 · Deployments & Lifecycle"}
              </div>
            </div>
          </div>
          <ChevronRight size={14} className="phase-card-arrow" />
        </div>
      </div>
    </div>
  );
};

export default WorkspacePhaseStepper;
