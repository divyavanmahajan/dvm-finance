## ADDED Requirements

### Requirement: The agent skill for the home finances
The repository SHALL hold the agent skill `home-finance` in
`plugins/home-finance/skills/home-finance/SKILL.md`. The skill SHALL tell the
agent how to find the database, and SHALL give the data model of the
transactions, the budgets, and the rules. It SHALL give a query for the spend
per category, the trend of a category, the cash flow, the budget against the
actual spend, the uncategorized transactions, and the recurring payments.

#### Scenario: The user asks about the spend of a category
- **WHEN** the user asks the agent how much the household spent on a category
- **THEN** the skill gives the agent a query for the spend of that category
  and its children in a period

### Requirement: Read-only access to the database
The skill SHALL tell the agent to open the database read-only. The skill SHALL
NOT allow a write to the database with SQL. The skill SHALL tell the agent to
make each change through the app, and to ask the user before each change.

#### Scenario: The agent proposes a new rule
- **WHEN** the agent finds many uncategorized transactions with one description
- **THEN** the agent writes a rule proposal for the user, and the user makes
  the rule on the Rules page

#### Scenario: The agent sets a manual category
- **WHEN** the user tells the agent to set the category of one transaction
- **THEN** the agent posts the form field `manual_category` to
  `/transactions/{id}/category` while the app runs

### Requirement: The numbers agree with the app
The queries of the skill SHALL use the calculation rules of the app. They
SHALL exclude a flagged or merged transaction. They SHALL use the manual
category before the rule category. A category SHALL include its children with
the hyphen separator. The cash flow and the budget actuals SHALL exclude a
category that contains `transfer`.

#### Scenario: The agent gives the cash flow of a month
- **WHEN** the agent runs the cash-flow query of the skill for a month
- **THEN** the income and the expense agree with the Cash flow page of the
  same month

#### Scenario: The agent gives the actual spend of a budget
- **WHEN** the agent runs the budget query of the skill
- **THEN** the actual spend of each budget agrees with the Budgets page

### Requirement: The plugin marketplace
The repository root SHALL hold the marketplace manifest
`.claude-plugin/marketplace.json` with the marketplace name `dvm-finance`. The
manifest SHALL list the plugin `home-finance` with the source
`./plugins/home-finance`. The plugin folder SHALL hold the manifest
`.claude-plugin/plugin.json`.

#### Scenario: The user installs the skill from the repository
- **WHEN** the user adds the marketplace `divyavanmahajan/dvm-finance` and
  installs `home-finance@dvm-finance`
- **THEN** the skill `home-finance` is available in a new session

### Requirement: The install instructions
The README SHALL tell the user how to add the marketplace, how to install the
plugin, and how to copy the skill folder by hand. It SHALL give example
questions.

#### Scenario: The user reads the README
- **WHEN** the user opens the section about the skill in the README
- **THEN** the user finds the install commands and example questions
