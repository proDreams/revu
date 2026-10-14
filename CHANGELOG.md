# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
