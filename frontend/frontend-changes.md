# Frontend Code Quality Changes

## Overview

Added code quality tooling to the frontend to enforce consistent formatting and catch common JS issues. All changes are frontend-only.

## New Files

### `package.json`
Introduces npm as a dev toolchain for the vanilla frontend. Defines the project metadata and declares two dev dependencies:
- **prettier** `^3.4.2` — opinionated code formatter
- **eslint** `^9.20.0` — JavaScript linter

Defines the following npm scripts:

| Script | Command | Purpose |
|---|---|---|
| `format` | `prettier --write "**/*.{js,css,html}"` | Auto-format all JS, CSS, and HTML files |
| `format:check` | `prettier --check "**/*.{js,css,html}"` | Check formatting without modifying files (CI-safe) |
| `lint` | `eslint "**/*.js"` | Run ESLint on all JS files |
| `lint:fix` | `eslint --fix "**/*.js"` | Auto-fix ESLint violations where possible |
| `quality` | `format:check && lint` | Full read-only quality check (for CI) |
| `quality:fix` | `format && lint:fix` | Apply all auto-fixes in one command |

### `.prettierrc`
Prettier configuration with the following rules:
- `printWidth: 100` — wrap lines at 100 characters
- `tabWidth: 2` — 2-space indentation
- `useTabs: false` — spaces, not tabs
- `semi: true` — always include semicolons
- `singleQuote: true` — use single quotes in JS
- `trailingComma: "es5"` — trailing commas where valid in ES5 (objects, arrays)
- `bracketSpacing: true` — spaces inside object literals `{ key: val }`
- `arrowParens: "always"` — always wrap arrow function args in parens
- `endOfLine: "lf"` — Unix line endings

### `eslint.config.js`
Flat ESLint config (ESLint v9 format) targeting all `*.js` files. Sets browser globals (`document`, `window`, `console`, `fetch`, `Date`) and `marked` (the CDN-loaded markdown library). Rules:
- `no-unused-vars: warn` — surface unused variables
- `no-console: off` — allow console.log (used for debug logging in `loadCourseStats`)
- `eqeqeq: error` — require `===` instead of `==`
- `no-var: error` — disallow `var`, require `let`/`const`
- `prefer-const: warn` — prefer `const` for variables that are never reassigned

### `.prettierignore`
Excludes `node_modules/` from Prettier formatting.

## Modified Files

### `script.js`
Reformatted to match `.prettierrc` rules:
- Indentation changed from 4 spaces to 2 spaces throughout
- Trailing commas added to multi-line object/array literals (e.g. fetch body, forEach callbacks)
- Arrow function parameters wrapped in parens: `button => {` → `(button) => {`
- Removed extra blank lines between function declarations
- Template literal HTML inside `createLoadingMessage` and `addMessage` re-indented to 2 spaces

No logic was changed.

### `index.html`
Reformatted to match Prettier's HTML formatting:
- Doctype lowercased: `<!DOCTYPE html>` → `<!doctype html>`
- Self-closing void elements use ` />`  (e.g. `<meta ... />`, `<link ... />`, `<input ... />`)
- Long `<button>` elements with `data-question` attributes split across lines for readability
- SVG inside `#sendButton` attributes each placed on their own line
- Consistent 2-space indentation throughout

No markup structure or attributes were changed.

### `style.css`
Reformatted to match Prettier's CSS formatting:
- Indentation changed from 4 spaces to 2 spaces throughout
- Multi-selector rules split to one selector per line where previously on one line (e.g. `*,` / `*::before,` / `*::after`)
- `@keyframes bounce` selector list `0%, 80%, 100%` each on its own line
- Single-property rules for `.message-content h1/h2/h3` expanded to full rule blocks
- `.no-courses, .loading, .error` selector list split to one per line

No style values were changed.

## Usage

```bash
# Install dev dependencies (one-time)
cd frontend
npm install

# Check formatting and linting (non-destructive, good for CI)
npm run quality

# Auto-fix all formatting and lint issues
npm run quality:fix

# Format only
npm run format

# Lint only
npm run lint
```
