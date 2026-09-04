"""Administrative control-plane authorization scopes for issue #147."""

CONTROL_SCOPES: dict[tuple[str, str], tuple[str, str, str]] = {
    ("POST", "/v1/principals"): (
        "admin.write",
        "administrative_control",
        "principals",
    ),
    ("GET", "/v1/principals"): (
        "admin.read",
        "administrative_control",
        "principals",
    ),
    ("GET", "/v1/principals/{id}"): (
        "admin.read",
        "administrative_control",
        "principals",
    ),
    ("PUT", "/v1/principals/{id}/status"): (
        "admin.write",
        "administrative_control",
        "principals",
    ),
    ("POST", "/v1/principals/{id}/credentials"): (
        "admin.write",
        "administrative_control",
        "credentials",
    ),
    ("GET", "/v1/principals/{id}/credentials"): (
        "admin.read",
        "administrative_control",
        "credentials",
    ),
    ("DELETE", "/v1/credentials/{id}"): (
        "admin.write",
        "administrative_control",
        "credentials",
    ),
    ("POST", "/v1/credentials/{id}/rotation"): (
        "admin.write",
        "administrative_control",
        "credentials",
    ),
}
