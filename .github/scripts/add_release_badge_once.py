"""Add a dynamic Latest release badge to Nuvio README once."""
from pathlib import Path

path = Path("README.md")
text = path.read_text(encoding="utf-8")
heading = "# Nuvio for Home Assistant\n"
assert text.count(heading) == 1, "Expected unique Nuvio README title"
assert "img.shields.io/github/v/release/fVaqueroG/home-assistant-nuvio" not in text, "Badge already exists"
badge = "\n[![Latest release](https://img.shields.io/github/v/release/fVaqueroG/home-assistant-nuvio?label=latest%20release)](https://github.com/fVaqueroG/home-assistant-nuvio/releases/latest) · [Latest release notes](https://github.com/fVaqueroG/home-assistant-nuvio/releases/latest) · [All releases and changes](https://github.com/fVaqueroG/home-assistant-nuvio/releases)\n"
path.write_text(text.replace(heading, heading + badge, 1), encoding="utf-8")
assert path.read_text(encoding="utf-8").count("[![Latest release]") == 1
print("PASS: Dynamic latest-release badge and release links added to README")
