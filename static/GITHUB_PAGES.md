# Publish CampusLoop on GitHub Pages

This repository supports **two separate entry points**. The existing Docker application is unchanged.

| Entry point | Purpose | Server required? |
| --- | --- | --- |
| `index.html` in the repository root | Public project showcase on GitHub Pages | No Python backend |
| `static/index.html`, served by `app/server.py` | Complete CampusLoop app at `http://localhost:8010` | Python, SQLite, and the configured Docker services |

## What visitors can use on Pages

The public site includes the existing landing page and photos, navigation links in section order, expandable FAQs, the interactive 1–4-rider pricing example, and the roadmap. The layout is responsive, and the CampusLoop logo returns to the top.

**GitHub Pages is static hosting.** It does not run the Python API, SQLite database operations, Docker Compose, or Ollama. Login, signup, posting a ride, real matching/bookings, Google Routes API requests, notifications, and the live AI chatbot are not enabled by this Pages deployment. Calls to action explain how to run the full app; they do not collect credentials or create pretend bookings.

The pricing example uses the existing sample trip, not a live route quote. Google API keys stay in the backend's local `.env`; no keys are required or published for Pages.

## 1. Add these changes to the repository

From your existing checkout, create a branch:

```bash
git switch -c feature/github-pages
```

Copy the files from the update archive into the same repository, preserving their paths. Include the hidden `.github` directory. The new root `index.html` goes **beside** `compose.yaml`; it does not replace `static/index.html`.

Commit only the intended files:

```bash
git add index.html static/pages.js static/pages.css static/pages-config.js \
  .github/workflows/deploy-pages.yml tests/pages_contract.cjs \
  GITHUB_PAGES.md PAGES_VALIDATION.md README.md .gitignore
git commit -m "Add GitHub Pages project showcase"
git push -u origin feature/github-pages
```

Open a pull request and merge it into `main`. The deployment workflow publishes from `main` only. It does not publish feature branches or pull requests.

## 2. Enable GitHub Pages

In the GitHub repository, open **Settings → Pages**. Under **Build and deployment → Source**, select **GitHub Actions**. Do not choose a root-folder/Jekyll deployment; the supplied workflow publishes only a vetted set of public files.

You need repository permissions to configure Pages. GitHub Free supports Pages from public repositories; private-repository support depends on the account plan. Review what is public before publishing, even when the source repository is private.

## 3. Run the deployment

After the workflow has been merged into `main`, open **Actions → Deploy CampusLoop to GitHub Pages → Run workflow**, select `main`, and run it. Use this manual run for first setup if the initial push ran before Pages was enabled.

The workflow validates the static entry point, assembles the public files, and publishes the site. Subsequent pushes to `main` that change the root entry point, static assets, Pages tests, or deployment workflow automatically redeploy it.

Find the real published URL in **Settings → Pages** or the successful deployment's `github-pages` environment. A normal project-site URL looks like:

```text
https://YOUR_GITHUB_USERNAME.github.io/YOUR_REPOSITORY_NAME/
```

Use the exact URL GitHub displays, including the repository name and trailing slash. Do not treat a guessed URL as evidence that deployment succeeded. Custom-domain and account-site URLs may differ.

## Public files and security

The workflow uploads `_site/`, not the whole repository. It explicitly includes:

```text
index.html
static/style.css
static/landing.css
static/landing.js
static/pages.css
static/pages.js
static/pages-config.js
static/landing-photo-*.jpeg
```

It excludes Python source from the hosted artifact, `.env`, databases, Docker configuration, and local model files. This does **not** make source files private in a public GitHub repository: never commit real credentials, student data, or production databases in the first place.

Asset paths work at both the domain root and a project subpath such as `/CampusLoop/`. A separate static bootstrap renders the existing landing content without loading `static/app.js` or calling `/api/config`. The workflow adds a commit-based cache version to the HTML assets and fills in the repository link automatically.

## Optional: connect a separately hosted full app

After the complete Python application is deployed to an HTTPS server, edit the **public** configuration in `static/pages-config.js`:

```javascript
window.CAMPUSLOOP_PAGES = {
  liveAppUrl: 'https://YOUR_FULL_APP_DOMAIN',
  repositoryUrl: ''
};
```

Commit and push the change. The landing page's login, find-a-ride, and post-a-trip buttons then navigate to the separately hosted app's landing page. This is a normal page navigation, not a cross-origin API connection. Complete login and booking inside that full app. The URL must use HTTPS and a different origin from the showcase. Leave it empty until an actual deployment exists.

Hosting the complete app requires a production-capable backend, persistent storage, secure cookies/HTTPS, real email delivery if signup verification is used, a protected Routes API key, and an accessible Ollama service or another deliberately configured model provider. The local Compose settings and demo credentials are not a production deployment. Do not expose the local demo publicly without reviewing authentication, secrets, persistence, and demo mode.

## Local development stays the same

Run the complete app as before:

```bash
HEKY_PORT=8010 docker compose up --build -d
```

Open `http://localhost:8010`. You do not need to rebuild Docker just to publish the Pages site; the GitHub Actions workflow deploys its separate static entry point.

To preview only the Pages showcase locally, run this from the repository root:

```bash
python3 -m http.server 8080 --bind 127.0.0.1
```

Then open `http://localhost:8080/`. Stop this preview with `Ctrl+C`. This is a local preview command, not a new application script and not a way to run the complete backend. Binding to `127.0.0.1` avoids exposing the repository to other computers.

Run the static contract tests with Node.js:

```bash
node --test tests/pages_contract.cjs
```

Node.js is needed for this optional local test, not for normal Docker startup. GitHub-hosted runners run the checks during deployment.

## Troubleshooting

**The workflow is missing:** Check that `.github/workflows/deploy-pages.yml` was copied and committed to `main`. Hidden directories may be omitted by some file-copy workflows.

**The job is skipped:** This workflow publishes only from `main`. If your default branch has another name, update both `push.branches` and the job's `if` condition.

**The first deployment fails with a Pages configuration error:** Select **GitHub Actions** under **Settings → Pages**, check repository/plan permissions, then run the workflow again.

**The page says it cannot connect to the API:** The wrong entry point was deployed. The public artifact must use the root `index.html`, not `static/index.html`.

**Images or styles are missing:** Publish the complete workflow artifact. Do not upload only `index.html` or change `./static/` references to domain-root `/static/` paths.

**A successful deploy still looks old:** Open the deployment URL, check the latest workflow completed successfully, and hard-refresh the browser. Assets built by the workflow have commit-based cache versions.

**Login opens an explanation dialog:** This is intentional in showcase mode. Enable a real, separately hosted application through `liveAppUrl`; GitHub Pages alone cannot host the backend.

## GitHub documentation

- [Creating a GitHub Pages site](https://docs.github.com/en/pages/getting-started-with-github-pages/creating-a-github-pages-site)
- [Configuring a publishing source](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site)
- [Using custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages)
- [GitHub Pages limits and usage rules](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
