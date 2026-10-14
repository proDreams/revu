"""The GitHub action manifest, checked as the interface it is.

A composite action passes values through `env:` and then names those variables again
in `docker run -e`. Nothing in the platform notices a name spelled differently in the
two places: the container simply receives an empty value, and the setting it was
meant to carry is silently ignored. So the two lists are compared here.
"""

import re
from pathlib import Path

import pytest

# The stubs for PyYAML are not installed in the environment the mypy hook runs in,
# so the call below is checked as an untyped library.
import yaml  # type: ignore[import-untyped,import-not-found]

pytestmark = pytest.mark.unit

MANIFEST = Path("action.yml")


@pytest.fixture(scope="module")
def action() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def step(action) -> dict:
    """The step that runs the review, rather than the checkout before it."""
    return [item for item in action["runs"]["steps"] if "run" in item][-1]


def test_it_is_a_composite_action(action):
    assert action["runs"]["using"] == "composite"


def test_it_declares_a_name_and_branding(action):
    assert action["name"] == "ReVu"
    assert action["branding"]["icon"]
    assert action["branding"]["color"]


def test_the_key_and_the_model_are_required(action):
    """Without them nothing can be reviewed, so the platform should say so first."""
    assert action["inputs"]["ai-api-key"]["required"] is True
    assert action["inputs"]["ai-model"]["required"] is True


def test_the_image_is_pinned_by_default(action):
    assert action["inputs"]["image"]["default"].startswith("ghcr.io/prodreams/revu")


def test_the_checkout_is_done_by_the_action(action):
    """Nobody should have to remember `fetch-depth: 0`, and its symptom is silence."""
    checkout = action["runs"]["steps"][0]

    assert checkout["uses"].startswith("actions/checkout@")
    assert checkout["with"]["fetch-depth"] == 0


def test_every_variable_passed_to_the_container_is_one_the_step_sets(step):
    passed = set(re.findall(r"-e ([A-Z_]+)", step["run"]))
    bound = set(step["env"])

    assert passed <= bound, f"passed to docker without being set: {passed - bound}"
    # The rest are this step's own locals: the image to run and the arguments it
    # assembles, none of which the container has any business reading.
    assert bound - passed == {"REVU_ARGS", "REVU_FAIL_ON", "REVU_FORMAT", "REVU_IMAGE"}


def test_every_input_reaches_the_step(action, step):
    """An input that is declared and then forgotten is a trap for whoever uses it."""
    bound = set(step["env"])
    for name, spec in action["inputs"].items():
        if name in {"image", "checkout", "args", "format", "fail-on"}:
            continue

        assert any(name.replace("-", "_").upper() in key or _matches(name, key) for key in bound), name


def _matches(input_name: str, variable: str) -> bool:
    """`ai-api-key` reaches the container as `AI_PROVIDER_API_KEY`, and the like."""
    aliases = {
        "ai-api-key": "AI_PROVIDER_API_KEY",
        "ai-model": "AI_PROVIDER_MODEL",
        "ai-base-url": "AI_PROVIDER_BASE_URL",
        "ai-scope": "AI_PROVIDER_SCOPE",
        "ai-folder-id": "AI_PROVIDER_FOLDER_ID",
        "ai-provider": "AI_PROVIDER",
        "git-provider": "GIT_PROVIDER",
        "git-provider-url": "GIT_PROVIDER_URL",
        "github-token": "GITHUB_TOKEN",
    }

    return aliases.get(input_name) == variable


def test_the_failure_gate_is_passed_as_an_argument(step):
    assert 'arguments=(--fail-on "$REVU_FAIL_ON")' in step["run"]


def test_an_empty_format_is_not_passed_on(step):
    """`--format ""` would be an argument error; the command decides the default."""
    assert 'if [ -n "$REVU_FORMAT" ]' in step["run"]


def test_the_checkout_can_be_skipped(action):
    assert action["inputs"]["checkout"]["default"] == "true"
    assert action["runs"]["steps"][0]["if"] == "inputs.checkout == 'true'"
