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
- **New `[data-theme="light"]` selector** with a full set of overridden variables:
  - `--background: #f8fafc`, `--surface: #ffffff`, `--surface-hover: #e2e8f0`
  - `--text-primary: #0f172a`, `--text-secondary: #64748b`
  - `--border-color: #cbd5e1`
  - `--welcome-bg: #eff6ff`, `--welcome-border: #93c5fd`
  - `--code-bg: rgba(0,0,0,0.06)`
  - Adjusted toggle surface colors for light backgrounds.
- **`body` transition** — `background-color 0.3s ease, color 0.3s ease` for a smooth crossfade.
- **`#themeToggle` styles** — fixed position, top-right corner, circular pill shape, hover/focus/active states, and `transition` on all theme-sensitive properties.
- **Icon visibility rules** — `.icon-moon` shown by default (dark mode); `.icon-sun` shown when `[data-theme="light"]` is active, and vice-versa.

#### `frontend/script.js`
- Added `themeToggle` to the DOM element declarations.
- **`initTheme()`** — reads `localStorage.getItem('theme')` (defaults to `'dark'`) and sets `data-theme` on `<html>` at startup.
- **`toggleTheme()`** — flips `data-theme` between `'dark'` and `'light'`, persists to `localStorage`.
- **`updateToggleLabel(theme)`** — updates `aria-label` and `title` on the button to reflect the current action ("Switch to light theme" / "Switch to dark theme").
- `setupEventListeners()` now registers a `click` handler on `themeToggle` → `toggleTheme`.
- `initTheme()` called inside `DOMContentLoaded` before other setup.

---

### Design Decisions
- `data-theme` is placed on `<html>` (`document.documentElement`) so CSS specificity is consistent regardless of nesting.
- All color changes go through CSS custom properties — no JavaScript style manipulation beyond toggling the attribute.
- The toggle button is `position: fixed` so it stays visible regardless of scroll state.
- Theme persists via `localStorage` — the correct theme is applied before paint (inside `DOMContentLoaded`) to avoid a flash of the wrong theme.
