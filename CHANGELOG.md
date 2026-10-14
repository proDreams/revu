# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
