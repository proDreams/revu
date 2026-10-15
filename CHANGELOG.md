# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.2] - 2026-10-15

### Fixed

- **The crash that restarted the container is gone, and it was a version.** The
  parser core was `tree-sitter` 0.26 while every grammar wheel here is built against
  0.25, and the mismatch showed up where the grammar's field tables are read: the tree
  walk touched node fields through a stale view of the language and, under memory
  pressure, the process died with SIGSEGV — `Error 139` in the container, which no
  Python `except` can catch and which arrives as a bare restart. Once the heap was
  poisoned on purpose it reproduced every time (`PYTHONMALLOC=malloc
  MALLOC_PERTURB_=165`): six crashes in six runs on 0.26.0, none in eight on 0.25.2,
  while plain parsing never crashed on either — which is what placed the fault in the
  walk and not in the grammar. The core is held below 0.26 until the wheels move, and
  `run_prod` sets `PYTHONFAULTHANDLER=1`, so a crash of any kind now leaves a Python
  stack in the container log instead of an exit code on its own.
- **A review of a large pull request is no longer cut off at thirty seconds.** The AI
  client shares this service's HTTP client, so `HTTP_CLIENT_TIMEOUT` — thirty seconds,
  which is right for a Git host and wrong for a model reading a whole diff — applied to
  the model as well, and the SDK's own retries spent three attempts of it before failing
  with `APITimeoutError` on a fifty-eight-file pull request. An AI profile now takes its
  own `AI_PROVIDER_TIMEOUT`, five minutes by default.
- **A model that fails to answer is asked again, visibly.** The SDK's own retries are
  silent and were capped at three attempts; an AI profile now says how many it wants
  (`AI_PROVIDER_RETRIES`, four retries — five attempts — by default), every attempt is
  logged with its reason, and the waits double with jitter, believing a `Retry-After`
  when the host sends one. Only failures that carried no verdict are repeated: a model
  that refused the answer is not asked five times for the same refusal. The SDK's own
  retries are switched off, so the configured count is the count that happens — the
  worst case is that count times `AI_PROVIDER_TIMEOUT`, which is why both are settings.
- **The probes around a changed file are fewer and quieter.** `deep` finds the tests and
  dependencies of a changed file by guessing paths and asking; for an icon, a font or an
  image that guess is a family of names that cannot exist, and one brand-kit pull request
  produced forty 404s for assets nobody reviews. A changed file that is data rather than
  code is skipped now — the diff still carries it — and a 404 on a probe is logged at
  debug level instead of as a warning, because for a probe a miss is an answer.

### Changed

- **The prompts are English now, and a third smaller.** Tokenizers spend noticeably more
  of them on Russian Cyrillic than on the same content in English, and the instructions
  travel with every review: 22 648 characters became 13 930, with the reviewer's criteria
  stated once instead of twice across the two modes. The *answer* is still Russian — that
  is what a person reads — and the rule saying so lives in the prompts themselves, with a
  test that fails if a later edit drops it. Rereading them also produced two things worth
  having: a review no longer spells out what the project's own linters and formatters
  already enforce (formatting, import order, line length), because the pipeline reports
  those and a review that repeats them is noise; and both modes now say plainly that a
  change which is fine needs no comment at all. What was worth keeping was kept — the
  diff handed to the model carries a line number on every line and the prompt tells it to
  copy those numbers rather than count, which is what keeps a comment on the line it was
  written about, and the data block stays fenced with an instruction to treat everything
  inside it as material rather than as orders.

- **A review says when it is waiting for the model.** The request line in the log arrives
  with the response *headers*, not with the answer — httpx logs before it reads the body —
  so a log can show a `200` in under a second and then look dead for minutes while the
  model is still generating. That is exactly how a fifty-eight file pull request read as
  stuck when nothing at all was wrong with it. The line before the call names the pull
  request, the connection, the mode and the size of the prompt, so the wait has a
  beginning and a number attached to it.

- **A model answer has a deadline now, not just a socket timeout.** `AI_PROVIDER_TIMEOUT`
  was handed to the HTTP client, whose read timeout measures the *gap* between two
  chunks — so a model that keeps generating never trips it, and a review of a
  nineteen-file pull request sat for minutes with its headers already in the log, looking
  answered. A second review in the same log finished in seventy-eight seconds, which is
  what a slow model looks like when it does finish. The whole request is now under that
  timeout, generation included: a model that will not stop is cut off and asked again,
  which also makes "the attempt count times the timeout" the real worst case rather than
  a number nothing enforced.

## [2.4.1] - 2026-10-15

### Fixed

- **The image builds again.** Three causes, in the order they surfaced. `uv sync
  --locked` ran in a layer holding only the metadata, and building the project needs
  its own source, so the install failed with `Expected a Python module at:
  src/revu/__init__.py`; the first sync now passes `--no-install-project` and the
  project is installed once its source has been copied in. The certificate step then
  failed the same way through `uv run`, which syncs — and therefore builds — before
  running `certifi`; it uses the environment's own interpreter now. And `uv` came from
  `ghcr.io/astral-sh/uv:latest`, so a new uv could change how this image builds
  without a line in the repository changing, which is exactly what had happened: the
  `uv_build` pin was written against an older uv. The image tag and the backend range
  are pinned together now.
- **A version tag is released, and only once.** The release workflow listened for
  `v*` while every tag in this repository is bare (`1.0.0` through `1.5.0`), so
  `git push origin 2.4.0` started nothing at all; and the release step rebuilt the tag
  name from the version, so pushing `2.4.0` would have released `v2.4.0`, creating it
  if it did not exist. Both spellings are accepted now, and the tag that was pushed is
  the one released. The image was also built twice — once by the push to `main`, once
  by the tag that followed — so `build.yaml` is now one workflow for both, and the tag
  path verifies the image the `main` push published instead of rebuilding it. Its lint
  step ran nothing either: `--hook-stage manual` selects hooks declaring that stage,
  and none here do.
- **Gitea's conversations are read through Gitea's own routes.**
  `GET /repos/{owner}/{repo}/pulls/{index}/comments` does not exist in Gitea's API —
  it is GitHub's route, inherited by sharing the GitHub-compatible comment reader —
  and it answers 404. The review survived that by running without the history, which
  is what made it quiet: a repeated review on Gitea never saw its own earlier inline
  findings, so the feature that makes a second review build on the first never worked
  there. The routes are a per-host hook now, and Gitea reads its issue timeline (an
  inline review comment is an issue comment carrying a `pull_request_url`) plus
  `/pulls/{index}/reviews` for the review bodies.

- **Deep context no longer drops a file without saying so.** The tree walk was
  recursive, and a generated tree is as deep as its source is nested: a call chain
  a thousand calls long exhausted the interpreter's stack, `parse` swallowed the
  `RecursionError` and returned an empty result — indistinguishable, at the call
  site, from a file with nothing in it. A file with 900 nested calls parsed to zero
  symbols before this; the walk is iterative now and the same file yields its
  function. Anything that still fails is logged with its traceback instead of
  disappearing.
- The walk also holds its `Parser` in a local until the walk is over. `Tree` keeps
  its language alive, so this is belt and braces rather than a fix — but a parser is
  cheap to keep and a use-after-free in a C extension cannot be caught.
- A wrapper definition (a decorator, a template) is asked through the same rule
  lookup as every other node, so `nested_inside_definition` and `requires_field` are
  no longer skipped for it.

### Changed

- A refusal by the Git host (401, 403, 404) logs what that host's own documentation
  requires of a token: Gitea's scope groups (`read:repository` for `/repos/*`,
  `write:issue` for `issues/*`, a scope required even for a public repository),
  GitHub's `repo`, GitLab's `api`. It goes to the log and not to the pull request —
  scopes are the operator's business, while the author only needs to know that the
  review failed.

## [2.4.0] - 2026-10-14

### Added

- **Reviews run in a pipeline, with nothing to deploy.** `revu review` is the same
  check with the same prompt, but without an inbound address, a permanent host or a
  bot account of its own: the code is already checked out, the event says which pull
  request it is, and the job already holds a token. GitHub Actions, GitLab CI and
  Gitea Actions are supported; the host, the repository, the pull request number and
  the revisions come from the platform's own variables, so a usual run takes no
  arguments at all.
    - Where the change comes from: the local checkout (the default), the host API, or
      a saved diff file. Reading locally spends no requests at all, and `deep` context
      is free in a pipeline: the files are on disk and the tree is one `git` command.
    - Where the answer goes: a comment in the pull request when a token allows it, the
      job log otherwise, or one JSON object with `--format json`.
    - `--fail-on never|error|findings` (`never` by default) decides what the job does
      about the result: a gate is a choice, not a default.
    - The flags are `--diff-source`, `--diff-file`, `--base`, `--head`, `--repo`,
      `--pr`, `--provider`, `--depth`, `--comment`/`--stdout`, `--format`, `--fail-on`
      and `--output`.
- A pipeline's configuration is built from the environment by the same parser that
  reads `settings.yaml`: the key names match, so do the checks and the error messages,
  and the settings file itself is not needed in CI.
- `revu serve` is the server under the same command; `app` and `docker-compose.yaml`
  keep working as before.
- `git` was added to the image (a local checkout is read with it) and the virtual
  environment to `PATH`, so `revu` works as a command.
- **A GitHub action** (`action.yml`) that checks the change out itself, with
  `fetch-depth: 0` — the setting whose absence means a review of an empty diff — and
  runs the image.
- **Findings can be shown without permission to write.** `--format
  github-annotations` prints the annotations GitHub places next to the changed lines,
  and `--format gitlab-codequality` writes the report the merge request widget reads.
  Neither creates a comment, so neither needs a token that may write: this is the
  answer to GitLab's read-only `CI_JOB_TOKEN`.
- `--output PATH` chooses where a report is written (`revu-codequality.json` by
  default).
- `NOTIFY_ON_FAILURE` works in a pipeline too: a review that could not be completed
  leaves a short comment naming the kind of error (a token that may write is
  required), with the details in the log.

### Changed

- `GitProviderProtocol` was split into `GitReaderProtocol` (diff, files, tree, earlier
  conversation) and `CommentPublisherProtocol` (comment, inline review). Host ports
  implement both, so the server is unaffected, while `ContextBuilder` now asks for the
  reading half only — the one it always used.
- The review itself moved into `ReviewRunner`, which takes its source and its
  destination as arguments and returns a `ReviewOutcome`. `ReviewService` is what
  makes a review a *webhook* review: it holds the connection's concurrency budget and
  turns an event into a request.
- In a pipeline the review no longer replaces the log with a comment but adds to it:
  the text is always in the job log and, when a token allows, also posted as a comment.
- ReVu's signature (`<!-- revu -->` and the inline badge) was removed from the places
  where it would be visible noise rather than invisible identification: GitHub
  annotations, the Code Quality report, and the list of findings in the log.

## [2.3.0] - 2026-10-14

### Added

- **`CONTEXT_DEPTH`**: `flat` (default) reviews the diff, `deep` also reads the
  surrounding code —
    - the full body of every symbol the changed lines fall into, instead of the
      three lines of context a unified diff carries;
    - the signatures (and docstrings) of the imported names the changed code
      actually mentions, so a contract is read rather than guessed;
    - the tests that cover the changed file, found by path and name.
- `CONTEXT_MAX_FILES` (12) and `CONTEXT_MAX_CHARS` (40 000), globally and per
  connection. They bound *additional* files and the total size of what is added;
  the diff is never trimmed, and a changed file is never dropped because of them.
- One line per review saying what the context cost: files and characters of the
  diff against entries and characters of the context, with a token estimate, the
  number of requests, whether a budget cut the gathering, and how long it took.
  This is what the budgets are meant to be tuned from.
- Code parsing through tree-sitter, with one grammar wheel per language (30 of
  them: Python, JavaScript, TypeScript, Go, Java, Kotlin, Ruby, Rust, C#, PHP, C,
  C++, Swift, Scala, Elixir, Lua, Perl, Dart, Bash, SQL, HTML, CSS, HCL, YAML,
  JSON, Make, Zig, Haskell, OCaml, Dockerfile). The aggregated
  `tree-sitter-language-pack` was rejected on purpose: it downloads grammars at
  runtime into a cache directory, so it breaks in a closed network and makes the
  container write state.
- A language with no grammar still gets deep context: the changed file is included
  whole. Precision needs a grammar; having context at all does not.

### Changed

- The prompt of both review modes gained a section for the surrounding code, inside
  the same guarded data block as the diff, and states that inline comments may only
  target lines from the diff — code that this pull request did not change is
  background, not review material.
- `HttpGatewayError` now carries the HTTP status code, so "this file is not there"
  can be told from "the host refused us" without parsing a message.

### Security

- Paths that must never reach an AI provider are skipped before any request:
  `.env*`, keys, credential and secret files, and generated or vendored trees
  (`node_modules/`, `vendor/`, `dist/`, `build/`), minified bundles and lock files.
  Files past 200 000 characters are ignored.
- Deep context is gathered at the revision of the pull request only, and any
  failure degrades to a flat review with the reason in the log.

## [2.2.0] - 2026-10-14

### Added

- **A repeated review now builds on the first one.** Before reviewing, ReVu reads
  the comments the pull request already carries — its own findings and the
  discussion around them — and a follow-up prompt works from them instead of
  starting over:
    - findings that were addressed are not raised again;
    - findings that still hold are not posted as duplicate inline comments, they
      are reported in the summary;
    - inline comments are added only for problems in the new changes.
- The summary of a re-review opens with the progress
  (`📊 Из прошлых замечаний исправлено: 3 из 5. Осталось: 2.`). The total is
  ReVu's own count of earlier findings, so a model that reports fewer of them
  cannot shrink it, and a model that reports none gets no line at all rather than
  a claim of zero fixes.
- **ReVu signs the comments it publishes.** Authorship could never answer "is this
  an earlier review of mine?": ReVu normally runs on the repository owner's token,
  so the bot and the person are the same account, and every comment they wrote
  looked like a previous finding. That made a first review take the follow-up
  prompt and report nonsense progress. Each published comment now ends with an
  invisible marker (a trailing HTML comment, which the hosts' CommonMark rendering
  hides and their APIs return verbatim), and only that marker decides what ReVu
  considers its own.
- A visible header on the summary — `🤖 ReVu`, or `🤖 ReVu · повторное ревью` —
  and a `🤖 ReVu:` prefix on every inline comment, so a reader can tell who wrote
  what even when both run under one account.
- `INCLUDE_PR_DISCUSSION` (default `true`, overridable per connection) decides
  whether other people's comments are sent to the AI provider as context. ReVu's
  own findings are always included, because they are the model's own earlier
  output rather than new data leaving the network.
- Each port reads the history the way its host exposes it: GitHub and Gitea read
  the timeline, the inline comments and the review bodies (where an inline summary
  goes); GitLab reads the notes, skipping system ones and keeping the resolution
  state; Bitbucket Data Center reads the comments with their anchors and flattens
  the replies.

### Changed

- The output schema of both review modes now carries `previous_findings`, empty
  on a first review. A provider answer that omits it is treated as "nothing
  reported" instead of as "nothing was fixed".
- ReVu no longer asks the host who the token belongs to (`/user` on GitHub, Gitea
  and GitLab, the reviewer name or `permittedOperations.canEdit` on Bitbucket):
  the signature answers that question, so a review makes fewer requests and cannot
  be misled by a shared account.
- A comment without the signature is not ReVu's, so a pull request reviewed by an
  older release is simply reviewed from the diff.
- A pull request without a description no longer reaches the model as the literal
  `None`.

## [2.1.0] - 2026-10-14

### Added

- **GitLab** as a git provider, including self-managed instances. Add a
  connection with `GIT_PROVIDER: "gitlab"` and point the webhook at
  `/webhooks/<key>`; `GIT_PROVIDER_URL` is optional and defaults to gitlab.com.
  Inline reviews are published as merge request discussions, positioned with the
  three commit SHAs GitLab requires.
- GitLab webhook authentication, both ways GitLab offers it: the signing token of
  GitLab 19.0 and later (Standard Webhooks: HMAC-SHA256 over
  `id.timestamp.body`, sent in `webhook-signature`), and the legacy plain
  `X-Gitlab-Token` that earlier versions send. The signature is preferred when
  present, because the legacy token does not authenticate the body.
- GitLab deliveries whose merge request revision was already reviewed are
  acknowledged without a second review. GitLab sends the `update` action for a
  renamed title or a new label as well as for a push and has no field that
  separates them ([gitlab-org/gitlab#10824](https://gitlab.com/gitlab-org/gitlab/-/work_items/10824)),
  so the head commit decides. The memory is bounded and evicts the least
  recently used entry, which costs at most one redundant review.

### Changed

- The event header check ignores case, because GitLab spells its event
  `Merge Request Hook`.

### Documentation

- The README covers GitLab, the per-connection review settings, the failure
  notice and the logging options, and gained a development section with the
  commands for tests and the type check that sees the project dependencies.
- `make test` runs the suite with its coverage gate.

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

- Inline comments are checked against the diff before they are published. A host
  rejects the whole review request when one anchor is not in the diff, which used
  to lose every other comment and the summary with it; comments that point
  outside the diff are now dropped and counted in the log.
- `NOTIFY_ON_FAILURE` (default `true`, overridable per connection) publishes a
  short comment on the pull request when a review fails. Only the error type
  reaches the pull request; the message and traceback stay in the log.
- Every log record carries the connection key, so a review that runs in a
  background task can be traced even when several connections are active.
- `uv run mypy src` (also `make typecheck`) type-checks against the project
  dependencies. The pre-commit hook runs mypy without them, so it cannot see
  errors at the fastapi/pydantic/openai boundary.
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
  still never requires a settings file to exist, and it creates the log file on
  the first record instead of on the first `get_logger()` call.
- `WebhookService` became `ReviewService` (with its module, exceptions and DI
  provider) now that it serves every connection rather than one webhook; the
  exception and review-mode modules were renamed to match.

[2.4.2]: https://github.com/proDreams/revu/compare/2.4.1...2.4.2
[2.4.1]: https://github.com/proDreams/revu/compare/2.4.0...2.4.1
[2.4.0]: https://github.com/proDreams/revu/compare/2.3.0...2.4.0
[2.3.0]: https://github.com/proDreams/revu/compare/2.2.0...2.3.0
[2.2.0]: https://github.com/proDreams/revu/compare/2.1.0...2.2.0
[2.1.0]: https://github.com/proDreams/revu/compare/2.0.0...2.1.0
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

- YandexGPT reviews crashed with `TypeError: object AsyncGPTModel can't be used
  in 'await' expression`: creating the model is synchronous in that SDK, only
  `run` is awaited. The unit test mocked the whole client, which made the call
  look awaitable and hid it.
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
