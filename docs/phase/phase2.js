/**
 * Phase 2: Alpine.js Filter Management Component
 *
 * Manages advanced filter state, active filter pills, clear/reset logic,
 * and form field synchronization. Filter state always lives in the URL query string
 * (Golden Principle 8); this component controls UI state and form interactions.
 *
 * Usage: attach to form with x-data="txnFilterBar()"
 */

document.addEventListener('alpine:init', () => {
  window.Alpine.data('txnFilterBar', () => ({
    // UI state (not filter state — that lives in the URL)
    showAdvancedFilters: false,

    // Active filters derived from URL params
    activeFilters: [],
    activeFilterCount: 0,

    /**
     * Initialize component: scan URL params and build activeFilters array,
     * auto-expand advanced filters if any are active.
     */
    init() {
      this.syncFiltersFromUrl();
      this.autoExpandAdvancedIfNeeded();

      // Watch for URL changes (browser back/forward)
      window.addEventListener('popstate', () => this.syncFiltersFromUrl());
    },

    /**
     * Scan URL query params and build activeFilters array.
     * Maps URL params to human-readable filter labels and values.
     */
    syncFiltersFromUrl() {
      const params = new URLSearchParams(window.location.search);
      const filters = [];

      // Date range
      if (params.has('date_from') || params.has('date_to')) {
        const from = params.get('date_from') || '';
        const to = params.get('date_to') || '';
        const dateRange = [from, to].filter(v => v).join(' – ');
        if (dateRange) {
          filters.push({
            key: 'date_range',
            label: 'Date',
            value: dateRange
          });
        }
      }

      // Amount range
      if (params.has('amount_min') || params.has('amount_max')) {
        const min = params.get('amount_min') || '';
        const max = params.get('amount_max') || '';
        const amountRange = [min, max].filter(v => v).map(v => `€${v}`).join(' – ');
        if (amountRange) {
          filters.push({
            key: 'amount_range',
            label: 'Amount',
            value: amountRange
          });
        }
      }

      // Account
      if (params.has('account')) {
        filters.push({
          key: 'account',
          label: 'Account',
          value: params.get('account')
        });
      }

      // Categories (can be multiple)
      const categories = params.getAll('category') || [];
      if (categories.length > 0) {
        filters.push({
          key: 'category',
          label: 'Categories',
          value: categories.join(', ')
        });
      }

      // Exclude categories
      const excludeCategories = params.getAll('exclude_category') || [];
      if (excludeCategories.length > 0) {
        filters.push({
          key: 'exclude_category',
          label: 'Exclude',
          value: excludeCategories.join(', ')
        });
      }

      // Tags (can be multiple)
      const tags = params.getAll('tag') || [];
      if (tags.length > 0) {
        filters.push({
          key: 'tag',
          label: 'Tags',
          value: tags.join(', ')
        });
      }

      this.activeFilters = filters;
      this.activeFilterCount = filters.length;
    },

    /**
     * Auto-expand advanced filters if any advanced filter is already active
     * (e.g., when a bookmarked URL with filters is loaded).
     */
    autoExpandAdvancedIfNeeded() {
      const advancedKeys = ['date_from', 'date_to', 'amount_min', 'amount_max', 'account', 'category', 'tag', 'exclude_category'];
      const params = new URLSearchParams(window.location.search);
      this.showAdvancedFilters = advancedKeys.some((k) => params.has(k));
    },

    /**
     * Remove a single filter by key.
     * Clears the form field(s) for that filter and resubmits the form via HTMX.
     */
    removeFilter(key) {
      const form = document.getElementById('filter-bar');
      if (!form) return;

      // Map filter keys to form input names
      const fieldMap = {
        'date_range': ['date_from', 'date_to'],
        'amount_range': ['amount_min', 'amount_max'],
        'account': ['account'],
        'category': ['category'],
        'exclude_category': ['exclude_category'],
        'tag': ['tag']
      };

      const fields = fieldMap[key] || [];
      fields.forEach(name => {
        const inputs = form.querySelectorAll(`[name="${name}"]`);
        inputs.forEach(input => {
          if (input.type === 'checkbox') {
            input.checked = false;
          } else {
            input.value = '';
          }
        });
      });

      // Trigger form submission via HTMX
      this.submitForm();
    },

    /**
     * Clear all filters: reset all form fields and resubmit.
     */
    clearFilters() {
      const form = document.getElementById('filter-bar');
      if (!form) return;

      // Reset all inputs except the search and sort
      const preserveFields = ['q', 'sort', 'preset'];
      const inputs = form.querySelectorAll('input, select');
      inputs.forEach(input => {
        if (!preserveFields.includes(input.name)) {
          if (input.type === 'checkbox') {
            input.checked = false;
          } else {
            input.value = '';
          }
        }
      });

      // Trigger form submission via HTMX
      this.submitForm();
    },

    /**
     * Manually trigger the form submission.
     * HTMX will capture the form state and submit via the configured hx-get endpoint.
     */
    submitForm() {
      const form = document.getElementById('filter-bar');
      if (!form) return;

      // Trigger the HTMX request by simulating a change event
      // or by directly calling htmx.ajax() with the form's configuration
      htmx.ajax('GET', '/transactions/table', {
        target: '#txn-table',
        swap: 'innerHTML',
        // Include all form data
        headers: { 'HX-Request': 'true' },
        // Serialize the form and pass as query string
        values: Object.fromEntries(new FormData(form))
      });

      // Push URL to reflect the new filter state
      const params = new URLSearchParams(new FormData(form));
      window.history.pushState({}, '', `/?${params.toString()}`);
    },

    /**
     * Sync form field when user changes an input in the offcanvas.
     * Called on change events from form controls.
     */
    onFilterChange() {
      // The form's built-in hx-trigger will handle the submission
      // This is just a hook if you need custom logic
      this.syncFiltersFromUrl();
    },

    /**
     * Get all selected categories from the form (for display in empty state).
     */
    getSelectedCategories() {
      const form = document.getElementById('filter-bar');
      if (!form) return [];
      const checkboxes = form.querySelectorAll('input[name="category"]:checked');
      return Array.from(checkboxes).map(cb => cb.value);
    },

    /**
     * Format a date for display (ISO format to readable format).
     */
    formatDate(isoDate) {
      if (!isoDate) return '';
      const date = new Date(isoDate + 'T00:00:00');
      return date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
    }
  }));
});

/**
 * HTMX Event Listener: Sync filters after successful form submission.
 * When the table partial is swapped, update the activeFilters array.
 */
document.addEventListener('htmx:afterSwap', (evt) => {
  if (evt.detail.target.id === 'txn-table') {
    // Get the Alpine component from the form and resync
    const form = document.getElementById('filter-bar');
    if (form && form.__x) {
      form.__x.syncFiltersFromUrl();
    }
  }
});

/**
 * Optional: Keyboard shortcuts
 * - Escape to close the offcanvas
 * - Ctrl+K to focus search
 */
document.addEventListener('keydown', (evt) => {
  // Escape closes offcanvas
  if (evt.key === 'Escape') {
    const offcanvas = document.getElementById('advancedFiltersOffcanvas');
    if (offcanvas) {
      const bsOffcanvas = bootstrap.Offcanvas.getInstance(offcanvas);
      if (bsOffcanvas) bsOffcanvas.hide();
    }
  }

  // Ctrl+K focuses search input
  if ((evt.ctrlKey || evt.metaKey) && evt.key === 'k') {
    evt.preventDefault();
    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.focus();
  }
});
