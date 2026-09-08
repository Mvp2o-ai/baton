"""Documented txcript CLI pin. Keep README and CI on this exact rev."""

TXCRIPT_GIT = "https://github.com/wiltshirek/txcript"
TXCRIPT_REV = "b35b6bee9f996cc2aea58dadef0a54fb5fa1d2fe"
TXCRIPT_CRATE = "txcript-cli"


def install_cmd() -> str:
    return f"cargo install --git {TXCRIPT_GIT} --rev {TXCRIPT_REV} {TXCRIPT_CRATE}"
