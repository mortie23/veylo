# powerpages-local

A local development server for Microsoft Power Pages that eliminates the 45-second "deploy → clear cache → refresh" feedback loop by providing an instant, mock-driven local preview with hot reloading.

This package accurately models the Power Pages rendering pipeline by parsing Dataverse YAML files, utilizing a custom LiquidJS engine, and locally resolving `{% include %}` template chains.

## Usage

### Configuration

Create a `powerpages-local.config.cjs` file in your repository root:

```javascript
/** @type {import('powerpages-local').PowerPagesLocalConfig} */
module.exports = {
  // Path to your PAC CLI-exported site directory
  sitePath: './src/orgfile-manager',
  // Content locale
  locale: 'en-US',
  // Port for the dev server
  port: 3000,
  // Default user role to simulate ('anonymous', 'authenticated', 'admin')
  defaultRole: 'anonymous',
};
```

### Running the Server Locally (Current Mono-repo Setup)

While the package is located inside the current project repository (`packages/powerpages-local`), you can spin it up directly using the provided npm scripts.

Open a terminal, navigate to the package directory, and run the dev script:

```bash
cd packages/powerpages-local
npm run dev
```

Alternatively, from the root of the repository, you can execute the CLI via `tsx` (the TypeScript executor):

```bash
node --import ./packages/powerpages-local/node_modules/tsx/dist/esm/index.mjs ./packages/powerpages-local/src/cli.ts
```

The server will auto-discover the `powerpages-local.config.cjs` in your root folder and spin up at `http://localhost:3000`.

---

## Roadmap: Migration & npm Publishing

This package was designed from day one to be decoupled from the Veylo repository. Here is the plan to transition it to a standalone open-source npm package:

### 1. Repository Extraction
- Create a new GitHub repository: `mortie23/powerpages-local`.
- Move the contents of `packages/powerpages-local/` to the root of the new repository.
- Ensure the standalone repo contains its own `package.json`, `tsconfig.json`, `README.md`, and `LICENSE`.

### 2. CI/CD & Testing
- Set up GitHub Actions for continuous integration.
- Include a synthetic Power Pages site structure in a `test/fixtures/` folder.
- Ensure `vitest` runs automatically on all PRs to validate the custom LiquidJS engine, YAML loaders, and routing server.

### 3. Publishing to npm
- Finalize the package name (e.g., `@mortie23/powerpages-local` or `powerpages-local` if available).
- Run `npm run build` to generate the `dist/` artifacts (ESM, CJS, and TypeScript definitions).
- Authenticate and publish using:
  ```bash
  npm publish --access public
  ```

### 4. Integration Back to Veylo
- Once published, delete the local `packages/powerpages-local/` folder from the Veylo repository.
- Install the package as a dev dependency:
  ```bash
  npm install -D powerpages-local
  ```
- Add a script to Veylo's root `package.json`:
  ```json
  "scripts": {
    "preview": "powerpages-local"
  }
  ```
- Developers will simply run `npm run preview` to launch the local Power Pages environment.
