# Frontend Changes

## Dark / Light Theme Toggle

### Summary
Added a theme toggle button that lets users switch between the existing dark theme and a new light theme. The selected theme persists across page reloads via `localStorage`.

---

### Files Modified

#### `frontend/index.html`
- Added a `<button id="themeToggle">` element immediately inside `<body>`, before `.container`.
- The button contains two inline SVG icons:
  - `.icon-moon` — displayed in dark mode; clicking it switches to light.
  - `.icon-sun` — displayed in light mode; clicking it switches to dark.
- The button has `aria-label` and `title` attributes for accessibility, updated dynamically by JavaScript.

#### `frontend/style.css`
- **New CSS custom properties on `:root` (dark theme defaults):**
  - `--theme-toggle-bg`, `--theme-toggle-color`, `--theme-toggle-hover` — button surface colors.
  - `--code-bg` — replaces hardcoded `rgba(0,0,0,0.2)` for `code`/`pre` backgrounds so they adapt to theme.
- **New `[data-theme="light"]` selector** with a full set of overridden variables.
- **`body` transition** — `background-color 0.3s ease, color 0.3s ease` for a smooth crossfade.
- **`#themeToggle` styles** — fixed position, top-right corner, circular pill shape, hover/focus/active states.
- **Icon visibility rules** — `.icon-moon` shown by default (dark mode); `.icon-sun` shown when `[data-theme="light"]` is active.

#### `frontend/script.js`
- Added `themeToggle` to the DOM element declarations.
- **`initTheme()`** — reads `localStorage.getItem('theme')` (defaults to `'dark'`) and sets `data-theme` on `<html>` at startup.
- **`toggleTheme()`** — flips `data-theme` between `'dark'` and `'light'`, persists to `localStorage`.
- **`updateToggleLabel(theme)`** — updates `aria-label` and `title` on the button to reflect the current action.
- `setupEventListeners()` now registers a `click` handler on `themeToggle` → `toggleTheme`.
- `initTheme()` called inside `DOMContentLoaded` before other setup.

---

## Testing Framework

### Summary

Enhanced the testing framework with API endpoint tests, pytest configuration, and shared test fixtures.

### Files Modified

- `backend/tests/` — Python test files
- `pyproject.toml` — pytest configuration via `[tool.pytest.ini_options]`
- `backend/tests/conftest.py` — shared Python fixtures for mocking RAGSystem, VectorStore, etc.
- `backend/tests/test_api.py` — FastAPI endpoint tests using `httpx.AsyncClient` / `TestClient`
