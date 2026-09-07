from pathlib import Path

from sre_agent.application import create_application
from sre_agent.release import CONTRACT_VERSION, SOURCE_ARCHIVE_BUILD_REVISION
from sre_agent.settings import Settings


def test_environment_injects_all_public_release_metadata() -> None:
    settings = Settings.from_environment(
        {
            "DATABASE_URL": "postgresql://unused",
            "SRE_AGENT_APPLICATION_VERSION": "2.3.4",
            "SRE_AGENT_CONTRACT_VERSION": "1.4.0",
            "SRE_AGENT_BUILD_REVISION": "0c1fb19",
        }
    )

    document = create_application(settings).openapi()

    assert document["info"]["version"] == "2.3.4"
    assert document["info"]["x-sre-agent-contract-version"] == "1.4.0"
    assert document["info"]["x-sre-agent-build-revision"] == "0c1fb19"
    assert "Application version: `2.3.4`" in document["info"]["description"]
    assert "Contract version: `1.4.0`" in document["info"]["description"]
    assert "Build revision: `0c1fb19`" in document["info"]["description"]


def test_empty_environment_values_keep_source_archive_defaults() -> None:
    settings = Settings.from_environment(
        {
            "DATABASE_URL": "postgresql://unused",
            "SRE_AGENT_APPLICATION_VERSION": "",
            "SRE_AGENT_CONTRACT_VERSION": "",
            "SRE_AGENT_BUILD_REVISION": "",
        }
    )

    assert settings.release_metadata.contract_version == CONTRACT_VERSION
    assert settings.release_metadata.build_revision == SOURCE_ARCHIVE_BUILD_REVISION
    assert settings.release_metadata.application_version


def test_default_contract_metadata_tracks_the_latest_schema_release() -> None:
    releases = Path("schemas/releases")
    latest = max(
        (path.name for path in releases.iterdir() if path.is_dir()),
        key=lambda value: tuple(int(part) for part in value.split(".")),
    )

    assert CONTRACT_VERSION == latest
