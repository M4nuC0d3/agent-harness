# frontend/AGENTS.md

Angular application, built with the Angular CLI. Package manager: **npm**
(*confirm — switch to pnpm/yarn here if that's your setup*). Use the Node
version the repo pins — check `.nvmrc` / `package.json` `engines` before
`npm install`; if your Node/npm can't satisfy it, that's a blocker (see the root
anti-patterns), not a reason to downgrade packages.

## Build & run

- Dev server: `npm start` (`ng serve`)
- Unit tests: `npm test` (`ng test`)
- Lint: `npm run lint`
- Build: `npm run build` (`ng build`)
- E2E: `npm run e2e` (*Playwright recommended — confirm your runner*)

## Conventions — modern Angular best practices

Write new code to these; don't reintroduce older patterns:

- **Standalone components** only — no `NgModule`s. Bootstrap via
  `bootstrapApplication`.
- **Signals** for component and derived state (`signal`, `computed`, `effect`);
  prefer them over ad-hoc `BehaviorSubject` for local state.
- **New control flow** in templates — `@if`, `@for`, `@switch` — not
  `*ngIf` / `*ngFor`.
- **`inject()`** for dependency injection in new code, not constructor injection.
- **`ChangeDetectionStrategy.OnPush`** on every component.
- **Typed reactive forms**; avoid template-driven forms beyond trivial cases.
- Smart / presentational component split; feature-first folder structure.
- State management: *state your choice — signals-only or NgRx*. Styling: *SCSS or
  Tailwind — state it*.
- Lint/format: ESLint (`angular-eslint`) + Prettier, both clean before a PR.

## API client — generated, contract-first

The typed HTTP client is **generated** from `../api/openapi.yaml` (e.g.
`ng-openapi-gen` or openapi-generator `typescript-angular`). Do **not** hand-write
or hand-edit the client, and do **not** call endpoints the contract doesn't
define. Need a new endpoint? Change `api/openapi.yaml` first, regenerate, then
use it. Keep the generated client in its own folder and treat it as read-only.
