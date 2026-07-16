# hr-dashboard-backend

This project uses Quarkus, the Supersonic Subatomic Java Framework.

If you want to learn more about Quarkus, please visit its website: <https://quarkus.io/>.

## Running the application in dev mode

You can run your application in dev mode that enables live coding using:

```shell script
./mvnw quarkus:dev
```

> **_NOTE:_**  Quarkus now ships with a Dev UI, which is available in dev mode only at <http://localhost:8080/q/dev/>.

## Packaging and running the application

The application can be packaged using:

```shell script
./mvnw package
```

It produces the `quarkus-run.jar` file in the `target/quarkus-app/` directory.
Be aware that it’s not an _über-jar_ as the dependencies are copied into the `target/quarkus-app/lib/` directory.

The application is now runnable using `java -jar target/quarkus-app/quarkus-run.jar`.

If you want to build an _über-jar_, execute the following command:

```shell script
./mvnw package -Dquarkus.package.jar.type=uber-jar
```

The application, packaged as an _über-jar_, is now runnable using `java -jar target/*-runner.jar`.

## Creating a native executable

You can create a native executable using:

```shell script
./mvnw package -Dnative
```

Or, if you don't have GraalVM installed, you can run the native executable build in a container using:

```shell script
./mvnw package -Dnative -Dquarkus.native.container-build=true
```

You can then execute your native executable with: `./target/hr-dashboard-backend-1.0-SNAPSHOT-runner`

If you want to learn more about building native executables, please consult <https://quarkus.io/guides/maven-tooling>.

## Related Guides

- REST resources for Hibernate ORM with Panache ([guide](https://quarkus.io/guides/rest-data-panache)): Generate Jakarta
  REST resources for your Hibernate Panache entities and repositories
- REST ([guide](https://quarkus.io/guides/rest)): Build RESTful web services and APIs using Jakarta REST (formerly
  JAX-RS)
- REST Jackson ([guide](https://quarkus.io/guides/rest#json-serialisation)): Jackson serialization support for Quarkus
  REST. This extension is not compatible with the quarkus-resteasy extension, or any of the extensions that depend on it
- JDBC Driver - MariaDB ([guide](https://quarkus.io/guides/datasource)): Connect to the MariaDB database via JDBC

## Provided Code

### REST Data with Panache

Generating Jakarta REST resources with Panache

[Related guide section...](https://quarkus.io/guides/rest-data-panache)

### REST

Easily start your REST Web Services

[Related guide section...](https://quarkus.io/guides/getting-started-reactive#reactive-jax-rs-resources)

## Microsoft Entra ID (Azure AD) SSO setup

SSO login (Angular SPA via MSAL.js + Quarkus backend validating Bearer tokens
via `quarkus-oidc`) and the 25-minute-inactivity warning dialog are already
implemented in code, but wired up against placeholder configuration — no real
Azure AD tenant exists yet. This section is what a human needs to do to make
it actually work against a real tenant.

### 1. Create two Azure AD app registrations

**SPA registration** (the Angular frontend):

- Platform type: **Single-page application**.
- Redirect URI(s): must match the `redirectUri` placeholder in
  `frontend/src/environment/environment.ts` — for local dev this is
  `http://localhost:4200`; add the production URL as an additional redirect
  URI when deploying.
- **No client secret needed, ever.** This is a public PKCE client: MSAL.js
  performs the Authorization Code + PKCE flow entirely in the browser, and the
  backend only *validates* tokens — it never issues them and never needs a
  secret either.

**API registration** (the Quarkus backend, exposed as a protected resource):

- Under **Expose an API**, set an Application ID URI of the form
  `api://{apiClientId}` (this matches the `api://{apiClientId}/access_as_user`
  scope already declared in the `azureAd` security scheme in
  `api/openapi.yaml`).
- Add a scope named `access_as_user`.
- Back in the **SPA registration**, add a delegated API permission for that
  `access_as_user` scope (pointing at the API registration) and grant admin
  consent for it.

**Important gotcha:** in the API registration's manifest, set
`accessTokenAcceptedVersion` to `2`. The OIDC config in
`src/main/resources/application.properties` is hardcoded against the Azure AD
**v2.0** authority endpoint
(`https://login.microsoftonline.com/${AZURE_AD_TENANT_ID}/v2.0`). If the API
registration is left on v1.0 (the manifest default for older app
registrations), Azure AD will issue v1.0-format tokens whose issuer/audience
`quarkus-oidc` will reject against the v2.0 endpoint it's configured for.

### 2. Plug in the real values

**Backend** — export these environment variables before running
`./mvnw quarkus:dev` (or in the production environment), exactly as
referenced in `src/main/resources/application.properties`:

- `AZURE_AD_TENANT_ID` — used in `quarkus.oidc.auth-server-url`.
- `AZURE_AD_API_CLIENT_ID` — used in both `quarkus.oidc.client-id` and
  `quarkus.oidc.token.audience` (as `api://${AZURE_AD_API_CLIENT_ID}`), so it
  must be the **API** registration's client/application ID, not the SPA's.

Without these exported, `%dev`/`%test` profiles fall back to placeholder
values and disable OIDC discovery on purpose (see the comments in
`application.properties`) so local dev/test boot doesn't hang trying to reach
`login.microsoftonline.com`.

**Frontend** — replace the placeholder fields in
`frontend/src/environment/environment.ts` (in the `auth` block) with the real
values from the two app registrations above:

- `tenantId` — currently `'REPLACE_WITH_TENANT_ID'`.
- `spaClientId` — currently `'REPLACE_WITH_SPA_CLIENT_ID'` (the **SPA**
  registration's client ID).
- `apiClientId` — currently `'REPLACE_WITH_API_CLIENT_ID'` (the **API**
  registration's client ID; must match `AZURE_AD_API_CLIENT_ID` on the
  backend).
- `redirectUri` / `postLogoutRedirectUri` — already `http://localhost:4200`
  for local dev; update for other environments to match the SPA
  registration's redirect URIs.

Note: these are **not** runtime secrets. `environment.ts` is baked into the
JS bundle at build time, and tenant ID / client IDs are public identifiers
for a public SPA client (by design — that's why no client secret exists).
They're placeholders only because the real values aren't known yet, not
because they need to be hidden.

### 3. Manual verification required (cannot be automated here)

Once the above is filled in, a human must perform one real end-to-end login
test against a real Azure AD tenant: redirect to the Microsoft login page →
consent → land back authenticated in the app → a call to a protected
`/api/*` endpoint succeeds with the attached Bearer token. This requires an
interactive Microsoft account consent flow, which cannot be performed or
verified by an AI agent in a sandboxed environment.

Everything else — auth guard logic, token audience/issuer configuration,
backend 401/200 tests, and the idle-timeout countdown logic — was written
with automated tests in mind and is meant to be verified by running the
project's full test suite once a working build environment is available. In
this repository's current sandbox, both `npm install`/`npm test` and
`./mvnw verify` fail due to an external network-proxy restriction unrelated
to the feature code itself, so **nothing on this feature branch has actually
been build/test-verified yet**. Before merging, a human needs to run, in an
unrestricted environment:

```shell script
./mvnw verify
```

and, from `frontend/`:

```shell script
npm run lint && npm test && npm run build
```

#### Known issue: sandbox network proxy blocks the allowlist it accepted

Root cause of the network-proxy restriction above, for whoever picks this up:

1. `sandbox.network.allowedDomains` is correctly parsed and displayed by the
   `/sandbox` Config tab, but the running srt proxy (`localhost:3128`) rejects
   every listed domain with `403 blocked-by-allowlist`. Reproduced on
   `repo1.maven.org`, `pypi.org`, `github.com`. Persists across a full session
   restart (fresh proxy auth token each time — rules out staleness).
2. `sandbox.excludedCommands` does not exempt commands from network namespace
   isolation on Linux/WSL2. `ip addr` inside an "excluded" `npm install` shows
   only the loopback interface — the process never leaves the bubblewrap
   container. Removing the sandbox proxy env vars for such a command causes
   immediate `EAI_AGAIN`, since the private network namespace has no route out
   except the (separately broken) allowlist proxy.

Environment: Claude Code 2.1.210, WSL2 (bubblewrap + socat, Unix-domain-socket
bridge to an outer-namespace TCP proxy). Possible upstream bug:
[anthropics/claude-code#30112](https://github.com/anthropics/claude-code/issues/30112).

This has only been reproduced with Claude Code's sandbox on WSL2 — it has not
yet been verified on other platforms (native Linux, macOS/Seatbelt) or with
other AI coding tools (Codex, Gemini CLI), so treat it as scoped to that combo
until someone confirms otherwise.
