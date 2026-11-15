// Alpine components for the rule editor.
// No build step (Golden Principle 9) — plain functions picked up by Alpine.

// Form-level state: only the tag-only switch of the Assign card.
function ruleEditor(initialTagOnly) {
  return {
    isTagOnly: !!initialTagOnly,
  };
}

// Match card: field rows of the sample, context filter rows and the advanced
// conditions. The selected rows feed hidden inputs with the same names as the
// editor without a sample, so the server parses one form shape.
function ruleMatch(state) {
  return {
    rows: Array.isArray(state.rows) ? state.rows : [],
    conditions: Array.isArray(state.conditions) ? state.conditions : [],
    filters: state.filters,
    init() {
      // The editor opened from a transaction: preview once the hidden inputs
      // hold their values. htmx listens after DOMContentLoaded, so wait for it.
      if (this.$el.dataset.autoPreview === undefined) return;
      const fire = () => this.$nextTick(() => htmx.trigger(document.body, "rule-auto-preview"));
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", fire);
      } else {
        fire();
      }
    },
    get selectedRows() {
      return this.rows.filter((r) => r.selected);
    },
    get primary() {
      return this.selectedRows[0] || null;
    },
    get andRows() {
      return this.selectedRows.slice(1);
    },
    addCondition() {
      this.conditions.push({
        field_target: "description",
        match_pattern: "contains",
        match_value: "",
        operator: "AND",
      });
    },
    removeCondition(i) {
      this.conditions.splice(i, 1);
    },
    moveUp(i) {
      if (i > 0) {
        const [row] = this.conditions.splice(i, 1);
        this.conditions.splice(i - 1, 0, row);
      }
    },
    moveDown(i) {
      if (i < this.conditions.length - 1) {
        const [row] = this.conditions.splice(i, 1);
        this.conditions.splice(i + 1, 0, row);
      }
    },
  };
}
window.ruleEditor = ruleEditor;
window.ruleMatch = ruleMatch;
