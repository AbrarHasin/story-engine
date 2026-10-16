# Dependency licence audit

Project licence: **GPL-3.0** (see `LICENSE`, "GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007").

## 1. Summary

- **Date:** 2026-10-17
- **Scope:** 399 third-party packages in total: 154 Python (130 runtime, 24 dev), 242 frontend npm (16 runtime, 226 dev/build), 3 root/e2e npm (dev). Docker images from the compose files and Dockerfiles are listed separately in section 3.4. They are not counted above.
- **Blockers:** none for distributing the repository source or the Docker images as currently built. There are conditional items, mainly the NVIDIA proprietary CUDA wheels that exist in the local dev venv. See section 4.
- **Unknown:** 1 package with no licence metadata (`cuda-toolkit`). See section 5.

### Method

- **Python.** Direct dependencies were parsed from `backend/requirements.txt` and `backend/requirements-dev.txt` in this worktree (`wt-se-triage`). Licence metadata came from the installed distributions in `/home/abrar/code/story-engine/backend/.venv` (Python 3.12), read with `importlib.metadata` from three fields: `License-Expression`, `License` and any `Classifier: License ::`. The tree was walked transitively through `Requires-Dist`. Requirements gated on extras were skipped, except the extras the manifest itself asks for (`uvicorn[standard]`, `sqlalchemy[asyncio]`, `python-jose[cryptography]`). Environment markers were evaluated against the venv's interpreter. Nothing was installed. The "Metadata source" column records where each licence came from: `expr` = `License-Expression`, `field` = `License`, `classifier` = trove classifier only, `field+classifier` = the `License` field was blank, `UNKNOWN` or full text, so the SPDX id was taken from the classifier.
- **npm.** The audit started from `dependencies` and `devDependencies` in `frontend/package.json` and in the root `package.json` (Playwright). It then walked each package's `dependencies` plus any optional dependencies that are actually installed, resolving packages with Node's lookup rules against `/home/abrar/code/story-engine/frontend/node_modules` and `/home/abrar/code/story-engine/node_modules`. Licences were read from the `license` field of each package's `package.json`, or from the legacy `licenses` field. A package reachable from both the runtime and the dev roots is counted as runtime.
- **Docker images.** Licences for images are from general knowledge (memory), not metadata. They are marked as such.
- **Caveats.**
  - Installed versions are what the shared `story-engine` environments contain today. Several requirements are open ranges (`>=`), so a fresh install may resolve to different versions. Example: `langfuse>=2.57.3` resolved to 4.7.1.
  - `frontend/package.json` is identical in the worktree and in `story-engine`.
  - `litellm` was removed from `backend/requirements.txt` in PR #22. The shared dev venv still has it installed (1.86.2, `License-Expression: MIT`), so it is excluded from the tables.

### Counts by licence family (all ecosystems)

| Family | Packages |
|---|---|
| MIT | 259 |
| Apache-2.0 | 55 |
| BSD | 44 |
| ISC | 18 |
| Proprietary (NVIDIA) | 7 |
| Dual / choice (permissive) | 4 |
| MPL-2.0 (weak copyleft, incl. combos) | 3 |
| Other permissive (MIT-CMU, Unlicense, BlueOak) | 3 |
| PSF / Python | 3 |
| Apache-2.0 + CNRI-Python (review) | 1 |
| CC-BY-4.0 (data) | 1 |
| Unknown / missing | 1 |

Python only:

| Family | Packages |
|---|---|
| MIT | 60 |
| BSD | 36 |
| Apache-2.0 | 35 |
| Proprietary (NVIDIA) | 7 |
| Dual / choice (permissive) | 4 |
| ISC | 3 |
| MPL-2.0 (weak copyleft, incl. combos) | 3 |
| Other permissive (MIT-CMU, Unlicense, BlueOak) | 2 |
| PSF / Python | 2 |
| Apache-2.0 + CNRI-Python (review) | 1 |
| Unknown / missing | 1 |

npm only (frontend + root):

| Family | Packages |
|---|---|
| MIT | 199 |
| Apache-2.0 | 20 |
| ISC | 15 |
| BSD | 8 |
| CC-BY-4.0 (data) | 1 |
| Other permissive (MIT-CMU, Unlicense, BlueOak) | 1 |
| PSF / Python | 1 |

The families are grouped as follows:

- "BSD" covers BSD-2-Clause, BSD-3-Clause and unversioned "BSD" classifiers.
- "Dual / choice" means an `OR` expression in which every option is permissive.
- "MPL-2.0 (incl. combos)" covers `certifi` (MPL-2.0), `orjson` (MPL-2.0 AND (Apache-2.0 OR MIT)) and `tqdm` (MPL-2.0 AND MIT).
- "PSF / Python" covers `aiohappyeyeballs`, `typing_extensions` and npm `argparse` (Python-2.0).

## 2. Package tables

### 2.1 Python (backend)

| Package | Version | Licence | Metadata source | Direct / transitive | Runtime / dev |
|---|---|---|---|---|---|
| aiohttp | 3.11.11 | Apache-2.0 | field | direct | runtime |
| aioredis | 2.0.1 | MIT | field | direct | runtime |
| alembic | 1.14.0 | MIT | field | direct | runtime |
| asyncpg | 0.30.0 | Apache-2.0 | field | direct | runtime |
| bcrypt | 5.0.0 | Apache-2.0 | field | direct | runtime |
| email-validator | 2.3.0 | Unlicense | field | direct | runtime |
| fastapi | 0.115.5 | MIT | classifier | direct | runtime |
| httpx | 0.28.1 | BSD-3-Clause | field | direct | runtime |
| langchain | 1.3.2 | MIT | field | direct | runtime |
| langchain-anthropic | 1.4.4 | MIT | field | direct | runtime |
| langchain-core | 1.4.0 | MIT | field | direct | runtime |
| langchain-openai | 1.2.2 | MIT | field | direct | runtime |
| langfuse | 4.7.1 | MIT | expr | direct | runtime |
| langgraph | 1.2.2 | MIT | expr | direct | runtime |
| langgraph-checkpoint-redis | 0.4.1 | MIT | field | direct | runtime |
| numpy | 2.4.6 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 | expr | direct | runtime |
| opentelemetry-api | 1.42.1 | Apache-2.0 | expr | direct | runtime |
| opentelemetry-sdk | 1.42.1 | Apache-2.0 | expr | direct | runtime |
| pgvector | 0.3.6 | MIT | field | direct | runtime |
| pydantic | 2.10.4 | MIT | expr | direct | runtime |
| pydantic-settings | 2.7.0 | MIT | field | direct | runtime |
| python-dotenv | 1.0.1 | BSD-3-Clause | field | direct | runtime |
| python-jose | 3.3.0 | MIT | field | direct | runtime |
| python-multipart | 0.0.12 | Apache-2.0 | expr | direct | runtime |
| redis | 5.2.1 | MIT | field | direct | runtime |
| sentence-transformers | 3.3.1 | Apache-2.0 | field | direct | runtime |
| SQLAlchemy | 2.0.36 | MIT | field | direct | runtime |
| sse-starlette | 2.1.3 | BSD-3-Clause | field | direct | runtime |
| uvicorn | 0.32.1 | BSD-3-Clause | field | direct | runtime |
| aiohappyeyeballs | 2.6.2 | PSF-2.0 | field | transitive | runtime |
| aiosignal | 1.4.0 | Apache-2.0 | field | transitive | runtime |
| annotated-types | 0.7.0 | MIT | classifier | transitive | runtime |
| anthropic | 0.105.2 | MIT | field | transitive | runtime |
| anyio | 4.7.0 | MIT | field | transitive (also pinned in dev reqs) | runtime |
| async-timeout | 5.0.1 | Apache-2.0 | field | transitive | runtime |
| attrs | 26.1.0 | MIT | expr | transitive | runtime |
| backoff | 2.2.1 | MIT | field | transitive | runtime |
| certifi | 2026.5.20 | MPL-2.0 | field | transitive | runtime |
| cffi | 2.0.0 | MIT | expr | transitive | runtime |
| charset-normalizer | 3.4.7 | MIT | field | transitive | runtime |
| click | 8.4.1 | BSD-3-Clause | expr | transitive | runtime |
| cryptography | 48.0.0 | Apache-2.0 OR BSD-3-Clause | expr | transitive | runtime |
| cuda-bindings | 13.3.1 | LicenseRef-NVIDIA-SOFTWARE-LICENSE | expr | transitive | runtime |
| cuda-pathfinder | 1.5.5 | Apache-2.0 | expr | transitive | runtime |
| cuda-toolkit | 13.0.2 | UNKNOWN | none | transitive | runtime |
| distro | 1.9.0 | Apache-2.0 | field | transitive | runtime |
| dnspython | 2.8.0 | ISC | field | transitive | runtime |
| docstring_parser | 0.18.0 | MIT | field | transitive | runtime |
| ecdsa | 0.19.2 | MIT | field | transitive | runtime |
| filelock | 3.29.0 | MIT | expr | transitive | runtime |
| frozenlist | 1.8.0 | Apache-2.0 | field | transitive | runtime |
| fsspec | 2026.4.0 | BSD-3-Clause | expr | transitive | runtime |
| googleapis-common-protos | 1.75.0 | Apache-2.0 | field | transitive | runtime |
| greenlet | 3.5.1 | MIT AND PSF-2.0 | expr | transitive | runtime |
| h11 | 0.16.0 | MIT | field | transitive | runtime |
| hf-xet | 1.5.0 | Apache-2.0 | expr | transitive | runtime |
| httpcore | 1.0.9 | BSD-3-Clause | expr | transitive | runtime |
| httptools | 0.8.0 | MIT | expr | transitive | runtime |
| huggingface_hub | 0.36.2 | Apache-2.0 | field | transitive | runtime |
| idna | 3.17 | BSD-3-Clause | expr | transitive | runtime |
| Jinja2 | 3.1.6 | BSD-3-Clause | classifier | transitive | runtime |
| jiter | 0.15.0 | MIT | expr | transitive | runtime |
| joblib | 1.5.3 | BSD-3-Clause | expr | transitive | runtime |
| jsonpatch | 1.33 | BSD-3-Clause | field | transitive | runtime |
| jsonpath-ng | 1.8.0 | Apache-2.0 | field | transitive | runtime |
| jsonpointer | 3.1.1 | BSD-3-Clause | field | transitive | runtime |
| langchain-protocol | 0.0.16 | MIT | field | transitive | runtime |
| langgraph-checkpoint | 4.1.1 | MIT | expr | transitive | runtime |
| langgraph-prebuilt | 1.1.0 | MIT | expr | transitive | runtime |
| langgraph-sdk | 0.3.15 | MIT | expr | transitive | runtime |
| langsmith | 0.8.8 | MIT | field | transitive | runtime |
| Mako | 1.3.12 | MIT | field | transitive | runtime |
| MarkupSafe | 3.0.3 | BSD-3-Clause | expr | transitive | runtime |
| ml_dtypes | 0.5.4 | Apache-2.0 | expr | transitive | runtime |
| mpmath | 1.3.0 | BSD (unversioned) | field | transitive | runtime |
| multidict | 6.7.1 | Apache-2.0 | field | transitive | runtime |
| networkx | 3.6.1 | BSD-3-Clause | expr | transitive | runtime |
| nvidia-cublas | 13.1.1.3 | LicenseRef-NVIDIA-Proprietary | expr | transitive | runtime |
| nvidia-cuda-nvrtc | 13.0.88 | LicenseRef-NVIDIA-Proprietary | field | transitive | runtime |
| nvidia-cudnn-cu13 | 9.20.0.48 | LicenseRef-NVIDIA-Proprietary | expr | transitive | runtime |
| nvidia-cusparselt-cu13 | 0.8.1 | LicenseRef-NVIDIA-Proprietary | field | transitive | runtime |
| nvidia-nccl-cu13 | 2.29.7 | LicenseRef-NVIDIA-Proprietary | expr | transitive | runtime |
| nvidia-nvshmem-cu13 | 3.4.5 | LicenseRef-NVIDIA-Proprietary | expr | transitive | runtime |
| openai | 2.38.0 | Apache-2.0 | field | transitive | runtime |
| opentelemetry-exporter-otlp-proto-common | 1.42.1 | Apache-2.0 | expr | transitive | runtime |
| opentelemetry-exporter-otlp-proto-http | 1.42.1 | Apache-2.0 | expr | transitive | runtime |
| opentelemetry-proto | 1.42.1 | Apache-2.0 | expr | transitive | runtime |
| opentelemetry-semantic-conventions | 0.63b1 | Apache-2.0 | expr | transitive | runtime |
| orjson | 3.11.9 | MPL-2.0 AND (Apache-2.0 OR MIT) | expr | transitive | runtime |
| ormsgpack | 1.12.2 | Apache-2.0 OR MIT | expr | transitive | runtime |
| packaging | 26.2 | Apache-2.0 OR BSD-2-Clause | expr | transitive | runtime |
| pillow | 12.2.0 | MIT-CMU | expr | transitive | runtime |
| propcache | 0.5.2 | Apache-2.0 | field | transitive | runtime |
| protobuf | 6.33.6 | BSD-3-Clause | field | transitive | runtime |
| pyasn1 | 0.6.3 | BSD-2-Clause | field | transitive | runtime |
| pycparser | 3.0 | BSD-3-Clause | expr | transitive | runtime |
| pydantic_core | 2.27.2 | MIT | field | transitive | runtime |
| python-ulid | 3.1.0 | MIT | expr | transitive | runtime |
| PyYAML | 6.0.3 | MIT | field | transitive | runtime |
| redisvl | 0.19.0 | MIT | expr | transitive | runtime |
| regex | 2026.5.9 | Apache-2.0 AND CNRI-Python | expr | transitive | runtime |
| requests | 2.34.2 | Apache-2.0 | field | transitive | runtime |
| requests-toolbelt | 1.0.0 | Apache-2.0 | field | transitive | runtime |
| rsa | 4.9.1 | Apache-2.0 | field | transitive | runtime |
| safetensors | 0.7.0 | Apache-2.0 | classifier | transitive | runtime |
| scikit-learn | 1.8.0 | BSD-3-Clause | expr | transitive | runtime |
| scipy | 1.17.1 | BSD-3-Clause | classifier | transitive | runtime |
| setuptools | 81.0.0 | MIT | expr | transitive | runtime |
| six | 1.17.0 | MIT | field | transitive | runtime |
| sniffio | 1.3.1 | MIT OR Apache-2.0 | field | transitive | runtime |
| starlette | 0.41.3 | BSD-3-Clause | field | transitive | runtime |
| sympy | 1.14.0 | BSD (unversioned) | field | transitive | runtime |
| tenacity | 9.1.4 | Apache-2.0 | field | transitive | runtime |
| threadpoolctl | 3.6.0 | BSD-3-Clause | field | transitive | runtime |
| tiktoken | 0.13.0 | MIT | classifier | transitive | runtime |
| tokenizers | 0.22.2 | Apache-2.0 | classifier | transitive | runtime |
| torch | 2.12.0 | BSD-3-Clause | field | transitive | runtime |
| tqdm | 4.67.3 | MPL-2.0 AND MIT | field | transitive | runtime |
| transformers | 4.57.6 | Apache-2.0 | field | transitive | runtime |
| triton | 3.7.0 | MIT | classifier | transitive | runtime |
| typing_extensions | 4.15.0 | PSF-2.0 | expr | transitive | runtime |
| urllib3 | 2.7.0 | MIT | expr | transitive | runtime |
| uuid_utils | 0.16.0 | BSD-3-Clause | expr | transitive | runtime |
| uvloop | 0.22.1 | MIT | field | transitive | runtime |
| watchfiles | 1.2.0 | MIT | field | transitive | runtime |
| websockets | 16.0 | BSD-3-Clause | expr | transitive | runtime |
| wrapt | 1.17.3 | BSD (unversioned) | field | transitive | runtime |
| xxhash | 3.7.0 | BSD (unversioned) | field | transitive | runtime |
| yarl | 1.24.2 | Apache-2.0 | field | transitive | runtime |
| zstandard | 0.25.0 | BSD-3-Clause | expr | transitive | runtime |
| ipython | 8.31.0 | BSD-3-Clause | field | direct | dev |
| mypy | 1.14.0 | MIT | field | direct | dev |
| pytest | 8.3.4 | MIT | field | direct | dev |
| pytest-asyncio | 0.24.0 | Apache-2.0 | field | direct | dev |
| pytest-cov | 6.0.0 | MIT | field | direct | dev |
| ruff | 0.8.4 | MIT | field | direct | dev |
| asttokens | 3.0.1 | Apache-2.0 | field | transitive | dev |
| coverage | 7.14.1 | Apache-2.0 | field | transitive | dev |
| decorator | 5.3.1 | BSD-2-Clause | field | transitive | dev |
| executing | 2.2.1 | MIT | field | transitive | dev |
| iniconfig | 2.3.0 | MIT | expr | transitive | dev |
| jedi | 0.20.0 | MIT | field | transitive | dev |
| matplotlib-inline | 0.2.2 | BSD-3-Clause | expr | transitive | dev |
| mypy_extensions | 1.1.0 | MIT | expr | transitive | dev |
| parso | 0.8.7 | MIT | field | transitive | dev |
| pexpect | 4.9.0 | ISC | field | transitive | dev |
| pluggy | 1.6.0 | MIT | field | transitive | dev |
| prompt_toolkit | 3.0.52 | BSD-3-Clause | classifier | transitive | dev |
| ptyprocess | 0.7.0 | ISC | classifier | transitive | dev |
| pure_eval | 0.2.3 | MIT | field | transitive | dev |
| Pygments | 2.20.0 | BSD-2-Clause | expr | transitive | dev |
| stack-data | 0.6.3 | MIT | field | transitive | dev |
| traitlets | 5.15.0 | BSD-3-Clause | classifier | transitive | dev |
| wcwidth | 0.7.0 | MIT | expr | transitive | dev |

### 2.2 Frontend npm (`frontend/package.json`)

| Package | Version | Licence | Direct / transitive | Runtime / dev |
|---|---|---|---|---|
| @tanstack/react-query | 5.100.14 | MIT | direct | runtime |
| @tanstack/react-query-devtools | 5.100.14 | MIT | direct | runtime |
| clsx | 2.1.1 | MIT | direct | runtime |
| lucide-react | 0.468.0 | ISC | direct | runtime |
| react | 18.3.1 | MIT | direct | runtime |
| react-dom | 18.3.1 | MIT | direct | runtime |
| react-router-dom | 6.30.4 | MIT | direct | runtime |
| tailwind-merge | 2.6.1 | MIT | direct | runtime |
| zustand | 5.0.14 | MIT | direct | runtime |
| @remix-run/router | 1.23.3 | MIT | transitive | runtime |
| @tanstack/query-core | 5.100.14 | MIT | transitive | runtime |
| @tanstack/query-devtools | 5.100.14 | MIT | transitive | runtime |
| js-tokens | 4.0.0 | MIT | transitive | runtime |
| loose-envify | 1.4.0 | MIT | transitive | runtime |
| react-router | 6.30.4 | MIT | transitive | runtime |
| scheduler | 0.23.2 | MIT | transitive | runtime |
| @types/react | 18.3.30 | MIT | direct | dev |
| @types/react-dom | 18.3.7 | MIT | direct | dev |
| @typescript-eslint/eslint-plugin | 8.60.0 | MIT | direct | dev |
| @typescript-eslint/parser | 8.60.0 | MIT | direct | dev |
| @vitejs/plugin-react | 4.7.0 | MIT | direct | dev |
| autoprefixer | 10.5.0 | MIT | direct | dev |
| eslint | 9.39.4 | MIT | direct | dev |
| postcss | 8.5.15 | MIT | direct | dev |
| tailwindcss | 3.4.19 | MIT | direct | dev |
| typescript | 5.9.3 | Apache-2.0 | direct | dev |
| vite | 6.4.3 | MIT | direct | dev |
| @alloc/quick-lru | 5.2.0 | MIT | transitive | dev |
| @babel/code-frame | 7.29.7 | MIT | transitive | dev |
| @babel/compat-data | 7.29.7 | MIT | transitive | dev |
| @babel/core | 7.29.7 | MIT | transitive | dev |
| @babel/generator | 7.29.7 | MIT | transitive | dev |
| @babel/helper-compilation-targets | 7.29.7 | MIT | transitive | dev |
| @babel/helper-globals | 7.29.7 | MIT | transitive | dev |
| @babel/helper-module-imports | 7.29.7 | MIT | transitive | dev |
| @babel/helper-module-transforms | 7.29.7 | MIT | transitive | dev |
| @babel/helper-plugin-utils | 7.29.7 | MIT | transitive | dev |
| @babel/helper-string-parser | 7.29.7 | MIT | transitive | dev |
| @babel/helper-validator-identifier | 7.29.7 | MIT | transitive | dev |
| @babel/helper-validator-option | 7.29.7 | MIT | transitive | dev |
| @babel/helpers | 7.29.7 | MIT | transitive | dev |
| @babel/parser | 7.29.7 | MIT | transitive | dev |
| @babel/plugin-transform-react-jsx-self | 7.29.7 | MIT | transitive | dev |
| @babel/plugin-transform-react-jsx-source | 7.29.7 | MIT | transitive | dev |
| @babel/template | 7.29.7 | MIT | transitive | dev |
| @babel/traverse | 7.29.7 | MIT | transitive | dev |
| @babel/types | 7.29.7 | MIT | transitive | dev |
| @esbuild/linux-x64 | 0.25.12 | MIT | transitive | dev |
| @eslint-community/eslint-utils | 4.9.1 | MIT | transitive | dev |
| @eslint-community/regexpp | 4.12.2 | MIT | transitive | dev |
| @eslint/config-array | 0.21.2 | Apache-2.0 | transitive | dev |
| @eslint/config-helpers | 0.4.2 | Apache-2.0 | transitive | dev |
| @eslint/core | 0.17.0 | Apache-2.0 | transitive | dev |
| @eslint/eslintrc | 3.3.5 | MIT | transitive | dev |
| @eslint/js | 9.39.4 | MIT | transitive | dev |
| @eslint/object-schema | 2.1.7 | Apache-2.0 | transitive | dev |
| @eslint/plugin-kit | 0.4.1 | Apache-2.0 | transitive | dev |
| @humanfs/core | 0.19.2 | Apache-2.0 | transitive | dev |
| @humanfs/node | 0.16.8 | Apache-2.0 | transitive | dev |
| @humanfs/types | 0.15.0 | Apache-2.0 | transitive | dev |
| @humanwhocodes/module-importer | 1.0.1 | Apache-2.0 | transitive | dev |
| @humanwhocodes/retry | 0.4.3 | Apache-2.0 | transitive | dev |
| @jridgewell/gen-mapping | 0.3.13 | MIT | transitive | dev |
| @jridgewell/remapping | 2.3.5 | MIT | transitive | dev |
| @jridgewell/resolve-uri | 3.1.2 | MIT | transitive | dev |
| @jridgewell/sourcemap-codec | 1.5.5 | MIT | transitive | dev |
| @jridgewell/trace-mapping | 0.3.31 | MIT | transitive | dev |
| @nodelib/fs.scandir | 2.1.5 | MIT | transitive | dev |
| @nodelib/fs.stat | 2.0.5 | MIT | transitive | dev |
| @nodelib/fs.walk | 1.2.8 | MIT | transitive | dev |
| @rolldown/pluginutils | 1.0.0-beta.27 | MIT | transitive | dev |
| @rollup/rollup-linux-x64-gnu | 4.61.0 | MIT | transitive | dev |
| @rollup/rollup-linux-x64-musl | 4.61.0 | MIT | transitive | dev |
| @types/babel__core | 7.20.5 | MIT | transitive | dev |
| @types/babel__generator | 7.27.0 | MIT | transitive | dev |
| @types/babel__template | 7.4.4 | MIT | transitive | dev |
| @types/babel__traverse | 7.28.0 | MIT | transitive | dev |
| @types/estree | 1.0.9 | MIT | transitive | dev |
| @types/json-schema | 7.0.15 | MIT | transitive | dev |
| @types/prop-types | 15.7.15 | MIT | transitive | dev |
| @typescript-eslint/project-service | 8.60.0 | MIT | transitive | dev |
| @typescript-eslint/scope-manager | 8.60.0 | MIT | transitive | dev |
| @typescript-eslint/tsconfig-utils | 8.60.0 | MIT | transitive | dev |
| @typescript-eslint/type-utils | 8.60.0 | MIT | transitive | dev |
| @typescript-eslint/types | 8.60.0 | MIT | transitive | dev |
| @typescript-eslint/typescript-estree | 8.60.0 | MIT | transitive | dev |
| @typescript-eslint/utils | 8.60.0 | MIT | transitive | dev |
| @typescript-eslint/visitor-keys | 8.60.0 | MIT | transitive | dev |
| acorn | 8.16.0 | MIT | transitive | dev |
| acorn-jsx | 5.3.2 | MIT | transitive | dev |
| ajv | 6.15.0 | MIT | transitive | dev |
| ansi-styles | 4.3.0 | MIT | transitive | dev |
| any-promise | 1.3.0 | MIT | transitive | dev |
| anymatch | 3.1.3 | ISC | transitive | dev |
| arg | 5.0.2 | MIT | transitive | dev |
| argparse | 2.0.1 | Python-2.0 | transitive | dev |
| balanced-match | 4.0.4 | MIT | transitive | dev |
| balanced-match | 1.0.2 | MIT | transitive | dev |
| baseline-browser-mapping | 2.10.33 | Apache-2.0 | transitive | dev |
| binary-extensions | 2.3.0 | MIT | transitive | dev |
| brace-expansion | 5.0.6 | MIT | transitive | dev |
| brace-expansion | 1.1.15 | MIT | transitive | dev |
| braces | 3.0.3 | MIT | transitive | dev |
| browserslist | 4.28.2 | MIT | transitive | dev |
| callsites | 3.1.0 | MIT | transitive | dev |
| camelcase-css | 2.0.1 | MIT | transitive | dev |
| caniuse-lite | 1.0.30001793 | CC-BY-4.0 | transitive | dev |
| chalk | 4.1.2 | MIT | transitive | dev |
| chokidar | 3.6.0 | MIT | transitive | dev |
| color-convert | 2.0.1 | MIT | transitive | dev |
| color-name | 1.1.4 | MIT | transitive | dev |
| commander | 4.1.1 | MIT | transitive | dev |
| concat-map | 0.0.1 | MIT | transitive | dev |
| convert-source-map | 2.0.0 | MIT | transitive | dev |
| cross-spawn | 7.0.6 | MIT | transitive | dev |
| cssesc | 3.0.0 | MIT | transitive | dev |
| csstype | 3.2.3 | MIT | transitive | dev |
| debug | 4.4.3 | MIT | transitive | dev |
| deep-is | 0.1.4 | MIT | transitive | dev |
| didyoumean | 1.2.2 | Apache-2.0 | transitive | dev |
| dlv | 1.1.3 | MIT | transitive | dev |
| electron-to-chromium | 1.5.364 | ISC | transitive | dev |
| es-errors | 1.3.0 | MIT | transitive | dev |
| esbuild | 0.25.12 | MIT | transitive | dev |
| escalade | 3.2.0 | MIT | transitive | dev |
| escape-string-regexp | 4.0.0 | MIT | transitive | dev |
| eslint-scope | 8.4.0 | BSD-2-Clause | transitive | dev |
| eslint-visitor-keys | 5.0.1 | Apache-2.0 | transitive | dev |
| eslint-visitor-keys | 3.4.3 | Apache-2.0 | transitive | dev |
| eslint-visitor-keys | 4.2.1 | Apache-2.0 | transitive | dev |
| espree | 10.4.0 | BSD-2-Clause | transitive | dev |
| esquery | 1.7.0 | BSD-3-Clause | transitive | dev |
| esrecurse | 4.3.0 | BSD-2-Clause | transitive | dev |
| estraverse | 5.3.0 | BSD-2-Clause | transitive | dev |
| esutils | 2.0.3 | BSD-2-Clause | transitive | dev |
| fast-deep-equal | 3.1.3 | MIT | transitive | dev |
| fast-glob | 3.3.3 | MIT | transitive | dev |
| fast-json-stable-stringify | 2.1.0 | MIT | transitive | dev |
| fast-levenshtein | 2.0.6 | MIT | transitive | dev |
| fastq | 1.20.1 | ISC | transitive | dev |
| fdir | 6.5.0 | MIT | transitive | dev |
| file-entry-cache | 8.0.0 | MIT | transitive | dev |
| fill-range | 7.1.1 | MIT | transitive | dev |
| find-up | 5.0.0 | MIT | transitive | dev |
| flat-cache | 4.0.1 | MIT | transitive | dev |
| flatted | 3.4.2 | ISC | transitive | dev |
| fraction.js | 5.3.4 | MIT | transitive | dev |
| function-bind | 1.1.2 | MIT | transitive | dev |
| gensync | 1.0.0-beta.2 | MIT | transitive | dev |
| glob-parent | 6.0.2 | ISC | transitive | dev |
| glob-parent | 5.1.2 | ISC | transitive | dev |
| globals | 14.0.0 | MIT | transitive | dev |
| has-flag | 4.0.0 | MIT | transitive | dev |
| hasown | 2.0.4 | MIT | transitive | dev |
| ignore | 7.0.5 | MIT | transitive | dev |
| ignore | 5.3.2 | MIT | transitive | dev |
| import-fresh | 3.3.1 | MIT | transitive | dev |
| imurmurhash | 0.1.4 | MIT | transitive | dev |
| is-binary-path | 2.1.0 | MIT | transitive | dev |
| is-core-module | 2.16.2 | MIT | transitive | dev |
| is-extglob | 2.1.1 | MIT | transitive | dev |
| is-glob | 4.0.3 | MIT | transitive | dev |
| is-number | 7.0.0 | MIT | transitive | dev |
| isexe | 2.0.0 | ISC | transitive | dev |
| jiti | 1.21.7 | MIT | transitive | dev |
| js-yaml | 4.2.0 | MIT | transitive | dev |
| jsesc | 3.1.0 | MIT | transitive | dev |
| json-buffer | 3.0.1 | MIT | transitive | dev |
| json-schema-traverse | 0.4.1 | MIT | transitive | dev |
| json-stable-stringify-without-jsonify | 1.0.1 | MIT | transitive | dev |
| json5 | 2.2.3 | MIT | transitive | dev |
| keyv | 4.5.4 | MIT | transitive | dev |
| levn | 0.4.1 | MIT | transitive | dev |
| lilconfig | 3.1.3 | MIT | transitive | dev |
| lines-and-columns | 1.2.4 | MIT | transitive | dev |
| locate-path | 6.0.0 | MIT | transitive | dev |
| lodash.merge | 4.6.2 | MIT | transitive | dev |
| lru-cache | 5.1.1 | ISC | transitive | dev |
| merge2 | 1.4.1 | MIT | transitive | dev |
| micromatch | 4.0.8 | MIT | transitive | dev |
| minimatch | 10.2.5 | BlueOak-1.0.0 | transitive | dev |
| minimatch | 3.1.5 | ISC | transitive | dev |
| ms | 2.1.3 | MIT | transitive | dev |
| mz | 2.7.0 | MIT | transitive | dev |
| nanoid | 3.3.12 | MIT | transitive | dev |
| natural-compare | 1.4.0 | MIT | transitive | dev |
| node-releases | 2.0.46 | MIT | transitive | dev |
| normalize-path | 3.0.0 | MIT | transitive | dev |
| object-assign | 4.1.1 | MIT | transitive | dev |
| object-hash | 3.0.0 | MIT | transitive | dev |
| optionator | 0.9.4 | MIT | transitive | dev |
| p-limit | 3.1.0 | MIT | transitive | dev |
| p-locate | 5.0.0 | MIT | transitive | dev |
| parent-module | 1.0.1 | MIT | transitive | dev |
| path-exists | 4.0.0 | MIT | transitive | dev |
| path-key | 3.1.1 | MIT | transitive | dev |
| path-parse | 1.0.7 | MIT | transitive | dev |
| picocolors | 1.1.1 | ISC | transitive | dev |
| picomatch | 4.0.4 | MIT | transitive | dev |
| picomatch | 2.3.2 | MIT | transitive | dev |
| pify | 2.3.0 | MIT | transitive | dev |
| pirates | 4.0.7 | MIT | transitive | dev |
| postcss-import | 15.1.0 | MIT | transitive | dev |
| postcss-js | 4.1.0 | MIT | transitive | dev |
| postcss-load-config | 6.0.1 | MIT | transitive | dev |
| postcss-nested | 6.2.0 | MIT | transitive | dev |
| postcss-selector-parser | 6.1.2 | MIT | transitive | dev |
| postcss-value-parser | 4.2.0 | MIT | transitive | dev |
| prelude-ls | 1.2.1 | MIT | transitive | dev |
| punycode | 2.3.1 | MIT | transitive | dev |
| queue-microtask | 1.2.3 | MIT | transitive | dev |
| react-refresh | 0.17.0 | MIT | transitive | dev |
| read-cache | 1.0.0 | MIT | transitive | dev |
| readdirp | 3.6.0 | MIT | transitive | dev |
| resolve | 1.22.12 | MIT | transitive | dev |
| resolve-from | 4.0.0 | MIT | transitive | dev |
| reusify | 1.1.0 | MIT | transitive | dev |
| rollup | 4.61.0 | MIT | transitive | dev |
| run-parallel | 1.2.0 | MIT | transitive | dev |
| semver | 7.8.1 | ISC | transitive | dev |
| semver | 6.3.1 | ISC | transitive | dev |
| shebang-command | 2.0.0 | MIT | transitive | dev |
| shebang-regex | 3.0.0 | MIT | transitive | dev |
| source-map-js | 1.2.1 | BSD-3-Clause | transitive | dev |
| strip-json-comments | 3.1.1 | MIT | transitive | dev |
| sucrase | 3.35.1 | MIT | transitive | dev |
| supports-color | 7.2.0 | MIT | transitive | dev |
| supports-preserve-symlinks-flag | 1.0.0 | MIT | transitive | dev |
| thenify | 3.3.1 | MIT | transitive | dev |
| thenify-all | 1.6.0 | MIT | transitive | dev |
| tinyglobby | 0.2.17 | MIT | transitive | dev |
| to-regex-range | 5.0.1 | MIT | transitive | dev |
| ts-api-utils | 2.5.0 | MIT | transitive | dev |
| ts-interface-checker | 0.1.13 | Apache-2.0 | transitive | dev |
| type-check | 0.4.0 | MIT | transitive | dev |
| update-browserslist-db | 1.2.3 | MIT | transitive | dev |
| uri-js | 4.4.1 | BSD-2-Clause | transitive | dev |
| util-deprecate | 1.0.2 | MIT | transitive | dev |
| which | 2.0.2 | ISC | transitive | dev |
| word-wrap | 1.2.5 | MIT | transitive | dev |
| yallist | 3.1.1 | ISC | transitive | dev |
| yocto-queue | 0.1.0 | MIT | transitive | dev |

### 2.3 Root / e2e npm (`package.json`, Playwright)

| Package | Version | Licence | Direct / transitive | Runtime / dev |
|---|---|---|---|---|
| @playwright/test | 1.60.0 | Apache-2.0 | direct | dev |
| playwright | 1.60.0 | Apache-2.0 | transitive | dev |
| playwright-core | 1.60.0 | Apache-2.0 | transitive | dev |

## 3. Compatibility with GPL-3.0 for distribution

### 3.1 Linked / bundled code: compatible

- **MIT, BSD-2/3-Clause, ISC, 0BSD, Zlib, CC0-1.0, Unlicense, MIT-CMU (HPND-style), BlueOak-1.0.0, PSF-2.0 / Python-2.0.** These are permissive and compatible with GPLv3. BlueOak (npm `minimatch` 10.x) is dev/build-only.
- **Apache-2.0.** Compatible with GPLv3. It is not compatible with GPLv2-only, but that does not apply here because the project is GPL-3.0.
- **MPL-2.0** (`certifi`, `orjson`, `tqdm`). Compatible. MPL-2.0 section 3.3 permits combination with GPL code, and these packages do not opt out through an "Incompatible With Secondary Licenses" notice (checked from memory, not metadata). MPL file-level obligations still apply to the MPL files themselves.
- **Dual / choice expressions** (`cryptography` Apache-2.0 OR BSD-3-Clause, `packaging`, `ormsgpack`, `sniffio`). Pick the permissive option.
- **CC-BY-4.0** (npm `caniuse-lite`, browser-support data). From memory, the FSF regards CC BY 4.0 as GPLv3-compatible. Either way it is a dev/build-time dependency of browserslist/autoprefixer and is not shipped in the frontend bundle.
- **No GPL-2.0-only, AGPL, SSPL, BUSL, Elastic or Commons Clause licence** appears in any linked Python or npm dependency.

### 3.2 Items needing review (linked code)

| Package | Licence (metadata) | Scope | Issue |
|---|---|---|---|
| `nvidia-cublas`, `nvidia-cuda-nvrtc`, `nvidia-cudnn-cu13`, `nvidia-cusparselt-cu13`, `nvidia-nccl-cu13`, `nvidia-nvshmem-cu13`, `cuda-bindings` | LicenseRef-NVIDIA-Proprietary / NVIDIA software licence | runtime, transitive via `sentence-transformers` → `torch` (PyPI CUDA build) | **Proprietary, GPL-incompatible if distributed together with the program.** They are present in the local dev venv only. `backend/Dockerfile` installs torch from `https://download.pytorch.org/whl/cpu` (`--extra-index-url`), which avoids these wheels. From memory: pip should prefer the `+cpu` local-version wheel, but this was not verified inside a built image. Check with `pip list` in the image. |
| `cuda-toolkit` 13.0.2 | none | runtime, transitive via `torch` | No licence metadata. From memory, this is an NVIDIA metapackage under the NVIDIA CUDA EULA (proprietary). Same treatment as the row above. |
| `regex` 2026.5.9 | `Apache-2.0 AND CNRI-Python` | runtime, transitive (via `tiktoken` / `transformers`) | The FSF lists the standalone CNRI Python licence as GPL-incompatible because of its choice-of-law clause (from memory). The CNRI part covers code derived from CPython's `sre`. Low practical risk, since it is a separate unmodified Python module loaded at run time, but it is the one non-NVIDIA licence that needs review. |
| `triton` 3.7.0 | classifier only: MIT | runtime, transitive via `torch` | Licence comes only from the trove classifier (no `License` field). From memory it is MIT. Not on the Docker CPU path. |

### 3.3 Weak metadata, resolved from classifiers

These packages are listed with a licence in the tables, but the metadata has no SPDX expression and no usable `License` field, so the trove classifier was used:

- `annotated-types` (MIT)
- `fastapi` (MIT)
- `Jinja2` (BSD → BSD-3-Clause)
- `prompt_toolkit` (BSD → BSD-3-Clause)
- `safetensors` (Apache-2.0)
- `tokenizers` (Apache-2.0)
- `triton` (MIT)

In addition:

- `ptyprocess` has `License: UNKNOWN` and an ISC classifier.
- `scipy`, `traitlets` and `tiktoken` put the full licence text in the `License` field. Their classifiers say BSD, BSD and MIT respectively.
- `mpmath`, `sympy`, `wrapt` and `xxhash` declare an unversioned "BSD".

### 3.4 Docker images (image, not linked)

All of these images run as separate network services or as build stages. Story Engine code talks to them over sockets or HTTP and does not link them. Their licences therefore do not affect the GPL-3.0 status of Story Engine's own code. They matter only if you redistribute the images themselves, or if you modify and serve AGPL software. **All licence information in this table is from memory**, not from image metadata.

| Image (as written in compose / Dockerfile) | Used for | Licence (from memory) | Notes |
|---|---|---|---|
| `pgvector/pgvector:pg16` | app database | PostgreSQL Licence (PostgreSQL and the pgvector extension) | Permissive. Image, not linked. |
| `postgres:16-alpine` | Langfuse database | PostgreSQL Licence | Permissive. Image, not linked. |
| `redis:7.2.16-alpine` (twice: app cache/checkpoints and Langfuse queue; also CI) | cache / LangGraph checkpoints / Langfuse | Redis ≤ 7.2.x: BSD-3-Clause. **Redis 7.4+: dual RSALv2 / SSPLv1** (source-available, not OSI). Redis 8+ adds AGPLv3 as a third option. | **Pinned to 7.2.16 (BSD-3-Clause) on branch tech-debt.** Before that, the floating `7-alpine` tag resolved to 7.4.x, i.e. RSALv2/SSPL. Note 7.2 is end-of-life; Valkey is the BSD-licensed successor. Neither RSALv2 nor SSPL is GPL-compatible, but licence is GPL-compatible, but Redis is an unmodified network service and is not linked, so it does not block GPL distribution of this repo. The restrictions concern offering Redis itself as a managed service. To avoid the question entirely, pin `redis:7.2-alpine` (BSD, but 7.2 is end-of-life) or switch to `valkey/valkey` (BSD-3-Clause). The Python client `redis` (redis-py) 5.2.1 is MIT. |
| `clickhouse/clickhouse-server` (no tag → `latest`) | Langfuse analytics store | Apache-2.0 | Compatible. Unpinned tag. Image, not linked. |
| `quay.io/minio/minio` (no tag → `latest`) | Langfuse blob storage (S3-compatible) | **AGPL-3.0** | AGPL obligations (offering source to network users) arise only if MinIO itself is modified. It is used unmodified as a separate service, so it has no effect on Story Engine's licence. If the images are redistributed, MinIO's AGPL source offer must accompany them. Also from memory: in late 2025 MinIO stopped publishing community-edition binaries and images, so `latest` may be stale. Pin a tag. |
| `langfuse/langfuse:3`, `langfuse/langfuse-worker:3` | observability | MIT for the core. The repo also contains `ee/` directories under a separate commercial licence, which need a licence key to enable. | The self-hosted OSS feature set needs no key. Image, not linked. The Python SDK `langfuse` 4.7.1 is MIT (metadata). |
| `nginx:alpine` (`docker-compose.prod.yml`, frontend prod stage) | static frontend / reverse proxy | BSD-2-Clause (nginx). Alpine base packages carry mixed licences (musl MIT, BusyBox GPL-2.0). | Image, not linked. Distributing the image means meeting BusyBox's GPL-2.0 source obligations, which is standard for Alpine images. |
| `python:3.12-slim` (backend Dockerfile base) | backend runtime | PSF-2.0 (CPython). Debian base packages carry mixed licences, including GPL/LGPL. | The base image is not part of the source distribution. Image redistribution carries Debian's usual source obligations. |
| `node:20-alpine` (frontend dev/build stages) | build only | MIT (Node.js) plus Alpine packages | Build stage only. Not present in the prod image. |
| Docker Model Runner model `ai/gemma3:4B` (`models:` in `docker-compose.yml`, enabled by `docker-compose.gemma.yml`) | optional local LLM | **Gemma Terms of Use** plus the Gemma Prohibited Use Policy. Not an OSI or FSF licence, and it includes use restrictions. | Opt-in. Weights are pulled at runtime and are not distributed with the repo. Do not bundle the weights in a GPL distribution. |

The embedding model `sentence-transformers/all-MiniLM-L6-v2` (`backend/app/core/config.py`) is downloaded at runtime. From memory its licence is Apache-2.0. It is not distributed with the repo.

## 4. Blockers

**None** for distributing this repository's source under GPL-3.0, or for distributing the Docker images as they are currently built. The reasons:

1. Every Python and npm dependency on the shipped path (the CPU-torch Docker build and the Vite production bundle) is under a permissive, MPL-2.0 or PSF licence, all of which are GPL-3.0 compatible.
2. No GPL-2.0-only, AGPL, SSPL, BUSL, Commons Clause or Elastic licence appears in any linked dependency.
3. The AGPL and SSPL/RSALv2 components (MinIO, Redis 7.4+) are separate, unmodified network services pulled as images. They are not linked.

**Conditional blockers.** These become blockers if circumstances change:

- **NVIDIA CUDA wheels.** This covers the `nvidia-*` packages, `cuda-bindings` and `cuda-toolkit`. Distributing an artifact that bundles them (for example a frozen venv, a wheelhouse, or an image built with PyPI's default CUDA torch) would ship proprietary libraries alongside GPL-3.0 code, and whether the GPL's system-library exception covers them is disputed. Keep the CPU wheel index in `backend/Dockerfile`. Before any release, confirm that the built image's `torch` is the `+cpu` build.
- **Redis image licence.** If you redistribute the Redis image as part of a bundle, or offer Redis to third parties as a service, RSALv2/SSPL terms apply. Pin to a BSD release or switch to Valkey if that matters.
- **Gemma weights.** If you ever bundle them, the Gemma Terms of Use apply. They are not a free-software licence.

**Review item (not a blocker):** the `regex` package's CNRI-Python component (section 3.2).

## 5. Unknown

Packages with **no licence metadata at all** (no `License-Expression`, no `License` field, no licence classifier, or for npm no `license`/`licenses` field):

| Package | Version | Ecosystem | Scope | Notes |
|---|---|---|---|---|
| `cuda-toolkit` | 13.0.2 | Python | runtime, transitive (via `torch`, CUDA build only) | From memory: NVIDIA CUDA EULA (proprietary). Absent from the CPU Docker build. |

No npm package was missing a licence field. Packages whose licence could be identified only from a classifier or from full licence text are listed in section 3.3. They are not treated as unknown.
