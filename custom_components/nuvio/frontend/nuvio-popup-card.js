function nuvioThemeStyle(target, choice) {
  if (!target) return;
  const palettes = {
    light: {'--card-background-color':'#ffffff','--ha-card-background':'#ffffff','--primary-text-color':'#182436','--secondary-text-color':'#58697d','--secondary-background-color':'#edf2f7','--divider-color':'#d8e0e9','--ha-card-border-color':'#d8e0e9'},
    dark: {'--card-background-color':'#171b24','--ha-card-background':'#171b24','--primary-text-color':'#f2f5fb','--secondary-text-color':'#aab6c8','--secondary-background-color':'#283142','--divider-color':'#465267','--ha-card-border-color':'#465267'}
  };
  for (const key of Object.keys(palettes.light)) target.style.removeProperty(key);
  target.style.removeProperty('color-scheme');
  target.style.setProperty('--nuvio-logo-contrast', choice === 'light' ? 'drop-shadow(0 0 1.3px rgba(25,36,58,.88)) drop-shadow(0 1px 1px rgba(25,36,58,.55))' : 'none');
  if (Object.hasOwn(palettes, choice)) {
    for (const [key,value] of Object.entries(palettes[choice])) target.style.setProperty(key,value);
    target.style.setProperty('color-scheme',choice);
  }
}
// Nuvio popup button. Bundled after nuvio-card.js so HACS loads both card types
// through the existing versioned Lovelace module resource.
class NuvioPopupCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({mode: "open"});
    this._config = {};
    this._hass = null;
    this._overlay = null;
    this._popupCard = null;
    this._autoCloseTimer = null;
    this._onKeydown = event => {
      if (event.key === "Escape" && this._overlay) {
        event.stopPropagation();
        this.closePopup();
      }
    };
  }
  static getConfigElement() { return document.createElement("nuvio-popup-card-editor"); }
  static getStubConfig() { return {button_label: "Nuvio", button_style: "horizontal", popup_width: "wide", popup_auto_close_minutes: 2}; }
  getCardSize() { return 2; }
  getGridOptions() { const tall = this.launcherStyle() === "vertical"; return {columns: tall ? 4 : 3, rows: tall ? 2 : 1, min_columns: 2, min_rows: tall ? 2 : 1}; }
launcherStyle() {
  // Old cards that saved an icon must keep showing that icon unless
  // their owner explicitly picks a different layout.
  const style = String(this._config.button_style || "").trim();
  if (["vertical", "horizontal", "logo_only", "icon_text"].includes(style)) return style;
  return String(this._config.button_icon || "").trim() ? "icon_text" : "horizontal";
}
  popupSize() { return ["normal", "wide", "fullscreen"].includes(this._config.popup_width) ? this._config.popup_width : "wide"; }
  popupAutoCloseMinutes() {
    const raw = this._config.popup_auto_close_minutes;
    if (raw === undefined || raw === null || String(raw).trim() === "") return 2;
    const minutes = Number(raw);
    return Number.isFinite(minutes) && minutes >= 0 ? minutes : 2;
  }
  startAutoCloseTimer() {
    if (this._autoCloseTimer !== null) {
      clearTimeout(this._autoCloseTimer);
      this._autoCloseTimer = null;
    }
    if (!this._overlay) return;
    const minutes = this.popupAutoCloseMinutes();
    if (minutes > 0) this._autoCloseTimer = setTimeout(() => this.closePopup(), minutes * 60000);
  }
  setConfig(config) {
    const previousAutoClose = this.popupAutoCloseMinutes();
    this._config = {...config};
    this.render();
    this._refreshPopupTheme();
    if (this._overlay) this._overlay.dataset.size = this.popupSize();
    if (this._overlay && previousAutoClose !== this.popupAutoCloseMinutes()) this.startAutoCloseTimer();
    if (this._popupCard) this._popupCard.setConfig({...this._config, type: "custom:nuvio-card"});
  }
  _refreshPopupTheme() {
      nuvioThemeStyle(this,this._config.theme);
      const frame=this._overlay?.querySelector('.nuvio-popup-frame');
      if (frame) nuvioThemeStyle(frame,this._config.theme);
    }
    set hass(value) {
      this._hass = value;
    this._refreshPopupTheme();
    if (this._popupCard) this._popupCard.hass = value;
  }
  render() {
  const label = String(this._config.button_label ?? "Nuvio");
  const icon = String(this._config.button_icon ?? "").trim();
  const style = this.launcherStyle();
  this.shadowRoot.innerHTML = `<style>
    :host{display:block;--popup-button-height:120px;height:120px!important;min-height:120px!important;max-height:120px!important;align-self:stretch;box-sizing:border-box}ha-card{display:block;width:100%;height:120px!important;min-height:120px!important;max-height:120px!important;box-sizing:border-box;border-radius:var(--ha-card-border-radius,14px);overflow:hidden}
    ha-card.launcher-vertical{height:120px!important;min-height:120px!important;max-height:120px!important}
    button{box-sizing:border-box;width:100%;height:120px!important;min-height:120px!important;max-height:120px!important;border:0;border-radius:inherit;padding:8px;display:flex;align-items:center;justify-content:center;gap:10px;cursor:pointer;background:transparent;color:var(--primary-text-color);font:inherit;font-weight:600}
    button:hover{background:var(--secondary-background-color)}button:focus-visible{outline:2px solid var(--primary-color);outline-offset:-3px}
    ha-icon{color:var(--primary-color);--mdc-icon-size:25px}
    .launcher-visual{min-width:0;display:flex;align-items:center;justify-content:center}
    .launcher-logo{display:block;width:120px;max-width:100%;height:auto;max-height:38px;object-fit:contain}
    .launcher-vertical-logo{display:block;width:auto;max-width:100%;height:104px;max-height:104px;object-fit:contain}
    .launcher-logo,.launcher-vertical-logo,.launcher-mark{filter:var(--nuvio-logo-contrast,none)}
    .launcher-mark{display:block;width:auto;height:46px;max-width:100%;object-fit:contain}
    .launcher-caption{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
    .launcher-vertical button{flex-direction:column;gap:0;padding:8px}
    .launcher-vertical .launcher-caption{font-size:13px;line-height:17px;max-width:100%}
  </style><ha-card class="launcher-${style}"><button type="button" aria-label="Open Nuvio"><span class="launcher-visual"></span><span class="launcher-caption"></span></button></ha-card>`;
  const visual = this.shadowRoot.querySelector(".launcher-visual");
  if (style === "icon_text") {
    const selected = document.createElement("ha-icon");
    selected.setAttribute("icon", icon || "mdi:television-play");
    visual.appendChild(selected);
  } else {
    const logo = document.createElement("img");
    if (style === "vertical") {
      logo.className = "launcher-vertical-logo";
      logo.src = "/nuvio/assets/vertical.png?v=0.4.82";
    } else if (style === "logo_only") {
      logo.className = "launcher-mark";
      logo.src = "/nuvio/assets/icon-only.png?v=0.4.82";
    } else {
      logo.className = "launcher-logo";
      logo.src = "/nuvio/assets/wordmark.png?v=0.4.82";
    }
    logo.alt = "";
    logo.addEventListener("error", () => {
      const fallback = document.createElement("strong");
      fallback.textContent = style === "logo_only" ? "N" : "Nuvio";
      logo.replaceWith(fallback);
    });
    visual.appendChild(logo);
  }
  const caption = this.shadowRoot.querySelector(".launcher-caption");
  caption.textContent = label;
  // The uploaded vertical and logo-only assets already contain the complete
  // visual treatment. The horizontal wordmark also contains the default name.
  caption.style.display = ["vertical", "logo_only"].includes(style) || (style === "horizontal" && label.trim().toLowerCase() === "nuvio") ? "none" : "";
  this.shadowRoot.querySelector("button").addEventListener("click", () => this.openPopup());
}
  openPopup() {
    if (this._overlay) return;
    this._opener = this.shadowRoot.activeElement;
    const overlay = document.createElement("div");
    overlay.className = "nuvio-popup-overlay";
    overlay.dataset.size = this.popupSize();
    overlay.innerHTML = `<style>
      .nuvio-popup-overlay{position:fixed;inset:0;z-index:9999;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.65);padding:12px;box-sizing:border-box}
      .nuvio-popup-frame{width:min(1440px,calc(100vw - 24px));max-width:calc(100vw - 24px);height:min(900px,calc(100dvh - 24px));max-height:calc(100dvh - 24px);min-width:0;display:flex;flex-direction:column;overflow:hidden;border-radius:18px;background:var(--card-background-color,var(--ha-card-background,#fff));color:var(--primary-text-color);box-shadow:0 20px 75px rgba(0,0,0,.4)}
      .nuvio-popup-overlay[data-size="normal"] .nuvio-popup-frame{width:min(900px,calc(100vw - 24px));height:min(700px,calc(100dvh - 24px))}
      .nuvio-popup-overlay[data-size="fullscreen"]{padding:0}
      .nuvio-popup-overlay[data-size="fullscreen"] .nuvio-popup-frame{width:100%;max-width:100%;height:100%;max-height:100%;border-radius:0}
      .nuvio-popup-top{height:48px;min-height:48px;box-sizing:border-box;flex:0 0 48px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 12px 0 20px;border-bottom:1px solid var(--divider-color);font:600 16px var(--paper-font-body1_-_font-family,inherit)}
      .nuvio-popup-top button{box-sizing:border-box;flex:0 0 36px;width:36px;height:36px;display:grid;place-items:center;padding:0;border:0;border-radius:50%;cursor:pointer;background:var(--secondary-background-color);color:var(--primary-text-color)}
      .nuvio-popup-top button:focus-visible{outline:2px solid var(--primary-color)}
      .nuvio-popup-body{min-height:0;flex:1;overflow:auto;overscroll-behavior:contain}
      .nuvio-popup-body nuvio-card{display:block;min-height:100%}
      @media(max-width:600px){.nuvio-popup-overlay{padding:0}.nuvio-popup-frame,.nuvio-popup-overlay[data-size="normal"] .nuvio-popup-frame,.nuvio-popup-overlay[data-size="wide"] .nuvio-popup-frame{width:100%;max-width:100%;height:100%;max-height:100%;border-radius:0}.nuvio-popup-top{height:44px;min-height:44px;flex-basis:44px;padding:0 8px 0 12px}}
    </style><div class="nuvio-popup-frame" role="dialog" aria-modal="true" aria-label="Nuvio"><div class="nuvio-popup-top"><span>Nuvio</span><button type="button" aria-label="Close Nuvio popup"><ha-icon icon="mdi:close"></ha-icon></button></div><div class="nuvio-popup-body"></div></div>`;
    const content = overlay.querySelector(".nuvio-popup-body");
    const card = document.createElement("nuvio-card");
    this._overlay = overlay;
    this._popupCard = card;
    card.setConfig({...this._config, type: "custom:nuvio-card"});
    content.appendChild(card);
    (document.body || document.documentElement).appendChild(overlay);
    this._refreshPopupTheme();
    card.hass = this._hass;
    overlay.querySelector(".nuvio-popup-top button").addEventListener("click", () => this.closePopup());
    overlay.addEventListener("click", event => { if (event.target === overlay) this.closePopup(); });
    document.addEventListener("keydown", this._onKeydown, true);
    overlay.querySelector(".nuvio-popup-top button").focus();
    this.startAutoCloseTimer();
  }
  closePopup() {
    if (this._autoCloseTimer !== null) {
      clearTimeout(this._autoCloseTimer);
      this._autoCloseTimer = null;
    }
    document.removeEventListener("keydown", this._onKeydown, true);
    if (this._overlay) this._overlay.remove();
    this._overlay = null;
    this._popupCard = null;
    if (this._opener && this.isConnected) this._opener.focus();
    this._opener = null;
  }
  disconnectedCallback() { this.closePopup(); }
}

class NuvioPopupCardEditor extends HTMLElement {
  constructor() { super(); this.attachShadow({mode:"open"}); this._config={}; this._hass=null; }
  set hass(value) { this._hass=value; const editor=this.shadowRoot.querySelector("nuvio-card-editor"); if(editor) editor.hass=value; }
  setConfig(config) {
    const next={...config};
    const changed=JSON.stringify(this._config)!==JSON.stringify(next);
    this._config=next;
    if(!this.shadowRoot.querySelector('nuvio-card-editor')||
       (changed&&!this.matches(':focus-within')))this.render();
  }
  emit(config) {
    this._config={...config,type:"custom:nuvio-popup-card"};
    this.dispatchEvent(new CustomEvent("config-changed", {detail:{config:{...this._config}},bubbles:true,composed:true}));
  }
  render() {
    this.shadowRoot.innerHTML=`<style>:host{display:block;color:var(--primary-text-color)}.popup-options{display:flex;gap:12px;flex-wrap:wrap;padding:12px 4px;border-bottom:1px solid var(--divider-color)}label{display:flex;flex:1 1 170px;flex-direction:column;gap:6px;font-size:13px}input{padding:10px;border:1px solid var(--divider-color);border-radius:9px;background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit}</style><div class="popup-options"><label>Button label<input data-field="button_label" type="text"></label><label>Button icon (MDI, optional)<input data-field="button_icon" type="text" placeholder="mdi:television-play"><small>Used for Icon + text; leave blank for the default TV icon.</small></label><label>Button appearance<select data-field="button_style"><option value="vertical">Vertical logo</option><option value="horizontal">Horizontal logo</option><option value="logo_only">Logo only</option><option value="icon_text">Icon + text</option></select></label><label>Popup size<select data-field="popup_width"><option value="normal">Normal</option><option value="wide">Wide</option><option value="fullscreen">Full screen</option></select></label><label>Popup auto-close (minutes)<input data-field="popup_auto_close_minutes" type="number" min="0" step="any" value="2"><small>Default: 2 minutes after opening. Set 0 to disable.</small></label></div><nuvio-card-editor></nuvio-card-editor>`;
    for (const field of ["button_label","button_icon"]) {
      const input=this.shadowRoot.querySelector(`[data-field="${field}"]`);
      input.value=String(this._config[field] ?? (field==="button_label"?"Nuvio":""));
      input.addEventListener("change", () => this.emit({...this._config,[field]:input.value}));
    }
    const buttonStyle=this.shadowRoot.querySelector("select[data-field=button_style]");
  buttonStyle.value=["vertical","horizontal","logo_only","icon_text"].includes(this._config.button_style)
    ? this._config.button_style
    : (String(this._config.button_icon||"").trim()?"icon_text":"horizontal");
  buttonStyle.addEventListener("change",()=>this.emit({...this._config,button_style:buttonStyle.value}));
    const popupSize=this.shadowRoot.querySelector("select[data-field=popup_width]");
    popupSize.value=["normal","wide","fullscreen"].includes(this._config.popup_width)?this._config.popup_width:"wide";
    popupSize.addEventListener("change",()=>this.emit({...this._config,popup_width:popupSize.value}));
    const autoClose=this.shadowRoot.querySelector("input[data-field=popup_auto_close_minutes]");
    autoClose.value=String(this._config.popup_auto_close_minutes ?? 2);
    autoClose.addEventListener("change",()=>{
      const raw=autoClose.value.trim(),minutes=Number(raw);
      this.emit({...this._config,popup_auto_close_minutes:raw === "" || !Number.isFinite(minutes) || minutes < 0 ? 2 : minutes});
    });
    const editor=this.shadowRoot.querySelector("nuvio-card-editor");
    editor.addEventListener("config-changed", event => {event.stopPropagation();this.emit(event.detail.config);});
    editor.setConfig({...this._config,type:"custom:nuvio-card"});
    if(this._hass)editor.hass=this._hass;
  }
}
if(!customElements.get("nuvio-popup-card-editor"))customElements.define("nuvio-popup-card-editor",NuvioPopupCardEditor);
if(!customElements.get("nuvio-popup-card"))customElements.define("nuvio-popup-card",NuvioPopupCard);
window.customCards=window.customCards||[];
if(!window.customCards.some(card=>card.type==="nuvio-popup-card"))window.customCards.push({type:"nuvio-popup-card",name:"Nuvio Popup Button",description:"Open the full Nuvio catalog in a popup from a compact button.",preview:true});


/* Nuvio remote foreground bridge v1 */
function nuvioRaisePopupRemote(popup) {
  let portal=null, attributes=null, top=null, stopped=false;
  const find=()=>popup._popupCard?._remoteExpanded ? document.getElementById('nuvio-remote-portal') : null;
  function dismiss() {
    const dialog=top;top=null;
    if(!dialog)return;
    if(portal?.parentNode===dialog && portal.isConnected)document.body.appendChild(portal);
    if(dialog.open)dialog.close();
    dialog.remove();
  }
  function sync() {
    if(stopped)return;
    const found=find();
    if(found!==portal){
      attributes?.disconnect();dismiss();portal=found;
      if(portal){attributes=new MutationObserver(sync);attributes.observe(portal,{attributes:true,attributeFilter:['hidden','style','class']});}
    }
    if(!portal?.isConnected || portal.hidden || getComputedStyle(portal).display==='none'){dismiss();return;}
    if(top)return;
    const dialog=document.createElement('dialog');top=dialog;
    dialog.className='nuvio-remote-front-dialog';
    dialog.style.cssText='position:fixed;inset:0;margin:0;padding:0;border:0;width:100vw;height:100dvh;max-width:100vw;max-height:100dvh;overflow:visible;background:transparent;color:inherit;';
    const style=document.createElement('style');
    style.textContent='.nuvio-remote-front-dialog::backdrop{background:transparent!important;backdrop-filter:none!important}';
    dialog.appendChild(style);
    dialog.addEventListener('cancel',event=>{
      event.preventDefault();
      const close=portal?.querySelector('.nuvio-remote-close');
      if(close)close.click();
      else if(popup._popupCard?._remoteExpanded)popup._popupCard.toggleRemote();
      queueMicrotask(sync);
    });
    const children=new MutationObserver(()=>queueMicrotask(sync));
    children.observe(dialog,{childList:true});
    dialog.addEventListener('close',()=>children.disconnect(),{once:true});
    document.body.appendChild(dialog);dialog.appendChild(portal);
    try{dialog.showModal();}
    catch(error){dismiss();console.error('Nuvio remote foreground:',error);}
  }
  const body=new MutationObserver(sync);body.observe(document.body,{childList:true});
  const onClick=()=>queueMicrotask(sync);
  document.addEventListener('click',onClick,true);
  function cleanup(){
    if(stopped)return;stopped=true;
    attributes?.disconnect();body.disconnect();
    document.removeEventListener('click',onClick,true);
    dismiss();
  }
  sync();return cleanup;
}
const nuvioPopupOpenForeground=NuvioPopupCard.prototype.openPopup;
NuvioPopupCard.prototype.openPopup=function(...args){
  const result=nuvioPopupOpenForeground.apply(this,args);
  if(this._overlay && !this._remoteForegroundCleanup)this._remoteForegroundCleanup=nuvioRaisePopupRemote(this);
  return result;
};
const nuvioPopupCloseForeground=NuvioPopupCard.prototype.closePopup;
NuvioPopupCard.prototype.closePopup=function(...args){
  this._remoteForegroundCleanup?.();this._remoteForegroundCleanup=null;
  return nuvioPopupCloseForeground.apply(this,args);
};
