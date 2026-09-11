"""Documented txcript CLI pin. Keep README and CI on this exact rev."""

TXCRIPT_GIT = "https://github.com/wiltshirek/txcript"
TXCRIPT_REV = "4869b4f4c30c2a4fe2c4779bda841458c1688fc0"
TXCRIPT_CRATE = "txcript-cli"


def install_cmd() -> str:
    return f"cargo install --git {TXCRIPT_GIT} --rev {TXCRIPT_REV} {TXCRIPT_CRATE}"
