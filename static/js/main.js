// CryptoSim global utilities

// Keep nav wallet updated on all pages if not handled by page scripts
(async function initNav() {
  try {
    const state = await fetch('/api/state').then(r => r.json());
    const el = document.getElementById('nav-wallet');
    if (el) el.textContent = '$' + state.wallet.toFixed(2);
  } catch(e) {}
})();
