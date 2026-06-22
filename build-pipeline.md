# Building the API-Quality Pipeline in Harness CI

This guide builds a Harness CI pipeline that runs the API documentation-quality
validator as **independent step-scripts**, in project **Wakanda**
(`bootcampjune2026` org, account `fAp1ee68RWmCJrfsdhwMeA`).

Pipelines URL:
`https://bootcamp-playground.pr2.harness.io/ng/account/fAp1ee68RWmCJrfsdhwMeA/module/ci/orgs/bootcampjune2026/projects/Wakanda/pipelines`

---

## What the pipeline does

```
1 download spec ─▶ ┌─ 2 dynamic test ─┐ ─▶ 4 build dashboard ─▶ publish
                   └─ 3 static  test ─┘     (results.json + report.html)
```

Each box is one of the scripts in `p1/steps/`, run as a Harness **Run** step.
Steps 2 and 3 only need the spec, so they run **in parallel**.

| Step | Script | Credentials it needs |
|------|--------|----------------------|
| 1 Download spec | `steps/step1_download_spec.py` | none |
| 2 Dynamic test | `steps/step2_dynamic_test.py` | `HARNESS_API_KEY` + `HARNESS_ACCOUNT` (+ `HARNESS_ORG`, `HARNESS_BASE_URL`) |
| 3 Static test | `steps/step3_static_test.py` | `ANTHROPIC_API_KEY` (LLM part only) |
| 4 Build dashboard | `steps/step4_build_dashboard.py` | none |

> **Credential rule:** dynamic = live Harness API → Harness key/account.
> static (LLM) = Anthropic → Anthropic key. The deterministic static checks need nothing.

**Outputs** (written by step 4 to `p1/results/`):
- `results.json` — feeds the Streamlit app (`dashboard.py`)
- `report.html` — self-contained, open in any browser (no Streamlit needed)

---

## Prerequisites (once)

### 1. Put the code in a Git repo
CI clones a repository, so `p1/` must live in Git.

**Option A — GitHub**
```bash
cd /Users/anuj/Desktop/hackathon
git init && git add . && git commit -m "API quality validator"
gh repo create harness-hack --private --source=. --push   # or push to an existing remote
```
Make sure `p1/.env` is **not** committed (it's already in `.gitignore`).

**Option B — Harness Code Repo (built-in)**
Project **Wakanda → Code → Repositories → New Repository**, then push `p1/` into it.

### 2. Create the secrets
**Wakanda → Project Settings → Secrets → New Secret → Text**

| Secret name | Value |
|-------------|-------|
| `harness_api_key` | a **fresh** PAT/x-api-key (rotate the shared one) |
| `anthropic_api_key` | your Claude API key |

Account id and org are not secret — pass them as plain env values.

### 3. Create a Git connector
**Project Settings → Connectors → New Connector → GitHub** (or use the built-in
Harness Code connector). Authenticate and **Test Connection**.

---

## Fast path — paste the YAML

1. Open the Pipelines URL → **Create a Pipeline** → name `API Quality Validation`
   → store **Inline** → **Start**.
2. Switch the editor from **Visual** to **YAML** (top-right).
3. Paste the contents of `p1/harness-pipeline.yml`.
4. In the **Codebase** settings set the **Connector** and **Repository** from the
   prerequisites.
5. **Save → Run**.

The full YAML is in `p1/harness-pipeline.yml` and reproduced at the bottom of this doc.

---

## Manual path — step by step

### A. Create pipeline and stage
1. **Create a Pipeline** → `API Quality Validation` → Inline → **Start**.
2. **Add Stage → Build (CI)** → name `validate` → **Set Up Stage**.
3. **Codebase**: pick the Git connector and repository → continue.
4. **Infrastructure** tab → **Cloud** (Harness-hosted) → OS **Linux**, Arch **Amd64**.

> For every Run step below: set **Shell = Sh**. To guarantee Python is available,
> set **Image = `python:3.11`** and **Container Registry = `account.harnessImage`**
> (the built-in Docker Hub connector).

### B. Add the steps (Execution → Add Step → **Run**)

**Step 0 — Install deps**
```sh
cd p1
pip install -r requirements.txt
```

**Step 1 — Download Spec**
```sh
cd p1
python steps/step1_download_spec.py
```
Optional env var to override the source spec:
`SPEC_URL = https://apidocs.harness.io/_bundle/index.yaml`

**Add a Parallel group** (`Add Step` gives the option to add steps in parallel),
then put these two inside it:

**Step 2 — Dynamic Test**  → Optional Configuration → **Environment Variables**
```sh
cd p1
python steps/step2_dynamic_test.py
```
| Name | Value |
|------|-------|
| `HARNESS_API_KEY` | `<+secrets.getValue("harness_api_key")>` |
| `HARNESS_ACCOUNT` | `fAp1ee68RWmCJrfsdhwMeA` |
| `HARNESS_ORG` | `bootcampjune2026` |
| `HARNESS_BASE_URL` | `https://bootcamp-playground.pr2.harness.io` |

**Step 3 — Static Test** → **Environment Variables**
```sh
cd p1
python steps/step3_static_test.py
```
| Name | Value |
|------|-------|
| `ANTHROPIC_API_KEY` | `<+secrets.getValue("anthropic_api_key")>` |

(Close the parallel group.)

**Step 4 — Build Dashboard Data**
```sh
cd p1
python steps/step4_build_dashboard.py
ls -la results/
```
This writes `results/results.json` **and** `results/report.html`.

**Step 5 — Publish report** (Add Step → **Upload Artifacts**, or a Run step)
```sh
cd p1
ls -la results/
```
Point an Upload-Artifacts step (S3/GCS) at `p1/results/` so `report.html` and
`results.json` are downloadable from each run.

### C. Save and run
**Save → Run → Run Pipeline.** Watch each step's logs in the execution view.

---

## Viewing results

- **report.html** — download from the run's artifacts and open in a browser.
  Fully self-contained: metrics, live request/response, and every diff.
- **results.json** — feed the Streamlit dashboard:
  ```bash
  cd p1
  pip install -r requirements.txt
  streamlit run dashboard.py     # sidebar: point at the downloaded results.json
  ```
  To deploy the Streamlit app (e.g. Streamlit Community Cloud / a container),
  ship `dashboard.py` + `results.json`; the app reads the JSON at the path in
  the sidebar (default `results/results.json`).

---

## Running locally (same scripts the pipeline uses)

```bash
cd p1
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill HARNESS_API_KEY, HARNESS_ACCOUNT, HARNESS_ORG, ANTHROPIC_API_KEY, HARNESS_BASE_URL

python run.py                   # runs steps 1→4 in order
python run.py --skip-download   # reuse an already-downloaded spec
python run.py --serve           # then launch the Streamlit dashboard

# or run any step on its own:
python steps/step1_download_spec.py
python steps/step2_dynamic_test.py
python steps/step3_static_test.py
python steps/step4_build_dashboard.py
```

Each step reads/writes JSON artifacts in `results/`, so they are independent and
re-runnable in isolation — exactly how Harness executes them as separate steps.

---

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| Step 2 prints `SKIP — HARNESS_API_KEY / HARNESS_ACCOUNT not set` | Secret not wired or value empty. Check the step's Environment Variables. |
| Live calls return `401` with an HTML sign-in body | Wrong cluster. `HARNESS_BASE_URL` must match the host in your Harness UI URL (`bootcamp-playground.pr2.harness.io`). |
| `401 {"message":"Token is not valid."}` | Expired/invalid PAT — generate a fresh token. |
| `403` on `POST /ng/api/projects` org create | Token lacks org-create rights. Set `HARNESS_ORG` to an existing org to reuse it. |
| Step 3 prints `SKIP LLM` | `ANTHROPIC_API_KEY` not set — deterministic checks still run. |
| `Spec not found … Run step 1 first` | Step 1 didn't run / artifact not shared. Ensure steps share the same stage workspace. |

---

## The pipeline YAML

The complete, ready-to-paste pipeline lives at **`p1/harness-pipeline.yml`**
(`projectIdentifier: Wakanda`, `orgIdentifier: bootcampjune2026`). Use the Fast
path above to paste it, or build it with the Manual path.
