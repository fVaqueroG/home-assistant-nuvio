/* Nuvio v0.4.94: mobile Back navigates the active card before the HA route. */
(() => {
  const Card = customElements.get('nuvio-card');
  const Popup = customElements.get('nuvio-popup-card');
  if (!Card || !Popup) throw new Error('Nuvio mobile Back: card and popup must be registered');
  const mobile = () => navigator.maxTouchPoints > 0 || matchMedia('(pointer: coarse)').matches;
  const stack = () => (window.__fvHaCardBackStack ||= []);
  const nested = card => !!card && (card._view !== 'home' || !!card._remoteExpanded);

  function step(card) {
    if (!card) return false;
    if (card._remoteExpanded) { card.toggleRemote(); return true; }
    if (card._view === 'sources') {
      card._view = card._sourcesBackView || 'details';
      card._error = '';
      card.render();
      return true;
    }
    if (card._view === 'details') {
      card._view = card._returnView || 'home';
      card._error = '';
      card.render();
      return true;
    }
    if (card._view === 'search' || card._view === 'catalog') {
      void card.goHome();
      return true;
    }
    return false;
  }

  function bridge(isOpen, onBack) {
    const id = 'nuvio-' + Math.random().toString(36).slice(2);
    let active = false, armed = false, url = '';
    const isTop = () => stack()[stack().length - 1] === api;
    const arm = () => {
      if (!active || armed || !isOpen()) return;
      try {
        history.pushState({ ...(history.state || {}), __fvHaCardBackId: id }, '', location.href);
        armed = true;
      } catch (error) { console.warn('Nuvio: mobile Back history not available', error); }
    };
    const pop = event => {
      if (!active || !armed || !isTop() || !isOpen()) return;
      if (history.state?.__fvHaCardBackId === id) return; // Another overlay's history entry was popped.
      armed = false;
      if (location.href !== url) { api.stop(false); return; } // Real HA navigation must be allowed.
      event.stopImmediatePropagation();
      onBack();
      if (isOpen()) arm();
      else api.stop(false);
    };
    const api = {
      start() {
        if (active || !mobile() || !isOpen()) return;
        active = true;
        url = location.href;
        stack().push(api);
        window.addEventListener('popstate', pop, true);
        arm();
      },
      stop(rewind = true) {
        if (!active) return;
        active = false;
        window.removeEventListener('popstate', pop, true);
        const owners = stack(), index = owners.indexOf(api);
        if (index >= 0) owners.splice(index, 1);
        if (rewind && armed && history.state?.__fvHaCardBackId === id) {
          armed = false;
          history.back(); // Remove our same-URL guard when the user closes the popup.
        }
        armed = false;
      },
    };
    return api;
  }

  const oldOpen = Popup.prototype.openPopup;
  const oldClose = Popup.prototype.closePopup;
  Popup.prototype.openPopup = function (...args) {
    if (!this._mobileBackEscape) {
      this._mobileBackEscape = true;
      this._onKeydown = event => {
        if (event.key !== 'Escape' || !this._overlay) return;
        event.preventDefault();
        event.stopImmediatePropagation();
        if (!step(this._popupCard)) this.closePopup();
      };
    }
    const result = oldOpen.apply(this, args);
    if (this._overlay && !this._mobileBackBridge) {
      this._mobileBackBridge = bridge(
        () => !!this._overlay?.isConnected,
        () => { if (!step(this._popupCard)) this.closePopup(); }
      );
      this._mobileBackBridge.start();
    }
    return result;
  };
  Popup.prototype.closePopup = function (...args) {
    this._mobileBackBridge?.stop();
    this._mobileBackBridge = null;
    return oldClose.apply(this, args);
  };
  const oldRender = Card.prototype.render;
  Card.prototype.render = function (...args) {
    const result = oldRender.apply(this, args);
    // Standalone cards also get hardware Back, but only while inside a nested view.
    // The popup owns the history guard for its embedded card, preventing two guards.
    if (mobile() && this.isConnected && !this.closest('.nuvio-popup-body')) {
      if (nested(this)) {
        if (!this._mobileBackBridge) this._mobileBackBridge = bridge(
          () => this.isConnected && nested(this),
          () => { step(this); }
        );
        this._mobileBackBridge.start();
      } else {
        this._mobileBackBridge?.stop();
        this._mobileBackBridge = null;
      }
    }
    return result;
  };
  const oldDisconnected = Card.prototype.disconnectedCallback;
  Card.prototype.disconnectedCallback = function (...args) {
    this._mobileBackBridge?.stop();
    this._mobileBackBridge = null;
    return oldDisconnected?.apply(this, args);
  };
})();
