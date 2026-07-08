// Alpine component for the rule editor's dynamic condition rows.
// No build step (Golden Principle 9) — plain function picked up by Alpine.
function ruleEditor(initialConditions) {
  return {
    conditions: Array.isArray(initialConditions) ? initialConditions : [],
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
