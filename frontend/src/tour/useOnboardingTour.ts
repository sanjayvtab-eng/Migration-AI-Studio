import { useState, useEffect, useRef, useCallback } from "react";
import { driver, Driver } from "driver.js";
import "driver.js/dist/driver.css";
import "./tour.css";
import { TOUR_STEPS, getStepsForStage, deriveEnvStepId, deriveStudioStepId, TourStep } from "./tourConfig";
import { getTourState, saveTourState, resetTourState } from "./tourStorage";

/**
 * Helper to wait for an element in the DOM using polling & MutationObserver
 */
function waitForElement(selector: string, timeoutMs: number = 4000): Promise<HTMLElement | null> {
  return new Promise((resolve) => {
    const existing = document.querySelector<HTMLElement>(selector);
    if (existing) {
      return resolve(existing);
    }

    let observer: MutationObserver | null = null;
    const timeout = setTimeout(() => {
      if (observer) observer.disconnect();
      resolve(document.querySelector<HTMLElement>(selector));
    }, timeoutMs);

    observer = new MutationObserver(() => {
      const el = document.querySelector<HTMLElement>(selector);
      if (el) {
        clearTimeout(timeout);
        if (observer) observer.disconnect();
        resolve(el);
      }
    });

    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
    });
  });
}

/**
 * Hook to manage stage-aware onboarding tour lifecycle with driver.js
 */
export function useOnboardingTour(currentStage: string, stageContext: Record<string, any> = {}) {
  const [welcomeModalOpen, setWelcomeModalOpen] = useState(false);
  const [tourActive, setTourActive] = useState(false);
  const driverInstanceRef = useRef<Driver | null>(null);
  const currentStepRef = useRef<TourStep | null>(null);
  const stageRef = useRef(currentStage);
  const contextRef = useRef(stageContext);
  const isWaitingForActionRef = useRef(false);

  stageRef.current = currentStage;
  contextRef.current = stageContext;

  // Cleanup active driver on unmount
  useEffect(() => {
    return () => {
      if (driverInstanceRef.current) {
        driverInstanceRef.current.destroy();
      }
    };
  }, []);

  const dismissSpotlight = useCallback(() => {
    if (driverInstanceRef.current) {
      driverInstanceRef.current.destroy();
      driverInstanceRef.current = null;
    }
  }, []);

  // Format the popover HTML with steps, dots, title, description, buttons
  const buildPopoverHtml = useCallback((stepConfig: TourStep) => {
    const { title, description } = stepConfig.popover;
    const { stepNumber, totalSteps } = stepConfig;

    const dotsHtml = Array.from({ length: totalSteps })
      .map((_, i) => {
        const dotNum = i + 1;
        let className = "mf-tour-dot";
        if (dotNum === stepNumber) className += " active";
        else if (dotNum < stepNumber) className += " passed";
        return `<span class="${className}"></span>`;
      })
      .join("");

    const isFirstStep = stepNumber === 1 || Boolean(stepConfig.disableBack);
    const isLastStep = stepNumber === totalSteps;
    const isActionStep = stepConfig.actionType === "click";

    return `
      <div class="mf-tour-badge-row">
        <span class="mf-tour-badge">Step ${stepNumber} of ${totalSteps}</span>
        <div class="mf-tour-dots">${dotsHtml}</div>
      </div>
      <h4 class="driver-popover-title">${title}</h4>
      <p class="driver-popover-description">${description}</p>
      <div class="driver-popover-footer">
        <button type="button" class="mf-tour-skip-link" data-tour-action="skip">Skip tour</button>
        <div class="mf-tour-actions">
          ${
            !isFirstStep && !isActionStep
              ? `<button type="button" class="mf-tour-btn-back" data-tour-action="back">Back</button>`
              : ""
          }
          ${
            !isActionStep
              ? `<button type="button" class="mf-tour-btn-next" data-tour-action="next">
                  ${isLastStep ? "Finish" : "Next"}
                </button>`
              : `<span class="mf-tour-action-hint">${stepConfig.actionHint || "Click the highlighted button to proceed"}</span>`
          }
        </div>
      </div>
    `;
  }, []);

  /**
   * Highlight a specific step by config
   */
  const highlightStep = useCallback(
    async (stepConfig: TourStep) => {
      if (!stepConfig) return;

      const state = getTourState();
      if (state.skipped || state.completed) return;

      currentStepRef.current = stepConfig;

      // Check step condition if provided
      if (stepConfig.condition && !stepConfig.condition(contextRef.current)) {
        console.log(`[Tour] Condition not met for step ${stepConfig.id}; waiting for condition/action.`);
        return;
      }

      // Wait for element to exist in DOM
      const targetEl = await waitForElement(stepConfig.element, 3500);
      if (!targetEl) {
        console.warn(`[Tour] Element ${stepConfig.element} not found, skipping gracefully.`);
        return;
      }

      // Smooth scroll into view if required or off-screen
      if (stepConfig.scrollIntoView || stepConfig.id === "step-4-test-results") {
        targetEl.scrollIntoView({ behavior: "smooth", block: "center" });
        await new Promise((res) => setTimeout(res, 350));
      }

      // Destroy any prior active driver instance
      dismissSpotlight();

      const driverObj = driver({
        animate: true,
        smoothScroll: true,
        allowClose: true,
        overlayColor: "rgba(15, 23, 42, 0.65)",
        stagePadding: 8,
        stageRadius: 8,
        popoverClass: "mf-tour-popover",
        onDestroyStarted: () => {
          driverObj.destroy();
        },
      });

      driverInstanceRef.current = driverObj;

      driverObj.highlight({
        element: targetEl,
        popover: {
          side: stepConfig.popover.side || "bottom",
          align: stepConfig.popover.align || "start",
          description: buildPopoverHtml(stepConfig),
        },
      });

      // Add gentle pulse class if action step
      if (stepConfig.actionType === "click") {
        targetEl.classList.add("tour-pulse");
        isWaitingForActionRef.current = true;
      } else {
        isWaitingForActionRef.current = false;
      }

      // When the user clicks the highlighted button, dismiss the popover immediately
      // Do NOT advance yet! Advance strictly when the process completes and emits an event.
      const handleTargetClick = () => {
        dismissSpotlight();
        targetEl.classList.remove("tour-pulse");
        targetEl.removeEventListener("click", handleTargetClick);
      };
      if (stepConfig.id !== "env-choose-prereq") {
        targetEl.addEventListener("click", handleTargetClick, { once: true });
      }

      // Wire up custom buttons in popover
      setTimeout(() => {
        const popoverEl = document.querySelector<HTMLElement>(".mf-tour-popover");
        if (!popoverEl) return;

        const skipBtn = popoverEl.querySelector<HTMLElement>('[data-tour-action="skip"]');
        const backBtn = popoverEl.querySelector<HTMLElement>('[data-tour-action="back"]');
        const nextBtn = popoverEl.querySelector<HTMLElement>('[data-tour-action="next"]');

        if (skipBtn) {
          skipBtn.onclick = (e) => {
            e.stopPropagation();
            skipTour();
          };
        }

        if (backBtn) {
          backBtn.onclick = (e) => {
            e.stopPropagation();
            goToPreviousStep(stepConfig);
          };
        }

        if (nextBtn) {
          nextBtn.onclick = (e) => {
            e.stopPropagation();
            goToNextStep(stepConfig);
          };
        }
      }, 50);
    },
    [buildPopoverHtml, dismissSpotlight]
  );

  const goToNextStep = useCallback(
    (currentStep: TourStep) => {
      // If it is an action step, user MUST complete the action to proceed
      if (currentStep.actionType === "click") {
        return;
      }

      dismissSpotlight();
      const stageSteps = getStepsForStage(currentStep.stage);
      const curIndex = stageSteps.findIndex((s) => s.id === currentStep.id);
      if (curIndex !== -1 && curIndex + 1 < stageSteps.length) {
        const nextStep = stageSteps[curIndex + 1];
        saveTourState({ currentStepIndex: curIndex + 1, currentStage: nextStep.stage });
        highlightStep(nextStep);
      } else {
        // Look in global sequence
        const globalIdx = TOUR_STEPS.findIndex((s) => s.id === currentStep.id) + 1;
        if (globalIdx < TOUR_STEPS.length) {
          const nextGlobalStep = TOUR_STEPS[globalIdx];
          saveTourState({ currentStepIndex: globalIdx, currentStage: nextGlobalStep.stage });
          if (nextGlobalStep.stage === stageRef.current) {
            highlightStep(nextGlobalStep);
          }
        } else {
          saveTourState({ completed: true, hasSeenTour: true });
          setTourActive(false);
        }
      }
    },
    [highlightStep, dismissSpotlight]
  );

  const goToPreviousStep = useCallback(
    (currentStep: TourStep) => {
      if (currentStep.disableBack || currentStep.actionType === "click") return;
      dismissSpotlight();
      const stageSteps = getStepsForStage(currentStep.stage);
      const curIndex = stageSteps.findIndex((s) => s.id === currentStep.id);
      if (curIndex > 0) {
        const prevStep = stageSteps[curIndex - 1];
        highlightStep(prevStep);
      }
    },
    [highlightStep, dismissSpotlight]
  );

  const skipTour = useCallback(() => {
    dismissSpotlight();
    saveTourState({ skipped: true, hasSeenTour: true });
    setTourActive(false);
    setWelcomeModalOpen(false);
  }, [dismissSpotlight]);

  const startTour = useCallback(
    (stageToStart = currentStage) => {
      setWelcomeModalOpen(false);
      setTourActive(true);
      saveTourState({ hasSeenTour: true, skipped: false, completed: false });

      if (stageToStart === "Environment Setup") {
        if (contextRef.current.isDemoAccount) return;
        const derivedId = deriveEnvStepId(
          contextRef.current.environmentConfig,
          contextRef.current.environmentPlan,
          contextRef.current.showDatabricksPrereqModal
        );
        const step = TOUR_STEPS.find((s) => s.id === derivedId);
        if (step) {
          highlightStep(step);
          return;
        }
      }

      if (stageToStart === "Migration Workflow") {
        const derivedId = deriveStudioStepId(
          contextRef.current.promptSpec,
          contextRef.current.isDevAlreadyPassed
        );
        const step = TOUR_STEPS.find((s) => s.id === derivedId);
        if (step) {
          highlightStep(step);
          return;
        }
      }

      // Find first step for the stage
      const stageSteps = getStepsForStage(stageToStart, contextRef.current);
      if (stageSteps.length > 0) {
        highlightStep(stageSteps[0]);
      } else if (TOUR_STEPS.length > 0) {
        const eligible = TOUR_STEPS.filter((s) => !s.condition || s.condition(contextRef.current));
        highlightStep(eligible[0] || TOUR_STEPS[0]);
      }
    },
    [currentStage, highlightStep]
  );

  const restartTour = useCallback(() => {
    resetTourState();
    startTour(stageRef.current);
  }, [startTour]);

  // Action-driven event notification: ONLY advance when the action has completed!
  const notify = useCallback(
    (event: string, payload: any = {}) => {
      console.log(`[Tour] Event received: ${event}`, payload);

      // 1. Projects stage: Project created or selected successfully
      if (event === "project-created" || event === "project-selected") {
        setTimeout(() => {
          const step2 = TOUR_STEPS.find((s) => s.id === "step-2-proceed-sources");
          if (step2) {
            saveTourState({ currentStepIndex: 1, currentStage: "Projects" });
            highlightStep(step2);
          }
        }, 400);
        return;
      }

      // 1b. Environment Setup stage (Stage 2) action progression
      if (event === "env:prereq-selected" || event === "env:prereq-dismissed") {
        dismissSpotlight();
        setTimeout(() => {
          const step = TOUR_STEPS.find((s) => s.id === "env-save-config");
          if (step) highlightStep(step);
        }, 300);
        return;
      }

      if (event === "env:prereq-opened") {
        setTimeout(() => {
          const step = TOUR_STEPS.find((s) => s.id === "env-choose-prereq");
          if (step) highlightStep(step);
        }, 300);
        return;
      }

      if (event === "env:config-saved") {
        setTimeout(() => {
          const step = TOUR_STEPS.find((s) => s.id === "env-test-connection");
          if (step) highlightStep(step);
        }, 400);
        return;
      }

      if (event === "env:connection-tested") {
        setTimeout(() => {
          const step = TOUR_STEPS.find((s) => s.id === "env-create-plan");
          if (step) highlightStep(step);
        }, 400);
        return;
      }

      if (event === "env:plan-created") {
        setTimeout(() => {
          const step = TOUR_STEPS.find((s) => s.id === "env-run-preflight");
          if (step) highlightStep(step);
        }, 500);
        return;
      }

      if (event === "env:preflight-completed") {
        setTimeout(() => {
          const step = TOUR_STEPS.find((s) => s.id === "env-approve-plan");
          if (step) highlightStep(step);
        }, 400);
        return;
      }

      if (event === "env:plan-approved") {
        setTimeout(() => {
          const step = TOUR_STEPS.find((s) => s.id === "env-provision-dev");
          if (step) highlightStep(step);
        }, 400);
        return;
      }

      if (event === "env:provision-completed") {
        setTimeout(() => {
          const step = TOUR_STEPS.find((s) => s.id === "env-proceed-sources");
          if (step) highlightStep(step);
        }, 400);
        return;
      }

      // 2a. Sources stage: Connector Agent modal closed -> guide to test connection
      if (event === "connector-agent-closed") {
        setTimeout(() => {
          const testStep = TOUR_STEPS.find((s) => s.id === "step-4-test-connection") || TOUR_STEPS.find((s) => s.id === "step-3-test-connection");
          if (testStep) {
            highlightStep(testStep);
          }
        }, 400);
        return;
      }

      // 2b. Sources stage: Connection test completed
      if (event === "test-connection-completed") {
        setTimeout(() => {
          const stepResults = TOUR_STEPS.find((s) => s.id === "step-5-test-results") || TOUR_STEPS.find((s) => s.id === "step-4-test-results");
          if (stepResults) {
            saveTourState({ currentStepIndex: 4, currentStage: "Sources" });
            highlightStep(stepResults);
          }
        }, 500);
        return;
      }

      // 3. Discovery stage: Discovery completed
      if (event === "discovery-completed") {
        setTimeout(() => {
          const stepStudio = TOUR_STEPS.find((s) => s.id === "step-8-proceed-studio") || TOUR_STEPS.find((s) => s.id === "step-7-proceed-studio");
          if (stepStudio) {
            saveTourState({ currentStepIndex: 7, currentStage: "Discovery" });
            highlightStep(stepStudio);
          }
        }, 500);
        return;
      }

      // 4. Studio stage: Only advance when prompt-parsed, plan-approved, etc.
      if (event.startsWith("studio:")) {
        setTimeout(() => {
          const derivedId = deriveStudioStepId(
            payload?.promptSpec || contextRef.current.promptSpec,
            Boolean(payload?.isDevAlreadyPassed || contextRef.current.isDevAlreadyPassed)
          );
          const nextStep = TOUR_STEPS.find((s) => s.id === derivedId);
          if (nextStep) {
            highlightStep(nextStep);
          }
        }, 500);
        return;
      }

      // 5. Deployments stage: Modal opened & promotion confirmed
      if (event === "deploy:modal-opened") {
        setTimeout(() => {
          const confirmStep = TOUR_STEPS.find((s) => s.id === "deploy-confirm-promotion");
          if (confirmStep) highlightStep(confirmStep);
        }, 400);
        return;
      }

      if (event === "deploy:promotion-confirmed") {
        dismissSpotlight();
        saveTourState({ completed: true, hasSeenTour: true });
        setTourActive(false);
        return;
      }

      if (event === "studio:reset-demo") {
        setTimeout(() => {
          const parseStep = TOUR_STEPS.find((s) => s.id === "studio-parse-prompt");
          if (parseStep) highlightStep(parseStep);
        }, 400);
      }
    },
    [highlightStep, dismissSpotlight]
  );

  // Auto-start for new users after delay on initial render of Projects stage
  useEffect(() => {
    const state = getTourState();
    if (!state.hasSeenTour && !state.skipped && !state.completed) {
      const timer = setTimeout(() => {
        setWelcomeModalOpen(true);
      }, 600);
      return () => clearTimeout(timer);
    }
  }, []);

  // Listen for local connector dialog close event
  useEffect(() => {
    const handleConnectorClosed = () => {
      notify("connector-agent-closed");
    };
    window.addEventListener("connector-agent-closed", handleConnectorClosed);
    return () => {
      window.removeEventListener("connector-agent-closed", handleConnectorClosed);
    };
  }, [notify]);

  // When stage changes, resume tour if active and not completed
  useEffect(() => {
    const state = getTourState();
    if (state.hasSeenTour && !state.completed && !state.skipped) {
      if (currentStage === "Projects") {
        // Only show step 2 if projects already exist and selected, otherwise step 1
        const timer = setTimeout(() => {
          if (state.currentStepIndex >= 1 && stageContext.hasProject) {
            const step2 = TOUR_STEPS.find((s) => s.id === "step-2-proceed-sources");
            if (step2) highlightStep(step2);
          } else if (stageContext.isDemoAccount) {
            const demoStep = TOUR_STEPS.find((s) => s.id === "step-1-demo-project");
            if (demoStep) highlightStep(demoStep);
          } else {
            const step1 = TOUR_STEPS.find((s) => s.id === "step-1-new-project");
            if (step1) highlightStep(step1);
          }
        }, 500);
        return () => clearTimeout(timer);
      } else if (currentStage === "Environment Setup") {
        if (stageContext.isDemoAccount) return;
        const timer = setTimeout(() => {
          const derivedId = deriveEnvStepId(
            stageContext.environmentConfig,
            stageContext.environmentPlan,
            stageContext.showDatabricksPrereqModal
          );
          const step = TOUR_STEPS.find((s) => s.id === derivedId);
          if (step) highlightStep(step);
        }, 500);
        return () => clearTimeout(timer);
      } else if (currentStage === "Sources") {
        const timer = setTimeout(() => {
          const step =
            TOUR_STEPS.find((s) => s.id === "step-3-connector-agent") ||
            TOUR_STEPS.find((s) => s.id === "step-4-test-connection") ||
            TOUR_STEPS.find((s) => s.id === "step-3-test-connection");
          if (step) highlightStep(step);
        }, 500);
        return () => clearTimeout(timer);
      } else if (currentStage === "Discovery") {
        const timer = setTimeout(() => {
          const step =
            TOUR_STEPS.find((s) => s.id === "step-7-run-discovery") ||
            TOUR_STEPS.find((s) => s.id === "step-6-run-discovery");
          if (step) highlightStep(step);
        }, 500);
        return () => clearTimeout(timer);
      } else if (currentStage === "Migration Workflow") {
        const timer = setTimeout(() => {
          const derivedId = deriveStudioStepId(
            stageContext.promptSpec,
            stageContext.isDevAlreadyPassed
          );
          const step = TOUR_STEPS.find((s) => s.id === derivedId);
          if (step) highlightStep(step);
        }, 500);
        return () => clearTimeout(timer);
      } else if (currentStage === "Deployments") {
        const timer = setTimeout(() => {
          const step = TOUR_STEPS.find((s) => s.id === "deploy-authorize-promotion");
          if (step) highlightStep(step);
        }, 500);
        return () => clearTimeout(timer);
      }
    }
  }, [currentStage, highlightStep, stageContext.promptSpec, stageContext.isDevAlreadyPassed, stageContext.hasProject, stageContext.environmentConfig, stageContext.environmentPlan, stageContext.isDemoAccount]);

  return {
    tourActive,
    welcomeModalOpen,
    startTour,
    skipTour,
    restartTour,
    notify,
    highlightStep,
    dismissSpotlight,
  };
}
