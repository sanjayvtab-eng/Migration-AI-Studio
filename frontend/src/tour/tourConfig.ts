export interface TourStep {
  id: string;
  stage: string;
  stageNumber: number;
  stepNumber: number;
  totalSteps: number;
  element: string;
  isCenteredModal?: boolean;
  nextBtnText?: string;
  popover: {
    title: string;
    description: string;
    side?: "top" | "right" | "bottom" | "left";
    align?: "start" | "center" | "end";
  };
  actionType?: "click" | "info";
  actionHint?: string;
  advanceOnEvent?: string;
  condition?: (context: any) => boolean;
  waitForElement?: boolean;
  scrollIntoView?: boolean;
  disableBack?: boolean;
}

export const TOUR_STEPS: TourStep[] = [
  // Stage 1: Projects (Steps 1 & 2)
  {
    id: "step-1-new-project",
    stage: "Projects",
    stageNumber: 1,
    stepNumber: 1,
    totalSteps: 9,
    element: '[data-tour="new-project-btn"]',
    popover: {
      title: "Create a project",
      description: "Start here. Create a new project to register your migration pipeline, then it will appear in the table below.",
      side: "bottom",
      align: "end",
    },
    actionType: "click",
    advanceOnEvent: "project-created",
    disableBack: true,
    condition: (context: any) => !context.isDemoAccount,
  },
  {
    id: "step-1-demo-project",
    stage: "Projects",
    stageNumber: 1,
    stepNumber: 1,
    totalSteps: 9,
    element: '[data-tour="project-row-demo"]',
    popover: {
      title: "Explore the pre-configured project",
      description: "For this demo, we've pre-configured the 'Demo' project connected to a live SQL Server database. Click the Demo project row to select it.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "project-selected",
    disableBack: true,
    condition: (context: any) => Boolean(context.isDemoAccount),
  },
  {
    id: "step-2-proceed-sources",
    stage: "Projects",
    stageNumber: 1,
    stepNumber: 2,
    totalSteps: 9,
    element: '[data-tour="proceed-sources-btn"]',
    popover: {
      title: "Continue with Selected Project",
      description: "Once your project is selected, click Continue to configure your target Databricks environment.",
      side: "top",
      align: "end",
    },
    condition: (context: any) => Boolean(context.hasProject || context.isDemoAccount),
  },

  // Stage 2: Environment Setup (Steps 1 to 8 - Active for Non-Demo Users)
  {
    id: "env-choose-prereq",
    stage: "Environment Setup",
    stageNumber: 2,
    stepNumber: 1,
    totalSteps: 8,
    element: '[data-tour="env-prereq-modal"]',
    popover: {
      title: "Target Databricks Account & Workspace Setup",
      description: "Select whether you have an existing Databricks workspace ('I Have an Account'), need to create a new trial account, or want to start instantly with our pre-configured trial account.",
      side: "top",
      align: "center",
    },
    actionType: "click",
    actionHint: "Select an account option below to proceed",
    advanceOnEvent: "env:prereq-selected",
    disableBack: true,
    condition: (context: any) => !context.isDemoAccount && Boolean(context.showDatabricksPrereqModal),
  },
  {
    id: "env-save-config",
    stage: "Environment Setup",
    stageNumber: 2,
    stepNumber: 2,
    totalSteps: 8,
    element: '[data-tour="env-save-config-btn"]',
    popover: {
      title: "Save Databricks Configuration",
      description: "Enter your Workspace Host, SQL Warehouse Path, and Personal Access Token (PAT) above, then click Save Configuration to encrypt credentials.",
      side: "top",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "env:config-saved",
    disableBack: true,
    condition: (context: any) => !context.isDemoAccount && !context.showDatabricksPrereqModal,
  },
  {
    id: "env-test-connection",
    stage: "Environment Setup",
    stageNumber: 2,
    stepNumber: 3,
    totalSteps: 8,
    element: '[data-tour="env-test-connection-btn"]',
    popover: {
      title: "Test Databricks Connection",
      description: "Click Test Connection to verify live reachability to Databricks SQL Warehouse and Unity Catalog.",
      side: "top",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "env:connection-tested",
    disableBack: true,
    condition: (context: any) => !context.isDemoAccount,
  },
  {
    id: "env-create-plan",
    stage: "Environment Setup",
    stageNumber: 2,
    stepNumber: 4,
    totalSteps: 8,
    element: '[data-tour="env-create-plan-btn"]',
    popover: {
      title: "Create DEV Plan",
      description: "Click Create DEV Plan to generate the governed deployment plan and target medallion schemas (Bronze, Silver, Gold).",
      side: "bottom",
      align: "end",
    },
    actionType: "click",
    advanceOnEvent: "env:plan-created",
    disableBack: true,
    condition: (context: any) => !context.isDemoAccount,
  },
  {
    id: "env-run-preflight",
    stage: "Environment Setup",
    stageNumber: 2,
    stepNumber: 5,
    totalSteps: 8,
    element: '[data-tour="env-run-preflight-btn"]',
    popover: {
      title: "Run Preflight Validation",
      description: "Click Run Preflight to validate catalog privileges, SQL warehouse readiness, and verify zero destructive operations.",
      side: "top",
      align: "end",
    },
    actionType: "click",
    advanceOnEvent: "env:preflight-completed",
    disableBack: true,
    waitForElement: true,
    scrollIntoView: true,
    condition: (context: any) => !context.isDemoAccount,
  },
  {
    id: "env-approve-plan",
    stage: "Environment Setup",
    stageNumber: 2,
    stepNumber: 6,
    totalSteps: 8,
    element: '[data-tour="env-approve-plan-btn"]',
    popover: {
      title: "Approve Environment Plan",
      description: "Review and approve the validated DEV execution plan to authorize deploying the schemas into Databricks.",
      side: "top",
      align: "end",
    },
    actionType: "click",
    advanceOnEvent: "env:plan-approved",
    disableBack: true,
    scrollIntoView: true,
    condition: (context: any) => !context.isDemoAccount,
  },
  {
    id: "env-provision-dev",
    stage: "Environment Setup",
    stageNumber: 2,
    stepNumber: 7,
    totalSteps: 8,
    element: '[data-tour="env-provision-dev-btn"]',
    popover: {
      title: "Provision to DEV",
      description: "Click Provision DEV to deploy and instantiate the live managed schemas into Databricks Unity Catalog.",
      side: "top",
      align: "end",
    },
    actionType: "click",
    advanceOnEvent: "env:provision-completed",
    disableBack: true,
    scrollIntoView: true,
    condition: (context: any) => !context.isDemoAccount,
  },
  {
    id: "env-proceed-sources",
    stage: "Environment Setup",
    stageNumber: 2,
    stepNumber: 8,
    totalSteps: 8,
    element: '[data-tour="env-proceed-sources-btn"]',
    popover: {
      title: "Proceed to Sources",
      description: "DEV environment is provisioned and ready! Click Proceed to Sources to connect your database profiles.",
      side: "top",
      align: "end",
    },
    actionType: "click",
    disableBack: true,
    scrollIntoView: true,
    condition: (context: any) => !context.isDemoAccount,
  },

  // Stage 3: Sources (Steps 3, 4, 5, 6)
  {
    id: "step-3-add-source",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 3,
    totalSteps: 9,
    element: '[data-tour="add-source-btn"]',
    popover: {
      title: "Add Data Source",
      description: "Click Add Source to register your database connection profile (SQL Server, PostgreSQL, MySQL, or Oracle) to begin migration.",
      side: "bottom",
      align: "center",
    },
    actionType: "click",
    actionHint: "Click the highlighted button to add a source",
    advanceOnEvent: "source-created",
    disableBack: false,
    condition: (context: any) => !context.isDemoAccount && (!context.sourcesCount || context.sourcesCount === 0),
  },
  {
    id: "step-3-connector-agent",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 3,
    totalSteps: 9,
    element: '[data-tour="connector-agent-btn"]',
    popover: {
      title: "Local Connector Agent – Guided Tour",
      description:
        "Step 1 – Open Connector Agent: Click the Connector Agent option to open registration.\nStep 2 – Generate Token: Click 'Generate a New Token' for a secure token.\nStep 3 – Download Connector: Download the EXE & ENV files.\nStep 4 – Register: Run the agent on your machine.\nStep 5 – Verify Sources: Check your sources at localhost:8585.\nStep 6 – Verify Connection: Confirm setup before testing.\n\nImportant: Whenever you add a new data source, download and apply the latest ENV configuration so the Local Connector receives the updated source credentials.",
      side: "bottom",
      align: "end",
    },
    actionType: "click",
    actionHint: "Open Connector Agent, then generate a registration token",
    advanceOnEvent: "connector:token-generated",
    disableBack: false,
    scrollIntoView: true,
  },
  {
    id: "connector-generate-token",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 1,
    totalSteps: 4,
    element: '[data-tour="generate-connector-token-btn"]',
    popover: {
      title: "Step 1: Generate Registration Token",
      description: "Click 'Generate New Token' (or 'Register Connector Agent') to create a secure authentication token for your local database connector.",
      side: "top",
      align: "start",
    },
    actionType: "click",
    actionHint: "Click to generate or register connector token",
    advanceOnEvent: "connector:token-generated",
    disableBack: true,
  },
  {
    id: "connector-download-env",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 2,
    totalSteps: 4,
    element: '[data-tour="download-agent-env-btn"]',
    popover: {
      title: "Step 2: Download Configuration File",
      description: "Download the pre-configured agent.env file containing this source's connection details. Downloading this unlocks the connector executable.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    actionHint: "Download agent.env to unlock the executable download",
    advanceOnEvent: "connector:env-downloaded",
    disableBack: true,
  },
  {
    id: "connector-download-exe",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 3,
    totalSteps: 4,
    element: '[data-tour="download-agent-exe-btn"]',
    popover: {
      title: "Step 3: Download Connector Executable",
      description: "Download migration-agent.exe and place it in the same directory as agent.env. Launch it and keep its console open.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    actionHint: "Download migration-agent.exe",
    advanceOnEvent: "connector:exe-downloaded",
    disableBack: true,
  },
  {
    id: "connector-close-modal",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 4,
    totalSteps: 4,
    element: '[data-tour="connector-close-btn"]',
    popover: {
      title: "Step 4: Close Dialog",
      description: "Both files are downloaded! Close this dialog to proceed with launching migration-agent.exe and testing connectivity.",
      side: "top",
      align: "end",
    },
    actionType: "click",
    actionHint: "Close this dialog to proceed",
    advanceOnEvent: "connector-agent-closed",
    disableBack: true,
  },
  {
    id: "connector-launch-agent-guide",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 4,
    totalSteps: 9,
    element: '[data-tour="connector-status-pill"], [data-tour="test-connection-btn"]',
    isCenteredModal: true,
    nextBtnText: "Proceed to Test Connection →",
    popover: {
      title: "⚡ Step 5 – Launch Migration Agent (.exe)",
      description: `
<div style="margin-top: 4px;">
  <div style="background: linear-gradient(135deg, #fef2f2 0%, #fee2e2 100%); border: 1.5px solid #ef4444; border-radius: 10px; padding: 12px 14px; margin-bottom: 14px; display: flex; align-items: center; gap: 10px; box-shadow: 0 2px 6px rgba(239, 68, 68, 0.1);">
    <span style="font-size: 24px; line-height: 1;">🚨</span>
    <div>
      <div style="font-size: 13px; font-weight: 800; color: #b91c1c; text-transform: uppercase; letter-spacing: 0.5px;">ACTION REQUIRED BEFORE TEST CONNECTION</div>
      <div style="font-size: 12px; font-weight: 700; color: #7f1d1d; margin-top: 2px;">The connector agent must be launched locally for connection testing to pass.</div>
    </div>
  </div>

  <div style="display: flex; flex-direction: column; gap: 9px; margin-bottom: 14px;">
    <div style="background: #f8fafc; border: 1.5px solid #cbd5e1; border-left: 5px solid #2563eb; border-radius: 9px; padding: 10px 14px;">
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 3px;">
        <span style="background: #2563eb; color: #ffffff; font-weight: 800; font-size: 11px; width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;">1</span>
        <span style="font-size: 13.5px; font-weight: 800; color: #0f172a;">Launch the Executable File:</span>
      </div>
      <div style="font-size: 13px; font-weight: 600; color: #1e293b; padding-left: 30px;">
        Open the downloaded <strong style="color: #0f172a; background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">migration-agent.exe</strong> in the exact same folder as <strong style="color: #0f172a; background: #e2e8f0; padding: 2px 6px; border-radius: 4px; font-family: monospace;">agent.env</strong>.
      </div>
    </div>

    <div style="background: #fffbeb; border: 1.5px solid #f59e0b; border-left: 5px solid #d97706; border-radius: 9px; padding: 10px 14px;">
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 3px;">
        <span style="background: #d97706; color: #ffffff; font-weight: 800; font-size: 11px; width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;">2</span>
        <span style="font-size: 13.5px; font-weight: 800; color: #92400e;">DO NOT CLOSE — JUST MINIMIZE:</span>
      </div>
      <div style="font-size: 13px; font-weight: 700; color: #78350f; padding-left: 30px;">
        ⚠️ Keep the console window running! <strong>DO NOT CLOSE IT</strong> — just <strong>MINIMIZE</strong> the window so it stays connected.
      </div>
    </div>

    <div style="background: #f0fdf4; border: 1.5px solid #86efac; border-left: 5px solid #16a34a; border-radius: 9px; padding: 10px 14px;">
      <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
        <span style="background: #16a34a; color: #ffffff; font-weight: 800; font-size: 11px; width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center;">3</span>
        <span style="font-size: 13.5px; font-weight: 800; color: #14532d;">View Live Streaming Logs:</span>
      </div>
      <div style="font-size: 13px; font-weight: 700; color: #166534; padding-left: 30px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px;">
        <span>The agent streams logs and status at:</span>
        <a href="http://localhost:8585" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()" style="display: inline-flex; align-items: center; gap: 5px; background: #16a34a; color: #ffffff; padding: 3px 10px; border-radius: 6px; font-weight: 800; text-decoration: none; font-size: 12px; box-shadow: 0 2px 4px rgba(22, 163, 74, 0.25);">
          <span style="width: 7px; height: 7px; border-radius: 50%; background: #86efac; display: inline-block;"></span>
          http://localhost:8585 ↗
        </a>
      </div>
    </div>
  </div>

  <div style="background: #f1f5f9; border-radius: 8px; padding: 8px 12px; font-size: 12.5px; font-weight: 700; color: #334155; text-align: center;">
    👉 After minimizing the agent console, click <strong>"Proceed to Test Connection →"</strong> below.
  </div>
</div>`,
      side: "bottom",
      align: "center",
    },
    disableBack: true,
  },
  {
    id: "step-4-test-connection",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 5,
    totalSteps: 9,
    element: '[data-tour="test-connection-btn"]',
    popover: {
      title: "Step 6 – Verify Connection & Test",
      description:
        "Confirm that the newly added sources and their configurations are available in the Local Connector before proceeding with Test Connection. Click the highlighted button to verify live reachability.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    actionHint: "Click the highlighted button to test live connectivity",
    advanceOnEvent: "test-connection-completed",
    disableBack: false,
  },
  {
    id: "step-5-test-results",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 6,
    totalSteps: 9,
    element: '[data-tour="test-results-panel"]',
    popover: {
      title: "Review the results",
      description: "Scroll down to Source Connection Test Results to confirm the TCP, authentication, database access and privilege checks all passed.",
      side: "top",
      align: "center",
    },
    waitForElement: true,
    scrollIntoView: true,
  },
  {
    id: "step-6-proceed-discovery",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 7,
    totalSteps: 9,
    element: '[data-tour="proceed-discovery-btn"]',
    popover: {
      title: "Move on to Discovery",
      description: "All checks passed. Continue to schema discovery.",
      side: "top",
      align: "end",
    },
  },

  // Stage 4: Discovery (Steps 8 & 9)
  {
    id: "step-7-run-discovery",
    stage: "Discovery",
    stageNumber: 4,
    stepNumber: 8,
    totalSteps: 9,
    element: '[data-tour="run-discovery-btn"]',
    popover: {
      title: "Run schema discovery",
      description: "Scan the source catalog to detect tables, relationships and migration readiness.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "discovery-completed",
    disableBack: true,
  },
  {
    id: "step-8-proceed-studio",
    stage: "Discovery",
    stageNumber: 4,
    stepNumber: 9,
    totalSteps: 9,
    element: '[data-tour="proceed-studio-btn"]',
    popover: {
      title: "Open Migration Studio",
      description: "Discovery complete. Proceed to Migration Studio to classify and plan your migration.",
      side: "top",
      align: "end",
    },
    actionType: "click",
    actionHint: "Click to proceed to Migration Studio",
    advanceOnEvent: "proceed-to-studio",
  },

  // Stage 7: Migration Studio (Steps mapped to studioTourStateMap)
  {
    id: "studio-enter-prompt",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 1,
    totalSteps: 10,
    element: '[data-tour="studio-prompt-input"]',
    popover: {
      title: "Step 1: Enter Migration Prompt",
      description: "Review or edit your Bronze, Silver, and Gold migration requirements here. Click into this prompt box to proceed to parsing.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    actionHint: "Click prompt box or edit prompt to proceed",
    advanceOnEvent: "studio:prompt-entered",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-parse-prompt",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 2,
    totalSteps: 10,
    element: '[data-tour="studio-parse-btn"]',
    popover: {
      title: "Step 2: Parse and Ground Prompt",
      description: "Click 'Parse and Ground Prompt' to ground your instructions against discovered source metadata.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "studio:prompt-parsed",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-clarifications-defaults",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 3,
    totalSteps: 10,
    element: '[data-tour="studio-clarifications-defaults-btn"]',
    popover: {
      title: "Step 3: Requirement Clarifications",
      description: "Policy-governed clarification questions detected. Click 'Use recommended defaults' to auto-populate approved answers.",
      side: "top",
      align: "start",
    },
    actionType: "click",
    actionHint: "Click 'Use recommended defaults'",
    advanceOnEvent: "studio:defaults-applied",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-clarifications-save",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 4,
    totalSteps: 10,
    element: '[data-tour="studio-clarifications-save-btn"]',
    popover: {
      title: "Step 4: Save Answers and Re-ground",
      description: "Click 'Save Answers and Re-ground' to commit clarified design rules and generate the Medallion architecture plan.",
      side: "top",
      align: "end",
    },
    actionType: "click",
    actionHint: "Click 'Save Answers and Re-ground'",
    advanceOnEvent: "studio:clarifications-saved",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-approve-plan",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 5,
    totalSteps: 11,
    element: '[data-tour="studio-approve-plan-btn"]',
    popover: {
      title: "Step 5: Review Grounded Plan & Approve",
      description: "Review the Grounded Medallion Artifacts Plan highlighted below (Bronze, Silver, Gold). Click 'Approve Exact Plan' above to authorize artifact generation.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    actionHint: "Review plan below and click Approve Exact Plan",
    advanceOnEvent: "studio:plan-approved",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-generate-artifacts",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 6,
    totalSteps: 11,
    element: '[data-tour="studio-generate-artifacts-btn"]',
    popover: {
      title: "Step 6: Generate Artifacts",
      description: "Plan approved! Click 'Generate Artifacts' to synthesize the Bronze, Silver, and Gold medallion artifacts.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    actionHint: "Click Generate Artifacts to synthesize artifacts",
    advanceOnEvent: "studio:artifacts-generated",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-review-artifacts",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 7,
    totalSteps: 11,
    element: '[data-tour="studio-validate-databricks-btn"]',
    popover: {
      title: "Step 7: Review Artifacts & Validate in Databricks",
      description: "Artifacts synthesized! Review the 38 Medallion artifacts in the Inline Reviews panel on the right, and click 'Validate in Databricks' here to test against Databricks target schemas.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    actionHint: "Click Validate in Databricks to test artifacts",
    advanceOnEvent: "studio:artifacts-validated",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-validate-databricks",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 7,
    totalSteps: 10,
    element: '[data-tour="studio-validate-databricks-btn"]',
    popover: {
      title: "Step 7: Validate in Databricks",
      description: "Validate the generated SQL against your Databricks target before approving.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "studio:artifacts-validated",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-approve-artifacts",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 8,
    totalSteps: 10,
    element: '[data-tour="studio-approve-artifacts-btn"]',
    popover: {
      title: "Step 8: Approve Current Artifacts",
      description: "Approve each validated artifact version so it can be deployed to DEV.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "studio:artifacts-approved",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-deploy-dev",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 9,
    totalSteps: 10,
    element: '[data-tour="studio-deploy-dev-btn"]',
    popover: {
      title: "Step 9: Deploy and Validate on DEV",
      description: "Deploy the approved artifacts to the DEV environment and run validation.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "studio:dev-deployed",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-proceed-promotion",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 10,
    totalSteps: 10,
    element: '[data-tour="studio-primary-action"]',
    popover: {
      title: "Step 10: Proceed to Promotion",
      description: "DEV passed. Continue to promotion to take these artifacts forward.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    scrollIntoView: true,
  },

  // Stage 8: Deployment (DEV)
  {
    id: "deploy-authorize-promotion",
    stage: "Deployments",
    stageNumber: 8,
    stepNumber: 1,
    totalSteps: 2,
    element: '[data-tour="authorize-promotion-btn"]',
    popover: {
      title: "Authorize promotion",
      description: "DEV is verified. Authorize automated promotion through TEST, UAT and PROD.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "deploy:modal-opened",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "deploy-confirm-promotion",
    stage: "Deployments",
    stageNumber: 8,
    stepNumber: 2,
    totalSteps: 2,
    element: '[data-tour="promotion-confirm-btn"]',
    popover: {
      title: "Confirm promotion to PROD",
      description: "Review and confirm to start the promotion through to PROD.",
      side: "top",
      align: "end",
    },
    actionType: "click",
    advanceOnEvent: "deploy:promotion-confirmed",
    waitForElement: true,
    scrollIntoView: true,
  },
];

/**
 * State-derived map for Stage 2 (Environment Setup)
 */
export const deriveEnvStepId = (
  environmentConfig: any,
  environmentPlan: any,
  showDatabricksPrereqModal?: boolean
): string => {
  if (showDatabricksPrereqModal) {
    return "env-choose-prereq";
  }
  if (environmentPlan?.status === "PROVISIONED") {
    return "env-proceed-sources";
  }
  if (environmentPlan?.status === "APPROVED") {
    return "env-provision-dev";
  }
  if (environmentPlan?.status === "PREFLIGHT_PASSED") {
    return "env-approve-plan";
  }
  if (environmentPlan?.exists) {
    return "env-run-preflight";
  }
  if (environmentConfig?.status === "READY") {
    return "env-create-plan";
  }
  if (environmentConfig?.configured) {
    return "env-test-connection";
  }
  return "env-save-config";
};

/**
 * State-derived map for Stage 7 (Migration Studio)
 */
export const deriveStudioStepId = (
  promptSpec: any,
  isDevAlreadyPassed: boolean,
  hasInteractedPrompt?: boolean,
  hasAppliedDefaults?: boolean
): string => {
  if (isDevAlreadyPassed || promptSpec?.status === "DEV_GATE_PASSED") {
    return "studio-proceed-promotion";
  }

  // Check if requirement clarification questions are open
  const hasOpenClarifications = Boolean(
    promptSpec?.clarifications?.some((q: any) => q.status === "OPEN")
  );
  if (hasOpenClarifications) {
    if (hasAppliedDefaults) {
      return "studio-clarifications-save";
    }
    return "studio-clarifications-defaults";
  }

  if (!promptSpec || !promptSpec.status || promptSpec.status === "DRAFT") {
    if (!hasInteractedPrompt) {
      return "studio-enter-prompt";
    }
    return "studio-parse-prompt";
  }
  if (promptSpec.status === "PENDING_PLAN_APPROVAL") {
    return "studio-approve-plan";
  }
  if (promptSpec.status === "PLAN_APPROVED") {
    return "studio-generate-artifacts";
  }
  if (["VALIDATING", "TARGET_VALIDATION_FAILED"].includes(promptSpec.status)) {
    return "studio-review-artifacts";
  }
  if (promptSpec.status === "PENDING_ARTIFACT_REVIEW") {
    return "studio-approve-artifacts";
  }
  if (["ARTIFACTS_APPROVED", "DEV_DEPLOYMENT_FAILED", "DEPLOYING_DEV"].includes(promptSpec.status)) {
    return "studio-deploy-dev";
  }
  return "studio-parse-prompt";
};

export const getStepsForStage = (stage: string, context: any = {}): TourStep[] => {
  return TOUR_STEPS.filter((step) => {
    if (step.stage !== stage) return false;
    if (step.condition && !step.condition(context)) return false;
    return true;
  });
};
