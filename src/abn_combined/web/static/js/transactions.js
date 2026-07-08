// Alpine component for the transactions filter bar.
// Filter *state* never lives here — it always lives in the URL query string
// (Golden Principle 8). This only controls the "more filters" disclosure and
// the multi-select dropdowns' open/closed UI state.
document.addEventListener('alpine:init', () => {
  window.Alpine.data('txnFilterBar', () => ({
    advanced: false,
    init() {
      // Auto-expand the advanced row if any advanced filter is already active
      // so a reloaded bookmarked URL shows its filters.
      const p = new URLSearchParams(window.location.search);
      const advancedKeys = ['date_from', 'date_to', 'amount_min', 'amount_max', 'account', 'category', 'tag'];
      this.advanced = advancedKeys.some((k) => p.has(k));
    },
  }));
});
