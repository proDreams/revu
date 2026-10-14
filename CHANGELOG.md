# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2026-10-14

### Breaking changes

- **One instance now serves many git providers.** The configuration moved from a
  single `GIT_PROVIDER_CONFIG` / `AI_PROVIDER_CONFIG` pair to a map of git
  connections (`GIT_PROVIDERS`) and named AI profiles (`AI_PROVIDERS`) with a
  `DEFAULT_AI_PROVIDER`. A 1.x settings file is rejected at startup with a
  message explaining what moved; see the migration table in `README.md`.
- **Webhook URLs changed.** `POST /webhooks/github`, `/webhooks/gitea` and
  `/webhooks/bitbucket` are gone. Each connection now has its own URL,
  `POST /webhooks/<connection_key>`, where the host type comes from the
  connection configuration. Update the webhook URL on the git host side.
- **`GIT_PROVIDER_URL` is required for Gitea and Bitbucket** and optional for
  GitHub (omit it for github.com, or point it at a GitHub Enterprise Server REST
  root including `/api/v3`). `AI_PROVIDER_BASE_URL` is required for
  `openai_compatible` and `AI_PROVIDER_FOLDER_ID` for `yandexgpt`.
- **AI providers are addressed by profile name.** A connection naming an unknown
  profile stops startup instead of silently falling back to the default model.
- The `/webhooks` routes no longer accept a payload whose host does not match the
  configured `GIT_PROVIDER`: it answers `422` and logs which connection to check.
  Previously such a delivery was often acknowledged as "review not needed".

### Added

- `DEFAULT_AI_PROVIDER` plus an optional per-connection `AI_PROVIDER` override:
  several git connections may share one AI profile, and one of them may use
  another model.
- Per-connection `REVIEW_MODE`, `SYSTEM_PROMPT` and `MAX_CONCURRENT_REVIEWS`,
  each falling back to the global value.
- Per-connection review budgets: a burst of pushes to one repository can no
  longer occupy the review slots of every other connection.
- A startup summary of the configured connections and the default AI profile, so
  a typo in a connection key is visible in the log (`GET /health` still says
  nothing about the configuration).
- GitHub Enterprise Server support through `GIT_PROVIDER_URL`.
- A typed configuration model: every consumer receives frozen dataclasses instead
  of reading a global settings object, and validation errors name the offending
  key (`GIT_PROVIDERS.gitea-int.GIT_PROVIDER_URL is required and must not be
  empty`).
- A warning when two connections share the same host and base URL, which would
  review a repository twice.

### Changed

- `AIProviderProtocol` takes a `ReviewTask` (`diff`, `git_host`, `pr_title`,
  `pr_body`, `system_prompt`) instead of loose arguments. AI ports no longer hold
  the system prompt, which is what allows one profile to serve connections with
  different prompts.
- `GitProviderProtocol`, `ReviewResponseDTO.from_request` and the git ports now
  speak of `git_host` rather than `git_provider`, matching what the value is.
- Infrastructure no longer calls `get_settings()`: 24 call sites across 15 files
  were replaced by constructor injection.
- YandexGPT now fails at startup when `AI_PROVIDER_FOLDER_ID` is missing instead
  of failing on the first review.
- The logger reads only the logging keys, so importing the configuration module
  still never requires a settings file to exist.

[2.0.0]: https://github.com/proDreams/revu/compare/1.7.0...2.0.0

## [1.7.0] - 2026-10-14

### Breaking changes

- **The configuration is now validated at startup.** A missing or misspelled
  `REVIEW_MODE`, an unknown `GIT_PROVIDER`/`AI_PROVIDER`, a missing provider
  token or an **empty** `GIT_PROVIDER_SECRET_TOKEN` stop the application with a
  clear error instead of failing on the first webhook. `GIT_PROVIDER_URL` is
  required for Gitea and Bitbucket, and optional for GitHub.
- **Bitbucket reviews now trigger on the events that change code.**
  `pr:opened` and `pr:from_ref_updated` (commits pushed to the pull request
  source branch) start a review. `pr:modified` only announces metadata changes
  and no longer triggers one. Previously new commits were never reviewed while
  editing a title was.
- **GitHub inline comments are anchored with `line` + `side`.** `position` is
  deprecated by GitHub and is an offset inside the diff rather than a file line
  number, so comments could be rejected or land on the wrong line for any hunk
  that does not start at line 1. `SYSTEM_PROMPT` overrides that change the
  output format may need an update.

### Fixed

- `REVIEW_MODE=comment` with `AI_PROVIDER=openai` failed with
  `TypeError: Unsupported response_format type - None`. The adapter passed
  `text_format=None`, which the SDK treats as a given value; it is now omitted
  and comment mode reads `output_text` instead of the (always empty)
  `output_parsed`.
- A model refusal left `parsed`/`output_parsed` empty and surfaced as an
  `AttributeError` inside a background task. It is now reported as
  `InvalidAIOutput`/`NoAIResponse`.
- GigaChat and YandexGPT answers are validated against the same schema as the
  structured-output providers. Valid JSON with the wrong shape used to escape as
  a `KeyError` (or reach the git host with an invalid `lineType`).
- The GitHub webhook signature check rejected deliveries whose matching
  signature arrived in a second header (Gitea sends both `X-Gitea-Signature`
  and `X-Hub-Signature-256`).
- Bitbucket file diffs that the server paginates are no longer truncated to the
  first page, and a malformed diff response no longer raises `KeyError`.
- Bitbucket inline comments were mapped from the pull request **target** branch
  (`toRef`) instead of the reviewed source branch (`fromRef`).
- The Bitbucket prompt's JSON example was invalid (a missing comma) and its
  anchoring rule gave no coordinate for removed or context lines; for GigaChat
  and YandexGPT the prompt is the only output schema.
- Review comments could be published several times: the HTTP gateway retried
  every failure, including `4xx` and read timeouts on the comment `POST`. Retries
  are now limited to requests that cannot duplicate a side effect, with
  exponential backoff and support for `Retry-After`.
- The HTTP gateway returned raw `bytes` where `GitProviderProtocol` promises a
  `str`; decoding now happens in the git ports.
- GigaChat's SDK client was never closed; it is now closed when the DI container
  shuts down.
- The `application.base.exception` module and the unused `gitverse_to_domain`
  mapper were removed; `UnknownGitProviderException` now derives from the shared
  `CoreException` base, so a single handler covers domain and application errors.

### Added

- `MAX_CONCURRENT_REVIEWS` bounds how many reviews run at once; further webhooks
  wait for a free slot instead of starting unlimited concurrent AI requests.
- `GET /health` liveness endpoint, a `HEALTHCHECK` in the `Dockerfile` and in
  both compose files.
- `APP_HOST`/`APP_PORT` make the listening address configurable.
- `HTTP_CLIENT_RETRY_BACKOFF` tunes the retry backoff.
- GitHub Enterprise Server support through `GIT_PROVIDER_URL`, which may now
  point at a self-hosted REST root such as `https://ghe.example.com/api/v3`.
- The diff is delimited as untrusted data in the review prompt.
- Boundary tests that drive the real `openai` client through `httpx.MockTransport`,
  asserting on the actual request body. The previous unit tests mocked the
  adapter, which is why `text_format=None` shipped broken.

### Changed

- `make run_prod` uses `uv run --frozen --no-sync`: the environment baked into
  the image is reused instead of re-resolving dependencies (and needing the
  network) on every container start.
- The `Dockerfile` declares `CMD` and `EXPOSE`, so `docker run <image>` works
  without an explicit command.
- `SYSTEM_PROMPT` handling trims whitespace; a whitespace-only value is ignored.
- Test and example configuration use nested plain mappings, matching what
  Dynaconf builds from the YAML settings file.

### Removed

- The GitVerse endpoint (`POST /webhooks/gitverse`), its payload schema, its
  authorization validator and its tests. The integration only ever answered
  `501 Not Implemented`, because the forge exposes no usable API.
- The `.gitverse/` CI mirror.

[1.7.0]: https://github.com/proDreams/revu/compare/1.6.0...1.7.0

## [1.6.0] - 2026-10-14

### Breaking changes

- **Bitbucket webhooks now require a signature.** Requests are rejected with `403`
  unless they carry a valid `X-Hub-Signature-256`, `X-Gitea-Signature` or `X-Hub-Signature`
  header (HMAC-SHA256 of the raw body as `sha256=<hex>`) matching `GIT_PROVIDER_SECRET_TOKEN`.
  This needs Bitbucket Data Center 8.9+ and a filled-in **Secret** field on the webhook.
- **`SYSTEM_PROMPT` now extends the built-in review prompt instead of replacing it.**
  The response format contract is therefore always preserved. If you relied on a full
  replacement, check the resulting prompt after upgrading.

### Added

- Webhook processing is now driven by a DI container built with
  [Dishka](https://dishka-api.dev), assembled when the application starts.
- The application validates its configuration at startup and fails fast, instead of
  failing on the first incoming webhook.
- Gitea's `synchronized` pull request action now triggers a review; previously only
  GitHub's `synchronize` was recognised.
- Deliveries ReVu does not act on — non pull request events such as `push`, or actions
  such as `closed` — are acknowledged with `200` instead of failing with `422`/`500`.

### Changed

- Invalid webhook payloads now return `422 Unprocessable Content` instead of `500`.
- The GitVerse endpoint responds with `501 Not Implemented` instead of crashing with an
  unhandled `NotImplementedError`.
- The background review task logs failures instead of letting them propagate into the worker.

### Fixed

- Bitbucket inline comments were anchored to the **pull request number** instead of the
  commented line; they now land on the correct line.
- An `httpx.AsyncClient` was created and never closed, leaking connections on every run.
  The shared HTTP client is now closed on shutdown.
- Bitbucket payloads missing `eventKey` or `reviewers` crashed with `KeyError`.
- GitVerse token comparison was not constant-time; it now uses `hmac.compare_digest`.
- The `validators` module imported from `routes`, creating a circular import.
- `config/settings.yaml` contains secrets and could be baked into the Docker image;
  it is now excluded by `.dockerignore`.

[1.6.0]: https://github.com/proDreams/revu/compare/1.5.0...1.6.0
