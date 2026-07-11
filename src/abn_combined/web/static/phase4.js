/**
 * Phase 4 Polish: Dark Mode, Toasts, Skeleton Loaders, Print Utilities
 *
 * Features:
 * - Dark mode toggle (localStorage + data-theme attribute)
 * - Toast notification system (HX-Trigger header listener)
 * - Skeleton loader injection for slow loads
 * - Tooltip re-initialization after HTMX swaps
 * - Print utilities and view transitions
 */

// ============================================================================
// DARK MODE TOGGLE
// ============================================================================
window.darkModeToggle = function() {
  return {
    dark: localStorage.getItem('theme') === 'dark' || false,

    init() {
      // Sync with localStorage on page load
      this.dark = localStorage.getItem('theme') === 'dark';
      this.applyTheme();
    },

    toggle() {
      this.dark = !this.dark;
      this.applyTheme();
      localStorage.setItem('theme', this.dark ? 'dark' : 'light');
      // Fire custom event for logging/analytics
      window.dispatchEvent(new CustomEvent('theme-changed', { detail: { dark: this.dark } }));
    },

    applyTheme() {
      const theme = this.dark ? 'dark' : 'light';
      document.documentElement.setAttribute('data-theme', theme);
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        document.documentElement.style.colorScheme = theme;
      }
    },
  };
};

// Apply dark mode on page load
document.addEventListener('DOMContentLoaded', () => {
  const savedTheme = localStorage.getItem('theme');
  if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
  }
});

// ============================================================================
// TOAST NOTIFICATION SYSTEM
// ============================================================================

class ToastManager {
  constructor() {
    this.container = document.getElementById('toast-container') || this.createContainer();
    this.toastTemplate = document.getElementById('toast-template');
    this.activeToasts = new Map();
  }

  createContainer() {
    const container = document.createElement('div');
    container.id = 'toast-container';
    container.className = 'toast-container';
    container.setAttribute('aria-live', 'polite');
    container.setAttribute('aria-atomic', 'true');
    document.body.appendChild(container);
    return container;
  }

  /**
   * Show a toast notification
   * @param {string} message - Notification text
   * @param {string} type - 'success', 'info', 'warning', or 'error'
   * @param {number} duration - Auto-dismiss time in ms (default 4000)
   */
  show(message, type = 'info', duration = 4000) {
    const id = Math.random().toString(36).substr(2, 9);

    // Clone template or create new toast
    let toast;
    if (this.toastTemplate) {
      toast = this.toastTemplate.content.cloneNode(true).querySelector('.toast');
    } else {
      toast = document.createElement('div');
      toast.className = 'toast';
      toast.innerHTML = `
        <span class="toast-icon" aria-hidden="true"></span>
        <span class="toast-message"></span>
        <button class="toast-close" aria-label="Close notification" type="button">✕</button>
      `;
    }

    toast.id = `toast-${id}`;
    toast.className = `toast ${type}`;
    toast.setAttribute('role', 'status');
    toast.setAttribute('data-id', id);

    const messageEl = toast.querySelector('.toast-message');
    if (messageEl) messageEl.textContent = message;

    const closeBtn = toast.querySelector('.toast-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', () => this.dismiss(id));
    }

    this.container.appendChild(toast);
    this.activeToasts.set(id, { element: toast, timer: null });

    // Auto-dismiss
    if (duration > 0) {
      const timer = setTimeout(() => this.dismiss(id), duration);
      this.activeToasts.get(id).timer = timer;
    }

    return id;
  }

  /**
   * Dismiss and remove a toast
   */
  dismiss(id) {
    const toast = this.activeToasts.get(id);
    if (!toast) return;

    clearTimeout(toast.timer);
    toast.element.classList.add('dismissing');

    setTimeout(() => {
      if (toast.element.parentNode) {
        toast.element.parentNode.removeChild(toast.element);
      }
      this.activeToasts.delete(id);
    }, 300); // matches animation duration
  }

  /**
   * Dismiss all active toasts
   */
  dismissAll() {
    for (const id of this.activeToasts.keys()) {
      this.dismiss(id);
    }
  }
}

// Global toast manager instance
window.toastManager = new ToastManager();

// Listen for HTMX responses with HX-Trigger headers to show toasts
document.addEventListener('htmx:afterSwap', (e) => {
  const xhr = e.detail.xhr;
  if (!xhr) return;

  // Check for HX-Trigger header with toast data
  // Format: "toastShown:success:Filters applied" or simple "filterApplied"
  const hxTrigger = xhr.getResponseHeader('HX-Trigger');
  if (!hxTrigger) return;

  try {
    const triggers = JSON.parse(hxTrigger);
    if (triggers.toast) {
      const [type, message] = triggers.toast.split(':', 2);
      window.toastManager.show(message, type || 'info');
    }
  } catch (e) {
    // Header might be a simple string, not JSON
    // Common triggers: filterApplied, ruleUpdated, rulesApplied, uploaded, etc.
    const message = getTriggerMessage(hxTrigger);
    if (message) {
      window.toastManager.show(message, 'info');
    }
  }
});

// Helper: map trigger names to user-friendly messages
function getTriggerMessage(trigger) {
  const messages = {
    'filterApplied': 'Filters applied',
    'filterCleared': 'Filters cleared',
    'ruleCreated': 'Rule created',
    'ruleUpdated': 'Rule updated',
    'ruleDeleted': 'Rule deleted',
    'rulesApplied': 'Rules applied',
    'categorized': 'Transaction categorized',
    'uploaded': 'File uploaded successfully',
    'snapshotExported': 'Snapshot exported',
    'snapshotImported': 'Snapshot imported',
    'budgetUpdated': 'Budget updated',
    'tagAdded': 'Tag added',
    'tagRemoved': 'Tag removed',
  };
  return messages[trigger] || null;
}

// ============================================================================
// SKELETON LOADER INJECTION
// ============================================================================

/**
 * Inject skeleton loader rows before HTMX request
 * Use on table targets: hx-confirm="..." hx-on="htmx:beforeRequest: showSkeletons('#target')"
 */
window.showSkeletons = function(selector, rowCount = 3) {
  const target = document.querySelector(selector);
  if (!target) return;

  const template = document.getElementById('skeleton-row-template');
  if (!template) {
    console.warn('Skeleton template not found');
    return;
  }

  // Clone skeleton template
  const skeleton = template.content.cloneNode(true);
  target.appendChild(skeleton);
};

/**
 * Alternative: inject skeletons via HTMX event
 * htmx:beforeRequest listener that swaps in placeholders
 */
document.addEventListener('htmx:beforeRequest', (e) => {
  // Check for data-show-skeleton attribute on the element
  if (!e.detail.xhr.responseType && e.detail.elt.hasAttribute('data-show-skeleton')) {
    const target = document.querySelector(e.detail.elt.getAttribute('hx-target'));
    if (target) {
      showSkeletons(e.detail.elt.getAttribute('hx-target'));
    }
  }
});

// ============================================================================
// TOOLTIP RE-INITIALIZATION (after HTMX swaps)
// ============================================================================

/**
 * Re-initialize tooltips after HTMX content swap
 * Call this after any dynamic content insertion.
 * Works with Pico's data-tooltip or Bootstrap tooltips if migrated.
 */
window.reinitTooltips = function() {
  // For Bootstrap tooltips (if migrated to Bootstrap 5):
  if (window.bootstrap && window.bootstrap.Tooltip) {
    const tooltipTriggerList = [].slice.call(
      document.querySelectorAll('[data-bs-toggle="tooltip"]')
    );
    tooltipTriggerList.forEach((tooltipTriggerEl) => {
      new bootstrap.Tooltip(tooltipTriggerEl);
    });
  }

  // For Pico data-tooltip (native):
  // Pico handles this automatically via CSS, so no JS needed.
  // But if custom tooltips are added, update them here.
};

// Re-init tooltips after HTMX content swap
document.addEventListener('htmx:afterSwap', () => {
  window.reinitTooltips();
});

// Initial tooltip setup on page load
document.addEventListener('DOMContentLoaded', () => {
  window.reinitTooltips();
});

// ============================================================================
// CHIP REMOVAL WITH TRANSITION
// ============================================================================

/**
 * Add fade-out animation before chip removal via HTMX
 * Call on chip click: @click="fadeOutChip(this)"
 */
window.fadeOutChip = function(element) {
  element.classList.add('removing');
  // HTMX request will trigger after animation (300ms)
  // Adjust timing to match CSS animation duration
  setTimeout(() => {
    element.click(); // Trigger HTMX
  }, 200);
};

// Alternative: use HTMX events
document.addEventListener('htmx:beforeRequest', (e) => {
  if (e.detail.elt && e.detail.elt.classList.contains('chip')) {
    e.detail.elt.classList.add('removing');
  }
});

// ============================================================================
// PRINT UTILITIES
// ============================================================================

/**
 * Prepare page for printing:
 * - Hide UI elements
 * - Show filter summary
 * - Optimize table layout
 */
window.preparePrint = function() {
  // Browser print dialog will use @media print CSS
  window.print();
};

/**
 * Add "Print" button to navbar or utilities
 * <button @click="preparePrint()" class="icon-button" title="Print page">🖨️</button>
 */

// ============================================================================
// VIEW TRANSITIONS (Optional Progressive Enhancement)
// ============================================================================

/**
 * Enable smooth view transitions on HTMX table updates
 * Requires CSS @supports (view-transition-name: root)
 * Use: hx-swap="innerHTML transition:true"
 */
document.addEventListener('htmx:beforeSwap', (e) => {
  // Check if view-transitions are supported
  if (!('startViewTransition' in document)) {
    return;
  }

  // Only apply to table updates
  if (!e.detail.target.classList.contains('txn-table') &&
      !e.detail.target.id.includes('table')) {
    return;
  }

  // Wrap swap in view transition
  document.startViewTransition(() => {
    // The swap will happen here
  });
});

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', () => {
  console.debug('[Phase4] Initialized: Dark Mode, Toasts, Skeletons, Tooltips');

  // Test toast system (remove in production)
  // window.toastManager.show('Welcome to Phase 4 Polish!', 'info', 5000);
});

// ============================================================================
// EXPORTS for Testing
// ============================================================================
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    ToastManager,
    darkModeToggle: window.darkModeToggle,
    reinitTooltips: window.reinitTooltips,
    preparePrint: window.preparePrint,
    showSkeletons: window.showSkeletons,
  };
}
