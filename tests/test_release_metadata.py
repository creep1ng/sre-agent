from pathlib import Path

import yaml

from sre_agent.application import create_application
from sre_agent.release import CONTRACT_VERSION, SOURCE_ARCHIVE_BUILD_REVISION
from sre_agent.settings import Settings


def test_environment_injects_all_public_release_metadata() -> None:
    settings = Settings.from_environment(
        {
            "DATABASE_URL": "postgresql://unused",
            "SRE_AGENT_APPLICATION_VERSION": "2.3.4",
            "SRE_AGENT_CONTRACT_VERSION": "2.0.0",
            "SRE_AGENT_BUILD_REVISION": "0c1fb19",
        }
    )

    document = create_application(settings).openapi()

    assert document["info"]["version"] == "2.3.4"
    assert document["info"]["x-sre-agent-contract-version"] == "2.0.0"
    assert document["info"]["x-sre-agent-build-revision"] == "0c1fb19"
    assert "Application version: `2.3.4`" in document["info"]["description"]
    assert "Contract version: `2.0.0`" in document["info"]["description"]
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

    assert settings.release_metadata.contract_version == CONTRACT_VERSION == "2.0.0"
    assert settings.release_metadata.build_revision == SOURCE_ARCHIVE_BUILD_REVISION
    assert settings.release_metadata.application_version


def test_default_contract_metadata_points_to_complete_published_snapshot() -> None:
    release = Path("schemas/releases") / CONTRACT_VERSION
    manifest_path = release / "manifest.yaml"

    assert manifest_path.is_file()
    manifest = yaml.safe_load(manifest_path.read_text())
    assert manifest["contract_version"] == CONTRACT_VERSION
    for entries in manifest["inventory"].values():
        for entry in entries:
            assert (Path("schemas") / entry["path"]).is_file()
