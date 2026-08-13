"use client";

import { useEffect, useId, useRef, useState } from "react";
import { createPortal } from "react-dom";

import type {
  ApplicationContextControl,
  ApplicationContextDefinition,
} from "./application-context";
import styles from "./context-control-bar.module.css";

function ContextIcon({
  control,
}: Readonly<{ control: ApplicationContextControl }>) {
  const readiness = control.id === "decision-readiness";
  const basis = control.id === "comparison-basis";
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      {readiness ? (
        <>
          <circle cx="12" cy="12" r="8" />
          <path d="m8.5 12 2.2 2.2 4.8-5" />
        </>
      ) : basis ? (
        <>
          <path d="M4 6h16M7 12h10M10 18h4" />
          <circle cx="8" cy="6" r="1.5" />
          <circle cx="15" cy="12" r="1.5" />
          <circle cx="12" cy="18" r="1.5" />
        </>
      ) : (
        <>
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="3" />
          <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
        </>
      )}
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m7 10 5 5 5-5" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="m6 6 12 12M18 6 6 18" />
    </svg>
  );
}

export function ContextControlBar({
  definition,
}: Readonly<{ definition: ApplicationContextDefinition }>) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const titleId = useId();
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const drawerRef = useRef<HTMLElement>(null);
  const triggerRefs = useRef(new Map<string, HTMLButtonElement>());
  const activeControl =
    definition.controls.find((control) => control.id === activeId) ?? null;

  useEffect(() => {
    if (!activeControl) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setActiveId(null);
        triggerRefs.current.get(activeControl!.id)?.focus();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = Array.from(
        drawerRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input, select, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      );
      const first = focusable.at(0);
      const last = focusable.at(-1);
      if (!first || !last) return;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [activeControl]);

  function openControl(control: ApplicationContextControl) {
    setActiveId(control.id);
  }

  function closeDrawer(restoreFocus = true) {
    const previousId = activeId;
    setActiveId(null);
    if (restoreFocus && previousId) {
      triggerRefs.current.get(previousId)?.focus();
    }
  }

  function selectOption(control: ApplicationContextControl, value: string) {
    if (control.queryParameter) {
      const parameters: Record<string, string | null> = {
        [control.queryParameter]: value === control.defaultValue ? null : value,
      };
      for (const key of control.resetQueryParameters ?? []) {
        parameters[key] = null;
      }
      updateLocation(parameters);
    }
    closeDrawer();
  }

  function updateLocation(parameters: Record<string, string | null>) {
    const url = new URL(window.location.href);
    for (const [key, value] of Object.entries(parameters)) {
      if (value) url.searchParams.set(key, value);
      else url.searchParams.delete(key);
    }
    window.history.replaceState(window.history.state, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }

  return (
    <>
      <div className={styles.rail} aria-label={definition.label}>
        {definition.controls.map((control) => (
          <button
            aria-expanded={activeId === control.id}
            className={`${styles.segment} ${styles[control.tone ?? "neutral"]}`}
            key={control.id}
            onClick={() => openControl(control)}
            ref={(node) => {
              if (node) triggerRefs.current.set(control.id, node);
              else triggerRefs.current.delete(control.id);
            }}
            type="button"
          >
            <span className={styles.icon}>
              <ContextIcon control={control} />
            </span>
            <span className={styles.copy}>
              <small>{control.label}</small>
              <strong>{control.value}</strong>
            </span>
            <span className={styles.chevron}>
              <ChevronIcon />
            </span>
          </button>
        ))}
      </div>

      {activeControl
        ? createPortal(
            <>
              <button
                aria-label="Dismiss report context"
                className={styles.backdrop}
                onClick={() => closeDrawer()}
                type="button"
              />
              <section
                aria-labelledby={titleId}
                aria-modal="true"
                className={styles.drawer}
                ref={drawerRef}
                role="dialog"
              >
                <div className={styles.drawerInner}>
                  <header className={styles.drawerHeader}>
                    <div>
                      <p>{activeControl.label}</p>
                      <h2 id={titleId}>{activeControl.title}</h2>
                      <span>{activeControl.description}</span>
                    </div>
                    <button
                      aria-label="Close report context"
                      className={styles.closeButton}
                      onClick={() => closeDrawer()}
                      ref={closeButtonRef}
                      type="button"
                    >
                      <CloseIcon />
                    </button>
                  </header>

                  {activeControl.options?.length ? (
                    <div className={styles.optionGrid}>
                      {activeControl.options.map((option) => (
                        <button
                          aria-pressed={
                            activeControl.selectedValue === option.value
                          }
                          className={
                            activeControl.selectedValue === option.value
                              ? styles.selected
                              : undefined
                          }
                          key={option.value}
                          onClick={() =>
                            selectOption(activeControl, option.value)
                          }
                          type="button"
                        >
                          <span
                            className={styles.choiceMark}
                            aria-hidden="true"
                          />
                          <span>
                            <strong>{option.label}</strong>
                            <small>{option.description}</small>
                          </span>
                        </button>
                      ))}
                    </div>
                  ) : null}

                  {activeControl.facts?.length ? (
                    <dl className={styles.facts}>
                      {activeControl.facts.map((fact) => (
                        <div key={fact.label}>
                          <dt>{fact.label}</dt>
                          <dd>{fact.value}</dd>
                        </div>
                      ))}
                    </dl>
                  ) : null}

                  {activeControl.messages?.length ? (
                    <div className={styles.messages}>
                      {activeControl.messages.map((message) => (
                        <p key={message}>{message}</p>
                      ))}
                    </div>
                  ) : null}

                  {activeControl.action || !activeControl.options?.length ? (
                    <footer className={styles.drawerActions}>
                      {activeControl.action ? (
                        <button
                          className={styles.secondaryAction}
                          onClick={() => {
                            closeDrawer(false);
                            if (activeControl.action) {
                              if (activeControl.action.href) {
                                const destination = new URL(
                                  activeControl.action.href,
                                  window.location.origin,
                                );
                                for (const [key, value] of Object.entries(
                                  activeControl.action.parameters,
                                )) {
                                  if (value)
                                    destination.searchParams.set(key, value);
                                }
                                window.location.assign(destination);
                              } else {
                                updateLocation(activeControl.action.parameters);
                              }
                            }
                          }}
                          type="button"
                        >
                          {activeControl.action.label}
                        </button>
                      ) : null}
                      <button onClick={() => closeDrawer()} type="button">
                        Close
                      </button>
                    </footer>
                  ) : null}
                </div>
              </section>
            </>,
            document.body,
          )
        : null}
    </>
  );
}
