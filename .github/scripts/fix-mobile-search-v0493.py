from pathlib import Path
import json

card = Path('custom_components/nuvio/frontend/nuvio-card.js')
source = card.read_text(encoding='utf-8')

def once(old, new, label):
    global source
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f'{label}: expected exactly one match, found {count}')
    source = source.replace(old, new, 1)

once(
    '''<div class="search"><ha-icon icon="mdi:magnify"></ha-icon><input id="search" value="'+this.esc(this._query)+'" placeholder="Search Nuvio…"></div>''',
    '''<div class="search"><input id="search" type="search" enterkeyhint="search" aria-label="Search Nuvio" value="'+this.esc(this._query)+'" placeholder="Search Nuvio…"><button type="button" class="search-submit" id="searchSubmit" title="Search" aria-label="Search"><ha-icon icon="mdi:magnify"></ha-icon></button></div>''',
    'search markup',
)
once(
    '.search input{border:0;',
    '.search-submit{display:grid;place-items:center;flex:0 0 40px;width:40px;height:40px;padding:0;margin:0;border:0;border-radius:50%;background:transparent;color:var(--primary-text-color);cursor:pointer;touch-action:manipulation}.search-submit ha-icon{--mdc-icon-size:23px}.search-submit:focus-visible{outline:2px solid var(--primary-color)}.search input{min-width:0;flex:1 1 auto;border:0;',
    'search button touch target',
)
once(
    '    if(q){q.addEventListener("input",e=>this._query=e.target.value);q.addEventListener("keydown",e=>{if(e.key==="Enter")this.search();});}',
    '''    if(q){
      const submitSearch=()=>{this._query=q.value;q.blur();void this.search();};
      q.addEventListener("input",e=>this._query=e.target.value);
      q.addEventListener("keydown",e=>{
        if(e.key==="Enter"&&!e.isComposing){e.preventDefault();submitSearch();}
      });
      r.querySelector("#searchSubmit")?.addEventListener("click",submitSearch);
    }''',
    'touch and keyboard search events',
)
once('v0.4.92</span>', 'v0.4.93</span>', 'displayed version')
assert 'id="searchSubmit"' in source
assert 'enterkeyhint="search"' in source
assert 'addEventListener("click",submitSearch)' in source
card.write_text(source, encoding='utf-8')

manifest_path = Path('custom_components/nuvio/manifest.json')
manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
if manifest.get('version') != '0.4.92':
    raise RuntimeError(f"Unexpected installed version: {manifest.get('version')}")
manifest['version'] = '0.4.93'
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('PASS: search button, mobile Search key, and desktop Enter wiring')
