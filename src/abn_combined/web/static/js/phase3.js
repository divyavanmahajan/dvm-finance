// Alpine components for Phase 3 enhancements:
// 1. categoryPicker() — manages category filter dropdown with search
// 2. Pagination handling via HTMX

document.addEventListener('alpine:init', () => {
  // ===== Category Picker Component (Phase 3) =====
  // Manages the category checkbox-dropdown with search filtering
  window.Alpine.data('categoryPicker', (allCategories, initialSelected) => ({
    selected: initialSelected || [],
    searchQuery: '',
    allCats: allCategories,

    /**
     * Filtered categories based on search query
     */
    get filtered() {
      if (!this.searchQuery.trim()) {
        return this.allCats;
      }
      const q = this.searchQuery.toLowerCase();
      return this.allCats.filter(cat => cat.toLowerCase().includes(q));
    },

    /**
     * Return button text showing selection state
     * Shows "N selected" if some are selected, "All categories" if all, "Categories" if none
     */
    buttonText() {
      if (this.selected.length === 0) {
        return 'Categories';
      }
      if (this.selected.length === this.allCats.length + 1) { // +1 for "uncategorized"
        return 'All categories';
      }
      return `${this.selected.length} selected`;
    },

    /**
     * Toggle a category's selection
     */
    toggleCategory(categoryId) {
      const idx = this.selected.indexOf(categoryId);
      if (idx > -1) {
        this.selected.splice(idx, 1);
      } else {
        this.selected.push(categoryId);
      }
      this.updateHiddenInputs();
    },

    /**
     * Sync selected array to hidden form inputs
     * Ensures filter-bar form has the correct checkbox states
     */
    updateHiddenInputs() {
      // Find all category checkboxes in the main filter form
      const categoryInputs = document.querySelectorAll('input[name="category"][form="filter-bar"]');
      categoryInputs.forEach(input => {
        input.checked = this.selected.includes(input.value);
      });

      // Trigger form submission to update the table
      const filterForm = document.getElementById('filter-bar');
      if (filterForm) {
        // Use HTMX to trigger the form submission
        htmx.trigger(filterForm, 'change');
      }
    },

    /**
     * Clear all selected categories
     */
    clearCategories() {
      this.selected = [];
      this.updateHiddenInputs();
    },

    /**
     * Slugify category name for use as HTML id
     */
    slugify(text) {
      return text.toLowerCase().replace(/\s+/g, '-').replace(/[^\w-]/g, '');
    },
  }));

  // ===== Pagination Handler (Phase 3) =====
  // Manages page size selector and pagination click handling
  window.Alpine.data('paginationHandler', () => ({
    pageSize: 20, // Default page size

    /**
     * Handle page size change
     * Updates URL with new page_size query param and fetches table
     */
    changePageSize(newSize) {
      const url = new URL(window.location.href);
      url.searchParams.set('page_size', newSize);
      url.searchParams.set('page', '1'); // Reset to first page
      this.pageSize = newSize;
      htmx.ajax('GET', '/transactions/table?' + url.searchParams.toString(), '#txn-table');
    },

    /**
     * Navigate to a specific page
     * Called by pagination links via HTMX
     */
    goToPage(pageNum) {
      const url = new URL(window.location.href);
      url.searchParams.set('page', pageNum);
      htmx.ajax('GET', '/transactions/table?' + url.searchParams.toString(), '#txn-table');
    },
  }));
});

// ===== Transaction Detail Expand/Collapse (Phase 3) =====
// For mobile cards: toggle detail visibility with smooth animation
document.addEventListener('alpine:init', () => {
  window.Alpine.data('txnCardDetail', () => ({
    expanded: false,
    init() {
      // This will be used in the mobile card template
    },
  }));
});

// ===== Utility: Smooth scroll to element =====
function scrollToElement(selector) {
  const el = document.querySelector(selector);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

// ===== HTMX Extensions =====
// Ensure pagination links and category updates integrate seamlessly with HTMX

// On HTMX after-swap, reinitialize any Alpine components in the new content
document.addEventListener('htmx:afterSwap', function(evt) {
  if (evt.detail.target.id === 'txn-table') {
    // Reinitialize Alpine for any new content
    Alpine.scan(evt.detail.target);
    // Smooth scroll to table
    scrollToElement('#txn-table');
  }
});

// On HTMX request, show loading indicator
document.addEventListener('htmx:xhr:progress', function(evt) {
  const indicator = document.getElementById('txn-loading');
  if (indicator) {
    indicator.style.display = 'block';
  }
});

// On HTMX request complete, hide loading indicator
document.addEventListener('htmx:afterSettle', function(evt) {
  const indicator = document.getElementById('txn-loading');
  if (indicator) {
    indicator.style.display = 'none';
  }
});
