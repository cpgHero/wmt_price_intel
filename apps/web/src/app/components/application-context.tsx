"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ContextControlTone = "neutral" | "ready" | "attention";

export interface ApplicationContextOption {
  description: string;
  label: string;
  value: string;
}

export interface ApplicationContextFact {
  label: string;
  value: string;
}

export interface ApplicationContextControl {
  action?: {
    href?: string;
    label: string;
    parameters: Record<string, string | null>;
  };
  defaultValue?: string;
  description: string;
  facts?: ApplicationContextFact[];
  id: string;
  label: string;
  messages?: string[];
  options?: ApplicationContextOption[];
  queryParameter?: string;
  resetQueryParameters?: string[];
  selectedValue?: string;
  title: string;
  tone?: ContextControlTone;
  value: string;
}

export interface ApplicationContextDefinition {
  controls: ApplicationContextControl[];
  label: string;
}

interface ApplicationContextValue {
  actions: ReactNode | null;
  definition: ApplicationContextDefinition | null;
  setActions: (actions: ReactNode | null) => void;
  setDefinition: (definition: ApplicationContextDefinition | null) => void;
}

const ApplicationContext = createContext<ApplicationContextValue | null>(null);

export function ApplicationContextProvider({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const [definition, setDefinition] =
    useState<ApplicationContextDefinition | null>(null);
  const [actions, setActions] = useState<ReactNode | null>(null);
  const value = useMemo(
    () => ({ actions, definition, setActions, setDefinition }),
    [actions, definition],
  );
  return (
    <ApplicationContext.Provider value={value}>
      {children}
    </ApplicationContext.Provider>
  );
}

export function useApplicationContext() {
  const value = useContext(ApplicationContext);
  if (!value) {
    throw new Error("Application context must be used within its provider");
  }
  return value;
}

export function useApplicationContextDefinition(
  definition: ApplicationContextDefinition,
) {
  const { setDefinition } = useApplicationContext();
  useEffect(() => {
    setDefinition(definition);
    return () => setDefinition(null);
  }, [definition, setDefinition]);
}

export function useApplicationContextActions(actions: ReactNode | null) {
  const { setActions } = useApplicationContext();
  useEffect(() => {
    setActions(actions);
    return () => setActions(null);
  }, [actions, setActions]);
}
