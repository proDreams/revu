# Napkin Tools: ReVu

**English** · [Русский](README.md) — the main README, and the one that is kept up to date first

> 🤖 Self-hosted AI code review for your Pull Requests.

![GitHub License](https://img.shields.io/github/license/proDreams/revu)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/proDreams/revu/lint.yaml)
[![Website](https://img.shields.io/badge/Website-napkincode.ru-blue)](https://napkincode.ru)
[![Код на салфетке](https://img.shields.io/badge/Telegram-Код_на_салфетке-blue)](https://t.me/napkincode)
[![Заметки на салфетке](https://img.shields.io/badge/Telegram-Заметки_на_салфетке-blue)](https://t.me/writeanynotes)
[![Кот на салфетке](https://img.shields.io/badge/Telegram-Кот_на_салфетке-blue)](https://t.me/+Li2vbxfWo0Q4ZDk6)

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/images/logo-dark.png">
    <img src=".github/images/logo.png" width="560" alt="ReVu">
  </picture>
</p>

---

## Table of contents

1. [About](#about)
2. [Key features](#key-features)
3. [Built with](#built-with)
4. [ToDo](#todo)
5. [Requirements](#requirements)
6. [Quick start](#quick-start)
   - [Several Git providers on one instance](#several-git-providers-on-one-instance)
   - [Repeated reviews](#repeated-reviews)
   - [Context depth](#context-depth)
   - [Migrating from 1.x to 2.0](#migrating-from-1x-to-20)
   - [Updating](#updating)
7. [Reviews in a pipeline](#reviews-in-a-pipeline)
8. [Development](#development)
9. [Author](#author)
10. [Support](#support)
11. [License](#license)

---

## About

ReVu is AI code review for pull requests: a self-hosted webhook service, or a command in
your pipeline. As a server it receives webhooks from Git providers (GitHub, Gitea, GitLab
and Bitbucket) and publishes its review right in the pull request; in a pipeline it does
the same thing where the repository is already checked out — with no inbound address, no
permanent host and no separate bot account.

One instance serves any number of connections: repositories on GitHub, on a corporate
GitLab and on Gitea can be reviewed at the same time, sharing one AI provider or using a
separate profile each.

> **The idea** — take load off the team and raise the quality of the code. Before a
> colleague picks the pull request up, AI has already looked at it and pointed out the
> likely problems.
> ReVu is not a third-party service: it is a self-hosted tool you run yourself.

> **A note on language:** ReVu's review comments are written in Russian, because its
> prompts are Russian. Everything around them — this README, the code, the comments in
> it and the commit messages — is English.

---

## Key features

* **Two ways to run it**
    * **Server** — a webhook from your Git provider, a permanent instance, a separate
      account for the bot.
    * **Pipeline** — `revu review` in GitHub Actions, GitLab CI or Gitea Actions: the same
      image, the same prompt, the same result, without an inbound address or a host. See
      [Reviews in a pipeline](#reviews-in-a-pipeline).
* **Two review modes**
    * **Comment (`comment`)** — one detailed review of the whole pull request.
    * **Inline (`inline`)** — comments attached to the exact lines that changed.
* **A repeated review remembers the previous one**
    * New commits are reviewed with what ReVu already said taken into account: findings
      that were addressed are not raised again and findings that still hold are not
      duplicated as comments but reported in the summary. Details are in
      [Repeated reviews](#repeated-reviews).
    * A first review and a follow-up use different prompts.
* **Manageable context depth**
    * `flat` (the default) — a review of the diff and the pull request discussion.
    * `deep` — the model also sees the repository's structure, the full body of every changed function, the signatures
      of what that code calls, and the tests next to it. Fewer invented findings and fewer
      "you did not handle case X" remarks about a case handled twenty lines below.
    * The context budgets are configurable, and every review logs what it cost: how many
      files and symbols the diff held, how much the context added, and roughly what that
      means in tokens.
* **A review that does not get lost**
    * Comments are checked against the diff before they are published: a line that the
      change does not contain no longer costs the whole review. One invented line number
      used to be able to do exactly that.
    * If a review could not be completed, ReVu says so in the pull request
      (`NOTIFY_ON_FAILURE`) instead of staying silent: a service that wrote nothing looks
      like a service that checked everything. The details stay in the logs.
* **Several providers on one instance**
    * One container serves any number of Git connections — GitHub, Gitea, GitLab and
      Bitbucket in any combination.
    * Every connection has its own webhook, its own token and its own secret.
    * One AI provider by default, overridable per connection.
* **Flexible integration**
    * **GitHub**, **Gitea**, **GitLab** (self-managed included) and **Bitbucket**.
    * **OpenAI API** and its alternatives (OpenRouter, LocalAI, LM Studio and others), plus
      **GigaChat** and **YandexGPT**.
    * Named AI profiles: different models for different repositories, without a second
      container.
* **Fully self-hosted**
    * Runs on your own servers, with no data handed to a third party.
    * Local models (DeepSeek, Qwen and the like) work too, running elsewhere in your
      infrastructure.
* **Straightforward configuration**
    * One YAML file; the full reference is `config/settings.yaml.example_full`.
    * A configuration mistake stops the start-up and names the offending key, instead of
      turning every webhook into a silent failure.
    * Timeouts, retry counts and exponential backoff are configurable, and only requests
      that cannot be duplicated are ever repeated.
    * The concurrency limit is counted per connection, so a noisy repository cannot block
      the others.
* **Observability**
    * Logs go to the console and to a rotating file, and every line names the connection it
      belongs to.

---

## Built with

* **Python 3.13+** and **FastAPI** — the API and the webhook handler
* **HTTPX** — one HTTP client for Git and AI providers: timeouts, retries and backoff in
  one place
* **OpenAI SDK**, **GigaChat SDK**, **Yandex AI Studio SDK** — integration with LLMs
* **Dishka** — dependency injection; configuration and clients are assembled in one place
* **Dynaconf** + **pydantic** — configuration and webhook validation
* **unidiff** — parsing diffs and preparing them for inline comments
* **Docker** — for a deployment that is one command

---

## ToDo

- [x] Git providers:
    - [x] GitHub
    - [x] Gitea
    - [x] GitLab (self-managed included)
    - [x] Bitbucket (thanks to [lanity_roshoose](https://gitverse.ru/lanity_roshoose))
- [ ] More AI providers:
    - [ ] Gemini
    - [ ] DeepSeek
    - [ ] Anthropic
    - [ ] Qwen
    - [x] GigaChat
    - [x] YandexGPT
- [x] Custom review prompts (through `SYSTEM_PROMPT`)
- [x] Detailed documentation of configuration and deployment
- [x] English README
- [x] Test coverage — 100%
- [ ] More documentation and docstrings throughout the code
- [ ] Replay protection for GitLab webhooks via `webhook-timestamp`
- [ ] Inline comments verified against real pull requests on every supported provider

---

## Requirements

To run ReVu you need:

- **Docker and Docker Compose** — ReVu ships as a ready image, so no local Python is
  required.

- **A domain name with a valid SSL certificate**
    - Required for public services (GitHub, GitLab.com): they deliver webhooks only to an
      HTTPS address reachable from the outside, with a valid certificate.
    - If your Git server and ReVu share a Docker network, neither a public address nor SSL
      is needed.

- **A personal access token (PAT) from your Git provider**
    - GitHub — a **PAT Classic** with `repo` scope.
    - Gitea — a token with access to the repository and its pull requests.
    - GitLab — a token with the `api` scope: it is needed both to read the diff and to
      publish comments.
    - Bitbucket — a token that may read pull requests and publish comments.

- **An API key from an AI provider**
    - **OpenAI** or a compatible service (OpenRouter, LocalAI, LM Studio), **GigaChat** or
      **YandexGPT**.

---

## Quick start

A few steps are enough to get going:

1. Connect to your server over SSH and create a directory for the project:
    ```bash
    mkdir revu && cd revu
    ```
2. Download the configuration file and fill it in:
    1. Download the file — the short one, or the full one with a comment on every setting:
        - Short:
          ```bash
          wget -O settings.yaml https://raw.githubusercontent.com/proDreams/revu/refs/heads/main/config/settings.yaml.example
          ```
        - Full:
          ```bash
          wget -O settings.yaml https://raw.githubusercontent.com/proDreams/revu/refs/heads/main/config/settings.yaml.example_full
          ```
    2. Open it for editing:
       ```bash
       nano settings.yaml
       ```
    3. Fill in the following:
        - `REVIEW_MODE` — the default review format:
            - `"comment"` — one long comment on the pull request
            - `"inline"` — comments on the exact places in the code
        - `DEFAULT_AI_PROVIDER` — the name of the profile in `AI_PROVIDERS` used by every
          Git connection that does not name one of its own.
        - `AI_PROVIDERS` — named AI settings. One profile can serve several Git
          connections. For each profile:
            - `AI_PROVIDER` — the AI provider to use:
                - `"openai"` — the official OpenAI API
                - `"openai_compatible"` — an OpenAI-compatible provider
                - `"gigachat"` — GigaChat
                - `"yandexgpt"` — YandexGPT
            - `AI_PROVIDER_API_KEY` — the provider's API key
            - `AI_PROVIDER_MODEL` — the model to use (for example `gpt-4o-mini`)
            - `AI_PROVIDER_TIMEOUT` — how long the WHOLE request to the model may take, generation included, in seconds (`300` by default; the Git hosts' timeout does not apply to the model, and httpx's would not do — it measures the gaps between chunks, not the total)
            - `AI_PROVIDER_RETRIES` — how many times to repeat a request the model did not answer (`4` by default, five attempts; only failures that carried no answer are repeated); exceeding `AI_PROVIDER_TIMEOUT` is repeated only once
            - `AI_PROVIDER_BASE_URL` — **required** for `openai_compatible`: the URL of the
              OpenAI-compatible provider
            - `AI_PROVIDER_SCOPE` — GigaChat only. Chooses the GigaChat version; it is
              listed in your account.
            - `AI_PROVIDER_FOLDER_ID` — **required** for YandexGPT: the folder identifier.
        - `GIT_PROVIDERS` — Git connections. **The key of an entry becomes part of its
          webhook URL**: `https://<your-host>/webhooks/<key>`. A key must match
          `^[a-z0-9][a-z0-9_-]{2,31}$` and be unique. For each connection:
            - `GIT_PROVIDER` — the Git provider to use:
                - `"github"`
                - `"gitea"`
                - `"gitlab"`
                - `"bitbucket"`
            - `GIT_PROVIDER_USER_TOKEN` — the personal access token (PAT) from your Git
              provider
            - `GIT_PROVIDER_URL` — the Git provider's URL. Required for Gitea and
              Bitbucket. Optional for GitHub and GitLab: without it `api.github.com` and
              `https://gitlab.com` are used. For GitHub Enterprise Server, give the root of
              the REST API including its `/api/v3` suffix (for example
              `https://ghe.example.com/api/v3`); for a self-managed GitLab, give the
              instance root — ReVu adds `/api/v4` itself.
            - `GIT_PROVIDER_SECRET_TOKEN` — a random string, used to validate an incoming
              webhook from the Git provider: the webhook must carry the very same secret.
              **Every connection has its own secret** — the signature of one does not fit
              another.
                - GitHub, Gitea, Bitbucket — a signature of the request body in the
                  `X-Hub-Signature-256`, `X-Gitea-Signature` or `X-Hub-Signature` header
                  (`sha256=<hex>`). For Bitbucket the signature is mandatory: it needs
                  Bitbucket Data Center 8.9+ and a filled-in **Secret** field in the webhook
                  settings, otherwise requests are rejected with `403`.
                - GitLab — either a **Signing token** (GitLab 19.0+, recommended: the body is
                  signed too) or the legacy **Secret token**, which travels in cleartext in
                  the `X-Gitlab-Token` header and protects nothing.
            - (optional) `AI_PROVIDER` — the name of a profile in `AI_PROVIDERS`, so this
              connection is reviewed by another model (for example `"cheap"`). Without it,
              `DEFAULT_AI_PROVIDER` is used.
            - (optional) `GIT_PROVIDER_REVIEWER` — Bitbucket only: the username the review
              is published as. Reviews run on `pr:opened` and `pr:from_ref_updated` (new
              commits in the pull request); a change to the pull request's metadata alone
              (`pr:modified`) starts nothing.
            - (optional) `SYSTEM_PROMPT`, `REVIEW_MODE`, `MAX_CONCURRENT_REVIEWS`,
              `NOTIFY_ON_FAILURE`, `INCLUDE_PR_DISCUSSION` — values for this connection;
              without them the global ones apply.
        - (optional) `SYSTEM_PROMPT` — extra instructions appended to the standard prompt
          (they do not replace it: the answer format and the review criteria stay).
        - Logging (every setting is optional):
            - `LOG_LEVEL` — the logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`,
              `CRITICAL`; `INFO` by default)
            - `LOG_DIR` / `LOG_FILE` — the directory and the file name (`logs` and
              `logs.txt` by default). Logs go to the console and to the file; in Docker the
              directory belongs on the host, which `docker-compose.yaml` already does.
            - `MAX_SIZE_MB` / `BACKUP_COUNT` — how large the file may grow before it
              rotates, and how many rotations to keep (`10` and `5` by default).
            - Every line names the connection it belongs to, which saves real time when
              several connections share one instance.
        - (optional) `MAX_CONCURRENT_REVIEWS` — how many reviews may run at once for one
          connection (`3` by default). The rest of the webhooks wait for a free slot rather
          than starting an unbounded number of calls to the AI. The limit is per
          connection, so a noisy repository cannot block the others.
        - (optional) `HTTP_CLIENT_TIMEOUT` — the HTTP timeout in seconds (`30.0` by default)
        - (optional) `HTTP_CLIENT_REQUEST_ATTEMPTS` — how many times a repeatable request
          may be sent in total (`3` by default). Only safe requests are repeated: client
          errors (`4xx`) are not, and a review comment (`POST`) is not sent again after a
          `5xx` or a read timeout — that would leave a duplicate in the pull request.
        - (optional) `HTTP_CLIENT_RETRY_BACKOFF` — the base delay of the exponential
          backoff between attempts, in seconds (`0.5` by default, capped at 8). A
          `Retry-After` header from the server takes precedence.
        - (optional) `APP_HOST` / `APP_PORT` — the address the built-in server listens on
          (`0.0.0.0:8000` by default)
        - (optional) `NOTIFY_ON_FAILURE` — whether to publish a short comment in the pull
          request when a review could not be completed (`true` by default). The message
          carries the kind of error only; the details stay in the logs. Turn it off if a
          systematic failure would only add noise.
        - (optional) `CONTEXT_DEPTH` — how much code the model sees: `"flat"` (the default,
          the diff alone) or `"deep"` (also the bodies of changed functions, the signatures
          of dependencies and the related tests). `deep` reads repository files and hands
          them to the AI provider whole, which is why it is off by default.
        - (optional) `CONTEXT_MAX_FILES` (`12` by default) — how many **additional** files
          may be fetched: dependency modules and tests. Changed files and the diff itself
          are not counted here and are never trimmed.
        - (optional) `CONTEXT_MAX_CHARS` (`40000` by default, roughly 10k tokens) — the
          total budget for everything the context adds. When it runs out the context is
          cut and the log says so; the diff stays complete.
        - (optional) `INCLUDE_PR_DISCUSSION` — whether to hand other people's pull request
          comments to the AI provider as context for a repeated review (`true` by default).
          ReVu's own earlier findings are always sent: they are its own previous answer
          rather than new data leaving your network. Turn the flag off when the discussion
          must not reach the AI provider.

      The configuration is validated at start-up: a typo in `REVIEW_MODE`, an unknown
      profile name in `AI_PROVIDER` or a missing provider token stops the start with the
      offending key named, instead of turning every webhook into a silent failure.
    4. Save and exit with CTRL+S, then CTRL+X.
3. Download the compose file:
    ```bash
    wget -O docker-compose.yaml https://raw.githubusercontent.com/proDreams/revu/refs/heads/main/docker-compose.yaml
    ```
4. Start it:
    ```bash
    sudo docker compose up -d
    ```
5. Open ReVu to the outside. The port is deliberately not published in
   `docker-compose.yaml`: by default the service is reachable only from its own compose
   network. Choose one of two ways — both are already in the file, commented out, so all
   it takes is removing `#`:
    - **With Traefik** — uncomment the service's `labels` block and the `networks` block at
      the end of the file, replacing `revu.example.com` with your own domain. Traefik
      obtains the certificate itself (the `letsencrypt` resolver), and the container keeps
      speaking plain HTTP on port 8000.
    - **With a proxy on the host (Caddy, NGINX) or a Git server on the same network as
      ReVu** — uncomment `ports: - "8000:8000"` and point the proxy at `127.0.0.1:8000`.
      If your Git provider and ReVu share a Docker network, no proxy is needed at all.
   HTTPS with a valid certificate is required when the Git provider delivers webhooks from
   the outside.
6. Register the webhook in every Git provider, pointing at your connection's URL:
    ```
    https://<your-host>/webhooks/<key from GIT_PROVIDERS>
    ```
    For the `main` connection of the example configuration that is
    `https://revu.example.com/webhooks/main`. The webhook secret must equal
    `GIT_PROVIDER_SECRET_TOKEN` of **that** connection: the signature of one connection
    does not fit another.
    - **GitHub** — enable the **Pull requests** event and fill in the **Secret** field.
    - **Gitea** — enable **Pull request** events and fill in the **Secret** field.
    - **GitLab** — enable **Merge request events**. In the **Signing token** field (GitLab
      19.0+) paste this connection's `GIT_PROVIDER_SECRET_TOKEN`; on older versions fill in
      **Secret token** instead. Reviews run on `open`, `reopen` and `update`; editing the
      title or the labels (an `update` with no new commits) does not start one, because
      GitLab does not distinguish those events — ReVu compares the head commit instead.
    - **Bitbucket** — enable the **Opened** and **Source branch updated** events and fill
      in **Secret**.
7. (optional) Check that the service came up: `curl http://localhost:8000/health` should
   answer `{"status":"ok"}`. That works when the port is published (step 5); without it,
   the same check from inside the container is
   `docker compose exec revu curl -fsS http://127.0.0.1:8000/health`. The same endpoint
   backs the image's `HEALTHCHECK`.
   The connections the service found are printed to the log at start-up:
   `configured git connections: gh-main (github), gitea-internal (gitea); default AI profile: strong`

### Several Git providers on one instance

One ReVu instance serves any number of Git connections: GitHub, Gitea, GitLab and Bitbucket
in any combination. Every connection is an entry of its own in `GIT_PROVIDERS`, with its
own token, its own secret and its own webhook URL.

The AI provider is shared: every connection uses the profile named by
`DEFAULT_AI_PROVIDER` unless it names one itself:

```yaml
DEFAULT_AI_PROVIDER: "strong"

AI_PROVIDERS:
  strong:
    AI_PROVIDER: "openai"
    AI_PROVIDER_API_KEY: "sk-..."
    AI_PROVIDER_MODEL: "gpt-4.1"
  cheap:
    AI_PROVIDER: "openai_compatible"
    AI_PROVIDER_BASE_URL: "https://openrouter.ai/api/v1"
    AI_PROVIDER_API_KEY: "sk-or-..."
    AI_PROVIDER_MODEL: "qwen-2.5-coder"

GIT_PROVIDERS:
  main:                 # goes to "strong" — like everything else
    GIT_PROVIDER: "github"
    GIT_PROVIDER_USER_TOKEN: "ghp_..."
    GIT_PROVIDER_SECRET_TOKEN: "..."
  side-project:         # overridden: goes to "cheap"
    GIT_PROVIDER: "gitea"
    GIT_PROVIDER_URL: "https://gitea.example.com"
    GIT_PROVIDER_USER_TOKEN: "..."
    GIT_PROVIDER_SECRET_TOKEN: "..."
    AI_PROVIDER: "cheap"
    REVIEW_MODE: "comment"          # optional
    MAX_CONCURRENT_REVIEWS: 1       # optional
  gitlab-internal:      # self-managed: without the URL ReVu would go to gitlab.com
    GIT_PROVIDER: "gitlab"
    GIT_PROVIDER_URL: "https://gitlab.example.com"
    GIT_PROVIDER_USER_TOKEN: "glpat-..."
    GIT_PROVIDER_SECRET_TOKEN: "whsec_..."
```

The overhead is one container, one configuration and one set of logs, rather than a
separate instance per provider.

### Repeated reviews

When the author pushes fixes, ReVu does not start from a blank page. Before reviewing it
reads what the pull request already carries: its own earlier findings and the discussion
around them. That run uses a prompt of its own, and the result differs:

- **what was fixed is not raised again** — a finding the author closed stays closed;
- **what remains is not duplicated** — instead of a second comment on the same line it is
  reported in the summary;
- **inline comments are placed on what is new** — problems in the fresh changes;
- **the summary opens with progress** — `📊 Из прошлых замечаний исправлено: 3 из 5.
  Осталось: 2.` The total comes from ReVu's own earlier findings, so it cannot be talked
  down.

The discussion counts too: when the participants explained a decision or asked for the code
to stay as it is, the finding is not raised again.

**How ReVu recognises its own comments.** Not by author: ReVu usually runs on your own
token, so "the bot" and "you" are one account, and by author alone every comment of yours
would look like an earlier review. Instead ReVu **signs** what it publishes: an invisible
marker at the end of the text, and a visible `🤖 ReVu` header on top (`🤖 ReVu · повторное
ревью` for a follow-up). Inline comments carry a `🤖 ReVu:` prefix. So under one account it
remains clear who is who, and recognising its own comments does not depend on the account at
all.

> **A separate account for ReVu is still recommended** — not for correctness (the signature
> provides that) but for readability: the pull request history then shows at a glance where
> the bot is and where the person is, and your own conversation does not mix with the
> model's output.

Where the earlier comments come from:

| Provider | What is read |
|---|---|
| GitHub, Gitea | the pull request timeline, the inline comments and the review bodies |
| GitLab | merge request notes (system notes are skipped, the `resolved` state is kept) |
| Bitbucket Data Center | comments with their anchors and nested replies |

A repeated review is triggered by the same webhook as the first: the sign is the presence of
ReVu's earlier findings in the pull request. A pull request that was never reviewed gets the
ordinary prompt.

> **Privacy.** The discussion in the pull request (your colleagues' comments) reaches the AI
> provider as context. When that is not acceptable, turn `INCLUDE_PR_DISCUSSION` off and
> only ReVu's own findings are sent.

### Context depth

By default ReVu reviews the diff: predictable in cost, and nothing extra leaves your
network. The `deep` mode adds exactly four things:

0. **the shape of the repository** — one line per directory, a few names each, manifests and lock files
   first. `uv.lock` in that list is how the review knows the project uses uv, `packages/` is where the
   components live, `.gitea/workflows/` is what builds it. The tree is read for tests and dependencies
   anyway, so this costs no extra request;

1. **the full body of the changed functions** — a diff shows three lines around the edit,
   while the model is judging the whole method. This is the most common cause both of
   invented findings and of misses;
2. **the signatures of what the changed code calls** — imports bring in declarations (and
   docstrings), not bodies. The model sees the contract instead of inventing it;
3. **the related tests** — matched by file path and name, with the test function names
   only.

What is worth knowing:

- **The diff is never trimmed.** The budgets bound additional files and the total size of
  what is added. A pull request touching 15 files is shown whole, whatever
  `CONTEXT_MAX_FILES` says.
- **Languages.** Parsing goes through tree-sitter, and grammars ship for Python,
  JavaScript, TypeScript, Go, Java, Kotlin, Ruby, Rust, C#, PHP, C, C++, Swift, Scala,
  Elixir, Lua, Perl, Dart, Bash, SQL, HTML, CSS, HCL, YAML, JSON, Make, Zig, Haskell, OCaml
  and Dockerfile. A language without a grammar does not turn the mode off: the changed file
  is included whole.
- **Privacy.** In `deep`, whole files reach the AI provider rather than only the changes.
  Paths such as `.env`, keys and `credentials`, along with `node_modules/`, `vendor/`,
  `dist/`, minified files and lock files, are never sent. If that is not acceptable, stay
  on `flat`.
- **Degradation.** Any failure while gathering context (no permission, host unreachable, a
  budget reached) does not break the review: it proceeds from the diff, and the log says
  why.
- **Comments stay on the diff.** The model is told plainly not to leave inline comments on
  the surrounding code; a problem that is only visible there belongs in the general
  comment.

**How to tune the budgets.** Every review writes one line to the log:

```
review context for connection main, owner/repo#7: depth=deep; diff=3 files/4821 chars (~1205 tokens);
context=8 entries/37120 chars (~9280 tokens): bodies=3 extra_files=4 signatures=7 tests=12 unparsed=1;
requests=9 truncated=False took=1.83s
```

It shows what the review cost: `diff` is the size of the pull request itself, `context` is
what was added, `requests` is how many calls went to the host and `truncated` says whether a
budget was reached. If `truncated=True` is common and tokens are cheap, raise
`CONTEXT_MAX_CHARS`; if `context` eats more than the diff itself, lower it.

### Migrating from 1.x to 2.0

The configuration format changed, and the old file is deliberately **not** accepted: the
application refuses to start and points at what moved. Values carry over like this:

| Was (1.x) | Became (2.0) |
|---|---|
| `GIT_PROVIDER_CONFIG.GIT_PROVIDER` | `GIT_PROVIDERS.<key>.GIT_PROVIDER` |
| `GIT_PROVIDER_CONFIG.GIT_PROVIDER_USER_TOKEN` | `GIT_PROVIDERS.<key>.GIT_PROVIDER_USER_TOKEN` |
| `GIT_PROVIDER_CONFIG.GIT_PROVIDER_URL` | `GIT_PROVIDERS.<key>.GIT_PROVIDER_URL` |
| `GIT_PROVIDER_CONFIG.GIT_PROVIDER_SECRET_TOKEN` | `GIT_PROVIDERS.<key>.GIT_PROVIDER_SECRET_TOKEN` |
| `GIT_PROVIDER_CONFIG.GIT_PROVIDER_REVIEWER` | `GIT_PROVIDERS.<key>.GIT_PROVIDER_REVIEWER` |
| `AI_PROVIDER_CONFIG.AI_PROVIDER` | `AI_PROVIDERS.<name>.AI_PROVIDER` + `DEFAULT_AI_PROVIDER: <name>` |
| `AI_PROVIDER_CONFIG.AI_PROVIDER_*` | `AI_PROVIDERS.<name>.AI_PROVIDER_*` |
| `REVIEW_MODE`, `SYSTEM_PROMPT`, `MAX_CONCURRENT_REVIEWS` | still global, now overridable per connection |
| `HTTP_CLIENT_*`, `LOG_*`, `APP_*` | unchanged |

**The webhook URL has to change too** in your Git provider's settings: instead of
`/webhooks/github`, `/webhooks/gitea` or `/webhooks/bitbucket` it is now `/webhooks/<key>`.
The old routes are gone.

**GitLab** is supported from 2.1.0 and needs no migration of its own: add a connection with
`GIT_PROVIDER: "gitlab"` and register its webhook URL.

### Updating

Updating is one command:

```bash
sudo docker compose pull && sudo docker compose up -d
```

## Reviews in a pipeline

The server needs an inbound HTTPS address, a host that stays up and a separate account for
the bot. When that is unavailable or unwanted, ReVu runs in the pipeline itself: the code
is already checked out, the event says which pull request it is, and the job already holds
a token.

The same image, a different command: `revu review` instead of the server.

### GitHub Actions

The shortest path is the action: it checks the change out itself (with `fetch-depth: 0`,
without which there is nothing to compare against) and runs the image.

```yaml
name: ReVu

on:
  pull_request:
    types: [opened, synchronize, reopened]
    paths-ignore:            # saving: documentation needs no review
      - "**/*.md"
      - "docs/**"

concurrency:                 # a new push cancels the previous review
  group: revu-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write   # without this GITHUB_TOKEN cannot comment
    steps:
      - uses: proDreams/revu@v2
        with:
          ai-api-key: ${{ secrets.REVU_AI_KEY }}
          ai-model: gpt-4o-mini
          # format: github-annotations   # marks in "Files changed" as well
          # context-depth: deep          # read the surroundings of changed functions
          # fail-on: error               # fail when the review could not run
```

The action's inputs are named after the variables in the table below (`ai-model` is
`AI_PROVIDER_MODEL`), plus `image` (`ghcr.io/prodreams/revu:latest` by default),
`checkout: false`, `fail-on`, `format` and `args` for everything else.

If the action does not fit (or the host is not GitHub), the same thing as a `docker run`
step. `actions/checkout` cannot be used inside a container job — it is a JavaScript action
and needs Node, which the ReVu image does not have. So the checkout stays on the runner and
the image is started as a step:

```yaml
name: ReVu

on:
  pull_request:
    types: [opened, synchronize, reopened]
    paths-ignore:            # saving: documentation needs no review
      - "**/*.md"
      - "docs/**"

concurrency:                 # a new push cancels the previous review
  group: revu-${{ github.event.pull_request.number }}
  cancel-in-progress: true

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write   # without this GITHUB_TOKEN cannot comment
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0     # the merge base is needed to compare against
      - name: ReVu
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          AI_PROVIDER_API_KEY: ${{ secrets.REVU_AI_KEY }}
          AI_PROVIDER_MODEL: gpt-4o-mini
        run: |
          docker run --rm -v "$PWD:/repo" -w /repo \
            -e GITHUB_TOKEN -e AI_PROVIDER_API_KEY -e AI_PROVIDER_MODEL \
            ghcr.io/prodreams/revu:2.5.0 review
```

### GitLab CI

Here a container is the native model, and `CI_JOB_TOKEN` is available straight away:

```yaml
revu:
  stage: test
  image: ghcr.io/prodreams/revu:2.5.0
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  variables:
    GIT_DEPTH: 0                      # history down to the merge base is needed
    AI_PROVIDER_API_KEY: $REVU_AI_KEY
    AI_PROVIDER_MODEL: gpt-4o-mini
    # GIT_PROVIDER_USER_TOKEN: $REVU_PROJECT_TOKEN   # to also comment in the MR
  script:
    - revu review --format gitlab-codequality
  artifacts:
    when: always                      # the report matters when the job failed too
    reports:
      codequality: revu-codequality.json
```

About the token: `CI_JOB_TOKEN` can **read** a merge request and its notes, but cannot write
one. So either set `GIT_PROVIDER_USER_TOKEN` (a project access token with the `api` scope)
and the review is also posted as a comment in the merge request, or leave it unset: the
findings go into the Code Quality report that GitLab shows in the merge request widget, and
the review text into the pipeline log. The report creates no comment at all and needs no
write permission whatsoever.

### Gitea Actions

The format is GitHub's; what differs is where the workflow lives and that the host is better
named explicitly: Gitea Actions repeats GitHub's variables, and by them alone Gitea is not
always distinguishable from github.com.

```yaml
# .gitea/workflows/revu.yaml
name: ReVu

on:
  pull_request:

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: ReVu
        env:
          GIT_PROVIDER: gitea
          GIT_PROVIDER_URL: https://git.example.com
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          AI_PROVIDER_API_KEY: ${{ secrets.REVU_AI_KEY }}
          AI_PROVIDER_MODEL: gpt-4o-mini
        run: |
          docker run --rm -v "$PWD:/repo" -w /repo \
            -e GIT_PROVIDER -e GIT_PROVIDER_URL -e GITHUB_TOKEN \
            -e AI_PROVIDER_API_KEY -e AI_PROVIDER_MODEL \
            ghcr.io/prodreams/revu:2.5.0 review
```

### Environment variables

ReVu recognises the host from `GITHUB_ACTIONS`, `GITLAB_CI` and `GITEA_ACTIONS` itself, and
takes the repository, the pull request number and the revisions from the platform's own
variables (`GITHUB_EVENT_PATH`, `CI_MERGE_REQUEST_IID`, `CI_MERGE_REQUEST_DIFF_BASE_SHA` and
the like). Only the AI key has to be set explicitly.

| Variable | What it sets |
|---|---|
| `AI_PROVIDER` | the vendor: `openai` (default), `openai_compatible`, `gigachat`, `yandexgpt` |
| `AI_PROVIDER_API_KEY` | the provider's key (required) |
| `AI_PROVIDER_MODEL` | the model (required) |
| `AI_PROVIDER_BASE_URL` | a custom endpoint for `openai_compatible` |
| `AI_PROVIDER_SCOPE`, `AI_PROVIDER_FOLDER_ID` | for GigaChat and YandexGPT |
| `GIT_PROVIDER` | the host: `github`, `gitea`, `gitlab`, `bitbucket` |
| `GIT_PROVIDER_URL` | the address of a self-hosted host |
| `GIT_PROVIDER_USER_TOKEN` | a token to read and comment with; without it the platform's own token is used |
| `REVIEW_MODE` | `inline` (default) or `comment` |
| `CONTEXT_DEPTH`, `CONTEXT_MAX_FILES`, `CONTEXT_MAX_CHARS` | the context depth and its budgets |
| `INCLUDE_PR_DISCUSSION` | whether to send the AI other people's pull request comments |
| `LOG_LEVEL` | `DEBUG`, `INFO` (default), `WARNING`, `ERROR` |

The names are the same as in `settings.yaml`, so knowing the file carries over unchanged.
The validation is shared too: a typo in `REVIEW_MODE` stops the job with the very message it
would have stopped the server with.

### Flags

| Flag | What it does |
|---|---|
| `--diff-source git\|api\|file` | where the change comes from: `git` from the checkout (default), `api` through the host, `file` from `--diff-file` |
| `--diff-file PATH` | a saved diff; turns on `--diff-source file` |
| `--base`, `--head` | the revisions to compare, when the platform did not say |
| `--repo`, `--pr` | the repository and the pull request number — for a run outside CI |
| `--provider` | the host; required outside CI |
| `--depth flat\|deep` | overrides `CONTEXT_DEPTH` |
| `--comment` / `--stdout` | comment in the pull request, or print to the log; by default a comment when the token allows one |
| `--format text\|json\|gitlab-codequality\|github-annotations` | what to add to the output: `text` (default), machine-readable `json`, a Code Quality report, or annotations in "Files changed" |
| `--output PATH` | where a report is written (`revu-codequality.json` by default) |
| `--fail-on never\|error\|findings` | when to fail the job: never (default), when the review could not run, or when there are findings |

Exit codes: `0` — all good, `1` — `--fail-on findings` was asked for and there were
findings, `2` — the review could not be started (a bad argument among the reasons).

### Running it locally

The same CLI works on a developer's machine — no CI, no webhook, no server:

```bash
export AI_PROVIDER_API_KEY=...
export AI_PROVIDER_MODEL=gpt-4o-mini
export GIT_PROVIDER=github
export GIT_PROVIDER_USER_TOKEN=...

revu review --base origin/main --head HEAD --stdout
```

### Worth knowing

- **`fetch-depth: 0` is required.** A shallow clone has no merge base, so
  `git diff base...head` answers with nothing and the review would look like a pull request
  that changes no files. ReVu catches that and stops with advice rather than reviewing an
  empty diff.
- **In `deep`, context is free.** Files are read from disk and the tree is one `git ls-tree`
  command, so no request goes to the host at all; the same mode on the server would cost up
  to 12 requests.
- **Pull requests from forks are not supported.** Reviews run for pull requests inside the
  repository: a pull request from a fork has neither secrets nor permission to comment, and
  `pull_request_target` calls for care of its own.
- **A server and a pipeline on one repository mean two reviews per push.** Pick one.
- **`--fail-on` defaults to `never`:** the pipeline does not go red because of a model's
  opinion. To have the opposite, use `--fail-on error` (the review could not run) or
  `--fail-on findings` (there are findings).
- **Findings can be shown without publishing anything.** `--format github-annotations`
  prints the annotations GitHub places next to the changed lines, and `--format
  gitlab-codequality` writes the report the merge request widget reads. Neither creates a
  comment and neither needs write permission — that is the answer to a read-only
  `CI_JOB_TOKEN`.
- **A failed review is announced in the pull request.** `NOTIFY_ON_FAILURE` (on by default)
  publishes a short comment naming the kind of error, when a token that may write exists;
  the details stay in the log. Turn it off if you would rather have no noise.
- **The review always reaches the pipeline log.** When the token allows a comment, it is
  posted as well: the log is read by whoever debugs the pipeline, the comment by the author
  of the change.
- **No repository code is ever executed.** A review reads files and parses them: neither
  `make`, nor `npm install`, nor `pip install` from the reviewed tree is ever run.

## Development

You will need Python 3.13+, [uv](https://docs.astral.sh/uv/) and Docker — for building the
image.

```bash
make install_dev   # project dependencies and git hooks
make run           # run the application locally
make test          # tests with coverage (100% at the moment)
make lint          # ruff, formatting and pre-commit
make typecheck     # mypy with the project's dependencies
```

`make typecheck` is not a duplicate of `make lint`: the `mypy` hook in pre-commit runs in an
isolated environment without the project's dependencies, so it cannot see errors at the
boundary with FastAPI, pydantic and the provider SDKs. That run is what found, for instance,
that a model in the Yandex AI Studio SDK is built synchronously and an `await` before it
failed at runtime.

Integration tests bring up the real application and the DI container; the rest run on mocks:

```bash
uv run pytest -m integration       # integration only
uv run pytest -m "not integration" # the fast ones
```

## Author

- [Ivan Ashikhmin](https://t.me/proDreams)

The project is written within "Код на салфетке" (Code on a napkin):

- Website: https://napkincode.ru
- Telegram channel: https://t.me/napkincode

---

## Support

If you like the project and would like to support its development, consider a donation:

- [Support via YooMoney](https://yoomoney.ru/to/41001431694461)
- [Support via Tribute in Telegram](https://t.me/tribute/app?startapp=dyds)
- [Support via our Telegram bot](https://t.me/press_any_button_bot?start=donate)

Your support helps the project grow and improve what comes next.

---

## License

This project is distributed under the MIT license. The details are in [LICENSE](LICENSE).
