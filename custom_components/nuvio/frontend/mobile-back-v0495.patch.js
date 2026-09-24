/* Nuvio v0.4.95: keep navigation owned by the active popup throughout loading and teardown. */
(() => {
  const Card = customElements.get('nuvio-card');
  const Popup = customElements.get('nuvio-popup-card');
  if (!Card || !Popup) throw new Error('Nuvio Back: card not registered');
  const mobile = () => navigator.maxTouchPoints > 0 || matchMedia('(pointer:coarse)').matches;
  const manager = window.__fvHaCardBackManagerV2 ||= (() => {
    const owners = [];
    let token = null, url = null, armed = false, unwinding = false;
    let handling = false, requested = false, lastHandled = 0;
    const current = () => armed && history.state?.__fvCardBackV2 === token;
    const disarm = () => {
      if (owners.length || unwinding) return;
      armed = false; requested = false;
      window.removeEventListener('popstate', onPop, true);
    };
    const arm = () => {
      if (!owners.length || armed || unwinding) return;
      url = location.href;
      token = 'fv-back-' + Math.random().toString(36).slice(2);
      try {
        history.pushState({ ...(history.state || {}), __fvCardBackV2: token }, '', url);
        armed = true; requested = false;
      } catch (error) { console.warn('Card Back: history protection unavailable', error); }
    };
    const unwind = () => {
      if (owners.length || unwinding) return;
      if (!current()) { disarm(); return; }
      unwinding = true;
      requested = false;
      try { history.back(); } catch (error) { unwinding = false; disarm(); }
    };
    function onPop(event) {
      if (unwinding) {
        if (location.href === url) event.stopImmediatePropagation();
        unwinding = false; armed = false; requested = false;
        if (owners.length) arm(); else disarm();
        return;
      }
      if (!armed || !owners.length) return;
      if (location.href !== url) { // A genuine Home Assistant route change, not a card Back action.
        owners.length = 0; armed = false; requested = false; disarm(); return;
      }
      event.stopImmediatePropagation();
      requested = false; lastHandled = Date.now();
      // The browser may have popped into an older guard after an HA history update.
      armed = history.state?.__fvCardBackV2 === token;
      const owner = owners[owners.length - 1];
      handling = true;
      try { owner.back(); } finally { handling = false; }
      if (owners.length) { if (!armed) arm(); }
      else if (armed) unwind(); else disarm();
    }
    return {
      add(owner) {
        if (!mobile() || owners.includes(owner)) return;
        if (!owners.length && !unwinding) window.addEventListener('popstate', onPop, true);
        owners.push(owner); arm();
      },
      remove(owner) {
        const index = owners.indexOf(owner);
        if (index < 0) return;
        owners.splice(index, 1);
        if (!owners.length && !handling) unwind();
      },
      request(owner) {
        if (!owners.length || owners[owners.length - 1] !== owner) return false;
        if (requested || Date.now() - lastHandled < 300) return true;
        if (current()) {
          requested = true;
          try { history.back(); } catch (error) { requested = false; owner.back(); }
        } else {
          lastHandled = Date.now();
          owner.back();
          if (owners.length && !armed) arm();
        }
        return true;
      },
    };
  })();
  const nested = card => !!card && (card._view !== 'home' || !!card._remoteExpanded);
  function step(card) {
    if (!card) return false;
    if (card._remoteExpanded) { card.toggleRemote(); return true; }
    if (card._view === 'sources') {
      card._view = card._sourcesBackView || 'details'; card._error = ''; card.render(); return true;
    }
    if (card._view === 'details') {
      card._view = card._returnView || 'home'; card._error = ''; card.render(); return true;
    }
    if (card._view === 'search' || card._view === 'catalog') { void card.goHome(); return true; }
    return false;
  }
  const oldOpen = Popup.prototype.openPopup;
  const oldClose = Popup.prototype.closePopup;
  Popup.prototype.openPopup = function (...args) {
    if (!this._fvBackKeyInstalled) {
      this._fvBackKeyInstalled = true;
      this._onKeydown = event => {
        if (event.key !== 'Escape' || !this._overlay) return;
        event.preventDefault(); event.stopImmediatePropagation();
        if (this._fvBackOwner && manager.request(this._fvBackOwner)) return;
        if (!step(this._popupCard)) this.closePopup();
      };
    }
    const result = oldOpen.apply(this, args);
    if (this._overlay && !this._fvBackOwner) {
      const owner = { back: () => { if (!step(this._popupCard)) this.closePopup(); } };
      this._fvBackOwner = owner;
      manager.add(owner);
    }
    return result;
  };
  Popup.prototype.closePopup = function (...args) {
    if (this._fvBackOwner) { manager.remove(this._fvBackOwner); this._fvBackOwner = null; }
    return oldClose.apply(this, args);
  };
  const oldRender = Card.prototype.render;
  Card.prototype.render = function (...args) {
    const result = oldRender.apply(this, args);
    if (!mobile() || !this.isConnected || this.closest('.nuvio-popup-body')) return result;
    if (nested(this)) {
      if (!this._fvBackOwner) this._fvBackOwner = { back: () => step(this) };
      manager.add(this._fvBackOwner);
    } else if (this._fvBackOwner) { manager.remove(this._fvBackOwner); this._fvBackOwner = null; }
    return result;
  };
  const oldDisconnect = Card.prototype.disconnectedCallback;
  Card.prototype.disconnectedCallback = function (...args) {
    if (this._fvBackOwner) { manager.remove(this._fvBackOwner); this._fvBackOwner = null; }
    return oldDisconnect?.apply(this, args);
  };
})();
