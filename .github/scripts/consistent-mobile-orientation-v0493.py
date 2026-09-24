from pathlib import Path

card = Path('custom_components/nuvio/frontend/nuvio-card.js')
source = card.read_text(encoding='utf-8')
old = '@media(max-width:700px){:host{--pw:120px}'
new = '@media(max-width:700px), (pointer:coarse){:host{--pw:120px}'
if source.count(old) != 1:
    raise RuntimeError(f'Expected one Nuvio mobile layout rule, got {source.count(old)}')
source = source.replace(old, new, 1)
card.write_text(source, encoding='utf-8')

popup = Path('custom_components/nuvio/frontend/nuvio-popup-card.js')
source = popup.read_text(encoding='utf-8')
old = '@media(max-width:600px){.nuvio-popup-overlay{padding:0}'
new = '@media(max-width:600px), (pointer:coarse){.nuvio-popup-overlay{padding:0}'
if source.count(old) != 1:
    raise RuntimeError(f'Expected one Nuvio mobile popup layout rule, got {source.count(old)}')
source = source.replace(old, new, 1)
popup.write_text(source, encoding='utf-8')
print('PASS: mobile layout rules apply consistently to coarse-pointer phones/tablets in portrait and landscape')
