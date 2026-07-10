/**
 * Phase 4: Polish & UX Enhancements
 *
 * Features:
 * - Dark mode toggle with localStorage persistence
 * - Toast notifications triggered by HX-Trigger headers
 * - Skeleton loaders for slow loads
 * - Print styles integration
 * - View transitions for smooth animations
 * - Accessibility helpers (tooltips, reduced-motion)
 */

/* ===== DARK MODE TOGGLE ===== */

document.addEventListener('alpine:init', () => {
  window.Alpine.data('darkModeToggle', () => ({
    dark: localStorage.getItem('theme') === 'dark',

    init() {
      // Apply theme on load
      this.applyTheme();

      // Watch for system preference changes
      const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
      darkModeQuery.addEventListener('change', () => {
        if (!localStorage.getItem('theme')) {
          this.dark = darkModeQuery.matches;
          this.applyTheme();
        }
      });
    },

    toggle() {
      this.dark = !this.dark;
      localStorage.setItem('theme', this.dark ? 'dark' : 'light');
      this.applyTheme();
    },

    applyTheme() {
      const theme = this.dark ? 'dark' : 'light';
      // Pico CSS convention
      document.documentElement.setAttribute('data-theme', theme);
      // Bootstrap 5.3 convention
      document.documentElement.setAttribute('data-bs-theme', theme);
      document.documentElement.style.colorScheme = theme;
    }
  }));
});

/* ===== TOAST MANAGER ===== */

window.toastManager = {
  container: null,

  init() {
    this.container = document.getElementById('toast-container');
    if (!this.container) {
      this.container = document.createElement('div');
      this.container.id = 'toast-container';
      this.container.className = 'toast-container';
      this.container.setAttribute('aria-live', 'polite');
      document.body.appendChild(this.container);
    }
  },

  show(message, type = 'info', duration = 4000) {
    if (!this.container) this.init();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.innerHTML = `
      <div class="toast-body">
        ${message}
        <button type="button" class="toast-close" aria-label="Close">×</button>
      </div>
    `;

    this.container.appendChild(toast);

    // Auto-dismiss if duration > 0
    if (duration > 0) {
      setTimeout(() => this.dismiss(toast), duration);
    }

    // Close button handler
    toast.querySelector('.toast-close').addEventListener('click', () => {
      this.dismiss(toast);
    });

    return toast;
  },

  dismiss(toast) {
    if (toast) {
      toast.classList.add('toast-closing');
      setTimeout(() => toast.remove(), 300);
    }
  },

  dismissAll() {
    const toasts = this.container?.querySelectorAll('.toast');
    if (toasts) {
      toasts.forEach(toast => this.dismiss(toast));
    }
  },

  // Trigger mapping for common backend events
  triggerMap: {
    'filterApplied': { message: 'Filters applied', type: 'success', duration: 3000 },
    'filterCleared': { message: 'Filters cleared', type: 'info', duration: 3000 },
    'ruleCreated': { message: 'Rule created', type: 'success', duration: 3000 },
    'ruleUpdated': { message: 'Rule updated', type: 'success', duration: 3000 },
    'rulesApplied': { message: 'Rules applied', type: 'success', duration: 3000 },
    'categorized': { message: 'Transaction categorized', type: 'success', duration: 2000 },
    'uploaded': { message: 'File uploaded successfully', type: 'success', duration: 3000 },
    'snapshotExported': { message: 'Snapshot exported', type: 'success', duration: 3000 },
    'snapshotImported': { message: 'Snapshot imported', type: 'success', duration: 3000 },
    'error': { message: 'An error occurred', type: 'error', duration: 5000 }
  }
};

toastManager.init();

/* ===== HTMX TOAST INTEGRATION ===== */

document.addEventListener('htmx:afterSwap', (evt) => {
  const hxTrigger = evt.detail.xhr?.getResponseHeader('HX-Trigger');

  if (hxTrigger) {
    try {
      // Try to parse as JSON (custom message)
      const trigger = JSON.parse(hxTrigger);
      if (trigger.toast) {
        const [type, ...msgParts] = trigger.toast.split(':');
        const message = msgParts.join(':').trim() || 'Action completed';
        toastManager.show(message, type || 'info', 4000);
      }
    } catch {
      // Fall back to string lookup
      const config = toastManager.triggerMap[hxTrigger];
      if (config) {
        toastManager.show(config.message, config.type, config.duration);
      }
    }
  }
});

/* ===== SKELETON LOADERS ===== */

document.addEventListener('htmx:beforeRequest', (evt) => {
  const target = evt.detail.target;

  // Show skeleton loader if marked with data-show-skeleton
  if (target.dataset.showSkeleton === 'true') {
    const skeletonCount = parseInt(target.dataset.skeletonCount || '3', 10);
    const skeletons = Array.from({ length: skeletonCount })
      .map(() => '<div class="skeleton-row"></div>')
      .join('');
    target.innerHTML = skeletons;
  }
});

/* ===== ACCESSIBILITY HELPERS ===== */

window.reinitTooltips = function() {
  // Reinitialize tooltips after HTMX swaps or page load
  // Uses Bootstrap 5 Tooltip
  const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  tooltipTriggerList.map(tooltipTriggerEl => {
    // Dispose existing tooltip if it exists
    const existingTooltip = bootstrap.Tooltip.getInstance(tooltipTriggerEl);
    if (existingTooltip) {
      existingTooltip.dispose();
    }
    // Create new tooltip
    return new bootstrap.Tooltip(tooltipTriggerEl);
  });
};

document.addEventListener('htmx:afterSwap', () => {
  window.reinitTooltips();
});

/* ===== PRINT DIALOG TRIGGER ===== */

window.preparePrint = function() {
  // Add print-specific class to body if needed
  document.body.classList.add('printing');
  window.print();
  document.body.classList.remove('printing');
};

/* ===== REDUCED MOTION SUPPORT ===== */

// Detect reduced motion preference
const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
if (prefersReducedMotion) {
  document.documentElement.setAttribute('data-reduced-motion', 'true');
}

/* ===== VIEW TRANSITIONS (Progressive Enhancement) ===== */

// Enable View Transitions API for smooth page updates (if supported)
if (document.startViewTransition) {
  document.addEventListener('htmx:beforeSwap', (evt) => {
    // Use View Transitions for table updates
    if (evt.detail.target.id === 'txn-table' || evt.detail.target.classList.contains('table-target')) {
      evt.detail.startViewTransition = true;
    }
  });
}

/* ===== INITIALIZATION ===== */

document.addEventListener('DOMContentLoaded', () => {
  // Ensure toast manager is ready
  toastManager.init();

  // Re-init tooltips on first load
  window.reinitTooltips();

  // Set initial theme if not already set
  if (!localStorage.getItem('theme')) {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
  }
});
