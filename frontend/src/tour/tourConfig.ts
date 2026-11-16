export interface TourStep {
  id: string;
  stage: string;
  stageNumber: number;
  stepNumber: number;
  totalSteps: number;
  element: string;
  popover: {
    title: string;
    description: string;
    side?: "top" | "right" | "bottom" | "left";
    align?: "start" | "center" | "end";
  };
  actionType?: "click" | "info";
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
  },
  {
    id: "step-2-proceed-sources",
    stage: "Projects",
    stageNumber: 1,
    stepNumber: 2,
    totalSteps: 9,
    element: '[data-tour="proceed-sources-btn"]',
    popover: {
      title: "Continue to Sources",
      description: "Once your project is created, proceed to Sources to connect your database.",
      side: "top",
      align: "end",
    },
    condition: (context: any) => Boolean(context.hasProject || context.isDemoAccount),
  },

  // Stage 3: Sources (Steps 3, 4, 5)
  {
    id: "step-3-test-connection",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 3,
    totalSteps: 9,
    element: '[data-tour="test-connection-btn"]',
    popover: {
      title: "Test your connection",
      description: "Verify that the source database is reachable before continuing.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "test-connection-completed",
    disableBack: true,
  },
  {
    id: "step-4-test-results",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 4,
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
    id: "step-5-proceed-discovery",
    stage: "Sources",
    stageNumber: 3,
    stepNumber: 5,
    totalSteps: 9,
    element: '[data-tour="proceed-discovery-btn"]',
    popover: {
      title: "Move on to Discovery",
      description: "All checks passed. Continue to schema discovery.",
      side: "top",
      align: "end",
    },
  },

  // Stage 4: Discovery (Steps 6 & 7)
  {
    id: "step-6-run-discovery",
    stage: "Discovery",
    stageNumber: 4,
    stepNumber: 6,
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
    id: "step-7-proceed-studio",
    stage: "Discovery",
    stageNumber: 4,
    stepNumber: 7,
    totalSteps: 9,
    element: '[data-tour="proceed-studio-btn"]',
    popover: {
      title: "Open Migration Studio",
      description: "Discovery complete. Proceed to Migration Studio to classify and plan your migration.",
      side: "top",
      align: "end",
    },
    condition: (context: any) => Boolean(context.hasDiscovered || context.isDemoAccount),
  },

  // Stage 7: Migration Studio (Steps mapped to studioTourStateMap)
  {
    id: "studio-parse-prompt",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 1,
    totalSteps: 7,
    element: '[data-tour="studio-parse-btn"]',
    popover: {
      title: "Parse and ground your prompt",
      description: "Start by parsing your prompt. The studio grounds it against your discovered source metadata.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "studio:prompt-parsed",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-approve-plan",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 2,
    totalSteps: 7,
    element: '[data-tour="studio-primary-action"]',
    popover: {
      title: "Approve the exact plan",
      description: "Review the grounded plan, then approve it to unlock artifact generation.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "studio:plan-approved",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-generate-artifacts",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 3,
    totalSteps: 7,
    element: '[data-tour="studio-primary-action"]',
    popover: {
      title: "Generate artifacts",
      description: "Generate the Bronze, Silver and Gold medallion artifacts from the approved plan.",
      side: "bottom",
      align: "start",
    },
    actionType: "click",
    advanceOnEvent: "studio:artifacts-generated",
    disableBack: true,
    scrollIntoView: true,
  },
  {
    id: "studio-validate-databricks",
    stage: "Migration Workflow",
    stageNumber: 7,
    stepNumber: 4,
    totalSteps: 7,
    element: '[data-tour="studio-primary-action"]',
    popover: {
      title: "Validate in Databricks",
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
    stepNumber: 5,
    totalSteps: 7,
    element: '[data-tour="studio-primary-action"]',
    popover: {
      title: "Approve current artifacts",
      description: "Approve each validated artifact version so it can be deployed.",
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
    stepNumber: 6,
    totalSteps: 7,
    element: '[data-tour="studio-primary-action"]',
    popover: {
      title: "Deploy and validate on DEV",
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
    stepNumber: 7,
    totalSteps: 7,
    element: '[data-tour="studio-primary-action"]',
    popover: {
      title: "Proceed to promotion",
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
 * State-derived map for Stage 7 (Migration Studio)
 */
export const deriveStudioStepId = (promptSpec: any, isDevAlreadyPassed: boolean): string => {
  if (isDevAlreadyPassed || promptSpec?.status === "DEV_GATE_PASSED") {
    return "studio-proceed-promotion";
  }
  if (!promptSpec || !promptSpec.status || promptSpec.status === "DRAFT") {
    return "studio-parse-prompt";
  }
  if (promptSpec.status === "PENDING_PLAN_APPROVAL") {
    return "studio-approve-plan";
  }
  if (promptSpec.status === "PLAN_APPROVED") {
    return "studio-generate-artifacts";
  }
  if (["VALIDATING", "TARGET_VALIDATION_FAILED"].includes(promptSpec.status)) {
    return "studio-validate-databricks";
  }
  if (promptSpec.status === "PENDING_ARTIFACT_REVIEW") {
    return "studio-approve-artifacts";
  }
  if (["ARTIFACTS_APPROVED", "DEV_DEPLOYMENT_FAILED", "DEPLOYING_DEV"].includes(promptSpec.status)) {
    return "studio-deploy-dev";
  }
  return "studio-parse-prompt";
};

export const getStepsForStage = (stage: string): TourStep[] => {
  return TOUR_STEPS.filter((step) => step.stage === stage);
};
