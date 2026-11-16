export interface TourState {
  completed: boolean;
  skipped: boolean;
  hasSeenTour: boolean;
  currentStage: string | null;
  currentStepIndex: number;
}

const STORAGE_KEY = "mf_onboarding_tour_state";

export const getTourState = (): TourState => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {
        completed: false,
        skipped: false,
        hasSeenTour: false,
        currentStage: null,
        currentStepIndex: 0,
      };
    }
    return JSON.parse(raw);
  } catch (e) {
    console.error("Failed to read tour state from storage:", e);
    return {
      completed: false,
      skipped: false,
      hasSeenTour: false,
      currentStage: null,
      currentStepIndex: 0,
    };
  }
};

export const saveTourState = (updates: Partial<TourState>): TourState => {
  try {
    const current = getTourState();
    const updated = { ...current, ...updates };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
    return updated;
  } catch (e) {
    console.error("Failed to save tour state to storage:", e);
    return getTourState();
  }
};

export const resetTourState = (): TourState => {
  try {
    const reset: TourState = {
      completed: false,
      skipped: false,
      hasSeenTour: false,
      currentStage: null,
      currentStepIndex: 0,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(reset));
    return reset;
  } catch (e) {
    console.error("Failed to reset tour state:", e);
    return getTourState();
  }
};
