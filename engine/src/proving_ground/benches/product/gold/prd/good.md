# PRD: Get paid faster

## Problem
Agencies chase late invoices by hand. 31% of invoices are paid late and DSO is 47 days. Every customer we interviewed named manual reminders (I1, I3, I5) or confusing partial payments (I1, I2, I5) as the cost.

## Users
Owners and finance leads of agencies from 1 to 30 people who invoice by email (I1-I5).

## Requirements
- MUST send automatic reminders on a schedule the user sets, and stop once the invoice is paid in full (I1, I3, I5).
- MUST record partial payments and show the client the remaining balance on the invoice (I1, I2, I5).
- MUST put a "pay by card" link in the invoice email, with the card fee shown before paying (I2, I3, I4).
- SHOULD show a list of who owes what today, oldest first (I2, I5).
- SHOULD flag clients who are late on more than half of their invoices (I5).
- SHOULD allow late fees, off by default and switchable per client (I4).

## Success metrics
- DSO from 47 days to 35 days within 6 months of launch.
- Late invoices from 31% to 20% within 6 months.
- Card payments from 12% to 30% of invoices within 6 months.
- Manual reminders per customer from 18 a month to under 3.

## Out of scope
- An AI chatbot for client questions: no customer raised it and I3 said clients don't want one. Kept as a research question for a later phase.
- Accounting integrations.

## Risks
- Automatic reminders could annoy clients: default to polite wording and let users preview them.
- Card fees could put users off: show fees up front (I2).
