# frontend/AGENTS.md

Angular application, built with the Angular CLI. Package manager: **npm**. Use
the Node version the repo pins — check `.nvmrc` / `package.json` `engines` before
`npm install`; if your Node/npm can't satisfy it, that's a blocker (see the root
anti-patterns), not a reason to downgrade packages.

## Build & run

- Dev server: `npm start` (`ng serve`)
- Unit tests: `npm test` (`ng test`, runs **Vitest**); add `--coverage` for a `coverage/` report
- Lint: `npm run lint`
- Build: `npm run build` (`ng build`)
- E2E: `npm run e2e` (**Playwright**)

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
- State management: **NgRx** for shared/application state — prefer its
  signal-based APIs (`SignalStore`, `selectSignal`) so it composes with the
  signals above instead of reintroducing `BehaviorSubject` stores. Keep
  local/derived UI state in component signals; reach for NgRx when state is
  shared across features or needs effects/DevTools.
- Styling: plain **CSS**, component-scoped `.css` files.
- Testing: **Vitest** via the first-party `@angular/build:unit-test` builder
  (Vitest is the Angular 21 default — don't reintroduce Karma/Jasmine). Specs use
  Vitest's `describe`/`it`/`expect` and `vi` for mocks, with `TestBed` for
  components. Tests run in Node + jsdom (logic, not real-browser rendering) — put
  layout/rendering checks in the Playwright E2E suite. New projects are zoneless:
  prefer native `async`/`await` and Vitest fake timers; if you need Zone's
  `fakeAsync`, add `zone.js/plugins/vitest-patch` to the test polyfills.
- Lint/format: ESLint (`angular-eslint`) + Prettier, both clean before a PR.

## API client — generated, contract-first

The typed HTTP client is **generated** from `../api/openapi.yaml` (e.g.
`ng-openapi-gen` or openapi-generator `typescript-angular`). Do **not** hand-write
or hand-edit the client, and do **not** call endpoints the contract doesn't
define. Need a new endpoint? Change `api/openapi.yaml` first, regenerate, then
use it. Keep the generated client in its own folder and treat it as read-only.
