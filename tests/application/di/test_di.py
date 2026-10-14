from unittest.mock import AsyncMock

import pytest
from dishka import AsyncContainer

from revu.application.di import create_container
from revu.application.entities.config import (
    ConfigError,
    HttpSettings,
    Settings,
    UnknownConnectionError,
)
from revu.application.entities.enums.ai_provider_enums import AIProviderEnum
from revu.application.entities.exceptions.webhook_routes_exceptions import (
    AIProviderException,
    GitProviderException,
)
from revu.application.registry.ai_profiles import AIProfileRegistry
from revu.application.registry.git_connections import GitConnectionRegistry
from revu.domain.entities.enums.git_provider_enums import GitProviderEnum
from revu.infrastructure.ai_providers.gigachat.gigachat_port import GigaChatPort
from revu.infrastructure.ai_providers.openai.openai_port import OpenAIPort
from revu.infrastructure.ai_providers.openai_compatible.openai_compatible_port import (
    OpenAICompatiblePort,
)
from revu.infrastructure.ai_providers.yandexgpt.yandexgpt_port import YandexGPTPort
from revu.infrastructure.git_providers.gitea.gitea_port import GiteaPort
from revu.infrastructure.git_providers.github.github_port import GithubPort
from revu.infrastructure.http_client.http_client_gateway import HttpClientGateway
from tests.conftest import make_ai_profile, make_connection, make_settings

pytestmark = pytest.mark.unit


async def _container(app_settings) -> AsyncContainer:
    return create_container()


async def test_the_configuration_is_provided_from_the_settings_loader(app_settings):
    async with create_container() as container:
        settings = await container.get(Settings)

    assert settings is app_settings


async def test_every_connection_gets_its_own_port(app_settings):
    async with create_container() as container:
        registry = await container.get(GitConnectionRegistry)

        github = registry.resolve("gh-main")
        gitea = registry.resolve("gitea-int")

    assert isinstance(github.port, GithubPort)
    assert isinstance(gitea.port, GiteaPort)
    # Different credentials, therefore different ports: no state leaks between them.
    assert github.port is not gitea.port
    assert github.port._get_headers()["Authorization"] != gitea.port._get_headers()["Authorization"]


def test_two_github_connections_use_their_own_tokens(http_gateway):
    """The regression that would appear if ports were global singletons."""
    settings = make_settings(
        git_connections={
            "gh-one": make_connection(key="gh-one", user_token="token-one"),
            "gh-two": make_connection(key="gh-two", user_token="token-two"),
        }
    )

    registry = GitConnectionRegistry(settings=settings, http_client=http_gateway)

    assert registry.resolve("gh-one").port._get_headers()["Authorization"] == "token token-one"
    assert registry.resolve("gh-two").port._get_headers()["Authorization"] == "token token-two"


def test_an_unknown_connection_key_is_rejected():
    registry = GitConnectionRegistry(settings=make_settings(), http_client=AsyncMock())

    with pytest.raises(UnknownConnectionError):
        registry.resolve("nope")

    with pytest.raises(UnknownConnectionError):
        registry.resolve(None)


def test_the_registry_reports_hosts_for_the_startup_summary():
    registry = GitConnectionRegistry(settings=make_settings(), http_client=AsyncMock())

    assert registry.hosts() == {"gh-main": "github", "gitea-int": "gitea", "bb-client": "bitbucket"}
    assert registry.keys() == ["bb-client", "gh-main", "gitea-int"]


def test_a_connection_uses_the_default_ai_profile(http_gateway):
    settings = make_settings()
    registry = AIProfileRegistry(settings=settings, http_client=http_gateway)

    port = registry.for_connection(settings.git_connections["gh-main"])

    assert isinstance(port, OpenAIPort)
    assert settings.git_connections["gh-main"].ai_provider == settings.default_ai_provider


def test_a_connection_override_selects_another_profile(http_gateway):
    settings = make_settings()
    registry = AIProfileRegistry(settings=settings, http_client=http_gateway)

    port = registry.for_connection(settings.git_connections["gitea-int"])

    assert isinstance(port, OpenAICompatiblePort)


def test_an_unknown_profile_name_is_rejected(http_gateway):
    registry = AIProfileRegistry(settings=make_settings(), http_client=http_gateway)

    with pytest.raises(UnknownConnectionError):
        registry.resolve("nope")


@pytest.mark.parametrize(
    ("builder", "value"),
    [
        ("git", "gitlab"),
        ("ai", "gemini"),
    ],
)
def test_an_unsupported_host_or_vendor_is_reported(http_gateway, builder, value):
    """Unreachable through the configuration, but the guard must still hold."""
    from revu.application.registry.ai_profiles import _build_port as build_ai_port
    from revu.application.registry.git_connections import _build_port as build_git_port

    if builder == "git":
        with pytest.raises(GitProviderException):
            build_git_port(make_connection(host=value), http_gateway)  # type: ignore[arg-type]
    else:
        with pytest.raises(AIProviderException):
            build_ai_port(make_ai_profile(vendor=value), http_gateway)  # type: ignore[arg-type]


def test_a_host_that_requires_a_base_url_says_so():
    connection = make_connection(host=GitProviderEnum.GITEA, base_url=None)

    with pytest.raises(ConfigError) as exc_info:
        connection.resolved_base_url

    assert "GIT_PROVIDER_URL is required for gitea" in str(exc_info.value)


async def test_a_profile_is_shared_between_connections(http_gateway):
    settings = make_settings()
    registry = AIProfileRegistry(settings=settings, http_client=http_gateway)

    assert registry.resolve("default") is registry.for_connection(settings.git_connections["gh-main"])


async def test_only_profiles_that_own_their_transport_are_closed(http_gateway, monkeypatch):
    """Closing a profile backed by the shared client would break every other one."""
    settings = make_settings(
        ai_profiles={
            "default": make_ai_profile(),
            "giga": make_ai_profile(name="giga", vendor=AIProviderEnum.GIGACHAT, model="GigaChat"),
        }
    )
    registry = AIProfileRegistry(settings=settings, http_client=http_gateway)

    giga = registry.resolve("giga")
    assert isinstance(giga, GigaChatPort)

    closed: list[str] = []

    async def fake_aclose() -> None:
        closed.append("giga")

    monkeypatch.setattr(giga, "aclose", fake_aclose)

    await registry.aclose()

    assert closed == ["giga"]
    # The OpenAI ports must stay unclosable on purpose (see the protocol docs).
    assert not hasattr(registry.resolve("default"), "aclose")


async def test_the_http_gateway_is_created_once_and_shared(app_settings):
    async with create_container() as container:
        first = await container.get(HttpClientGateway)
        second = await container.get(HttpClientGateway)

    assert first is second


async def test_the_http_gateway_is_closed_when_the_container_closes(app_settings):
    async with create_container() as container:
        gateway = await container.get(HttpClientGateway)
        assert gateway._client.is_closed is False

    assert gateway._client.is_closed is True


async def test_the_gateway_receives_the_configured_http_settings(app_settings):
    async with create_container() as container:
        gateway = await container.get(HttpClientGateway)

    assert gateway.timeout == app_settings.http.timeout
    assert gateway.attempts == app_settings.http.attempts
    assert gateway.backoff == app_settings.http.backoff


def test_http_settings_are_not_shared_by_accident():
    assert HttpSettings(timeout=1.0, attempts=1, backoff=0.0) != HttpSettings(timeout=2.0, attempts=1, backoff=0.0)


def test_connection_hosts_are_typed():
    settings = make_settings()

    assert settings.git_connections["gitea-int"].host == GitProviderEnum.GITEA


@pytest.mark.parametrize(
    ("vendor", "expected"),
    [
        (AIProviderEnum.OPENAI, OpenAIPort),
        (AIProviderEnum.OPENAI_COMPATIBLE, OpenAICompatiblePort),
        (AIProviderEnum.GIGACHAT, GigaChatPort),
        (AIProviderEnum.YANDEXGPT, YandexGPTPort),
    ],
)
def test_every_vendor_builds_the_matching_port(http_gateway, vendor, expected):
    """All four vendors stay reachable now that profiles come from the config."""
    from revu.application.registry.ai_profiles import _build_port

    profile = make_ai_profile(vendor=vendor, base_url="https://cheap.example.com/v1", folder_id="f", scope="s")

    assert isinstance(_build_port(profile, http_gateway), expected)
