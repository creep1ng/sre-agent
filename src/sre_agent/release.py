"""Public release metadata for the runtime API."""

from collections.abc import Mapping
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version

CONTRACT_VERSION = "2.1.0"
SOURCE_ARCHIVE_BUILD_REVISION = "source-archive"


def installed_application_version() -> str:
    """Return the installed package version without requiring repository metadata."""
    try:
        return version("sre-agent")
    except PackageNotFoundError:
        return "0+unknown"


@dataclass(frozen=True, slots=True)
class ReleaseMetadata:
    """The application, contract, and build identities published in OpenAPI."""

    application_version: str
    contract_version: str
    build_revision: str

    @classmethod
    def defaults(cls) -> "ReleaseMetadata":
        return cls(
            application_version=installed_application_version(),
            contract_version=CONTRACT_VERSION,
            build_revision=SOURCE_ARCHIVE_BUILD_REVISION,
        )

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "ReleaseMetadata":
        defaults = cls.defaults()
        return cls(
            application_version=environment.get("SRE_AGENT_APPLICATION_VERSION")
            or defaults.application_version,
            contract_version=environment.get("SRE_AGENT_CONTRACT_VERSION")
            or defaults.contract_version,
            build_revision=environment.get("SRE_AGENT_BUILD_REVISION") or defaults.build_revision,
        )

    def openapi_description(self) -> str:
        return "\n".join(
            (
                "Deployment metadata:",
                "",
                f"- Application version: `{self.application_version}`",
                f"- Contract version: `{self.contract_version}`",
                f"- Build revision: `{self.build_revision}`",
            )
        )
