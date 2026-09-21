"""Apply the HACS integration-manifest correction once, then remove this script."""
from pathlib import Path
import json

manifest_path = Path('custom_components/nuvio/manifest.json')
manifest = json.loads(manifest_path.read_text())
assert manifest['domain'] == 'nuvio'
assert manifest['version'] == '0.4.65', manifest['version']
assert not manifest.get('issue_tracker')
manifest['issue_tracker'] = 'https://github.com/fVaqueroG/home-assistant-nuvio/issues'
manifest['version'] = '0.4.66'
manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')

card_path = Path('custom_components/nuvio/frontend/nuvio-card.js')
card = card_path.read_text()
for old, new in [('NUVIO-CARD v0.4.65', 'NUVIO-CARD v0.4.66'), ('<span class="card-version">v0.4.65</span>', '<span class="card-version">v0.4.66</span>')]:
    assert card.count(old) == 1, (old, card.count(old))
    card = card.replace(old, new)
card_path.write_text(card)

hacs = json.loads(Path('hacs.json').read_text())
assert hacs.get('name') == 'Nuvio'
assert hacs.get('content_in_root') is False
print('Manifest now advertises issue_tracker, version 0.4.66, card matches, and HACS path is valid')
