import React, { createContext, useContext, ReactNode } from "react";
import { useOnboardingTour } from "./useOnboardingTour";
import { WelcomeModal } from "./WelcomeModal";

interface TourContextValue {
  notify: (event: string, payload?: any) => void;
  restartTour: () => void;
  startTour: (stage?: string) => void;
  skipTour: () => void;
  dismissSpotlight: () => void;
}

const TourContext = createContext<TourContextValue>({
  notify: () => {},
  restartTour: () => {},
  startTour: () => {},
  skipTour: () => {},
  dismissSpotlight: () => {},
});

interface TourProviderProps {
  children: ReactNode;
  currentStage: string;
  stageContext?: Record<string, any>;
}

export function TourProvider({ children, currentStage, stageContext = {} }: TourProviderProps) {
  const tour = useOnboardingTour(currentStage, stageContext);

  return (
    <TourContext.Provider
      value={{
        notify: tour.notify,
        restartTour: tour.restartTour,
        startTour: tour.startTour,
        skipTour: tour.skipTour,
        dismissSpotlight: tour.dismissSpotlight,
      }}
    >
      {children}
      <WelcomeModal
        isOpen={tour.welcomeModalOpen}
        onStart={() => tour.startTour()}
        onSkip={() => tour.skipTour()}
      />
    </TourContext.Provider>
  );
}

export function useTour(): TourContextValue {
  return useContext(TourContext);
}
