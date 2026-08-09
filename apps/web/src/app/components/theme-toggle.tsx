"use client";

function setTheme(theme: "light" | "dark") {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  window.localStorage.setItem("rci-theme", theme);
}

export function ThemeToggle() {
  function toggleTheme() {
    setTheme(
      document.documentElement.dataset.theme === "dark" ? "light" : "dark",
    );
  }

  return (
    <button
      aria-label="Toggle light and dark theme"
      className="theme-toggle"
      onClick={toggleTheme}
      title="Toggle light and dark theme"
      type="button"
    >
      <svg
        aria-hidden="true"
        className="theme-icon theme-icon-sun"
        viewBox="0 0 24 24"
      >
        <circle cx="12" cy="12" r="3.5" />
        <path d="M12 2v2M12 20v2M4.93 4.93l1.42 1.42M17.65 17.65l1.42 1.42M2 12h2M20 12h2M4.93 19.07l1.42-1.42M17.65 6.35l1.42-1.42" />
      </svg>
      <svg
        aria-hidden="true"
        className="theme-icon theme-icon-moon"
        viewBox="0 0 24 24"
      >
        <path d="M20.3 15.2A8.3 8.3 0 0 1 8.8 3.7 8.3 8.3 0 1 0 20.3 15.2Z" />
      </svg>
    </button>
  );
}
