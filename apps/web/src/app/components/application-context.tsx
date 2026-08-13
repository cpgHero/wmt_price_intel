"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

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
  definition: ApplicationContextDefinition | null;
  setDefinition: (definition: ApplicationContextDefinition | null) => void;
}

const ApplicationContext = createContext<ApplicationContextValue | null>(null);

export function ApplicationContextProvider({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  const [definition, setDefinition] =
    useState<ApplicationContextDefinition | null>(null);
  const value = useMemo(() => ({ definition, setDefinition }), [definition]);
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
