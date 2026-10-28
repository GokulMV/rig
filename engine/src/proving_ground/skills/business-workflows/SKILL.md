---
name: business-workflows
description: Complex, real-world agentic workflows per discipline (parallel branches, joins, several loops), each modelled on a published operating procedure or agent pattern, with the source named.
values:
  disciplines:
    finance:
      label: Finance
      steps:
        collect: {name: Collect the documents, does: "Gather the source documents and list what's missing.", kind: do, words: [finance, documents]}
        reconcile: {name: Reconcile, does: "Tie each balance to its source and explain every difference.", kind: check, words: [reconciliation, accounting]}
        review: {name: Review, does: "Review the work against policy and materiality; list exceptions.", kind: judge, words: [review, audit]}
        report: {name: Report, does: "Write the summary for sign-off.", kind: do, words: [report, finance]}
    compliance:
      label: Compliance
      steps:
        gather: {name: Gather evidence, does: "Collect the evidence the policy asks for.", kind: do, words: [compliance, evidence]}
        screen: {name: Screen, does: "Screen against the lists and rules that apply; record every hit.", kind: check, words: [screening, sanctions, kyc]}
        assess: {name: Assess risk, does: "Rate the risk with the reasons, by the policy's factors.", kind: judge, words: [risk, assessment]}
        decide: {name: Decide, does: "Approve, refer or decline, with the rule that applies.", kind: think, words: [decision, policy]}
  workflows:
    - id: feature-to-release
      discipline: development
      name: Feature from PRD to release
      source: "MetaGPT's software-company SOP (documents handed between product, architect, engineer, QA); Anthropic's orchestrator-workers and evaluator-optimizer patterns"
      steps:
        - {id: prd, name: Read the PRD, does: "List the requirements, acceptance criteria and open questions.", kind: think}
        - {id: design, name: Design, does: "Write the technical design: modules, interfaces, data changes, risks.", kind: think}
        - {id: tests, name: Write acceptance tests, does: "Turn each acceptance criterion into a failing test.", kind: do}
        - {id: implement, name: Implement, does: "Build the modules in the design, one at a time.", kind: do}
        - {id: integrate, name: Integrate and run the suite, does: "Merge the parts and run the whole test suite; report failures by module.", kind: check}
        - {id: review, name: Code review, does: "Review the diff for correctness, design fit and missing tests; list concrete problems.", kind: judge}
        - {id: security, name: Security review, does: "Check the change for injection, auth, secrets and unsafe input handling.", kind: judge}
        - {id: docs, name: Update the docs, does: "Update user docs and the changelog for the change.", kind: do}
        - {id: release, name: Release notes and sign-off, does: "Write the release notes and the go/no-go summary with test evidence.", kind: do}
      edges: [[prd, design], [prd, tests], [design, implement], [tests, integrate], [implement, integrate], [integrate, review], [integrate, security], [integrate, docs], [review, release], [security, release], [docs, release]]
      loops: [[integrate, implement, 3], [review, implement, 2], [security, implement, 1]]
      harness: [guardrails, cite-evidence]
    - id: release-regression
      discipline: qa
      name: Risk-based release regression
      source: "Risk-based testing practice; Anthropic's parallelization (sectioning) pattern"
      steps:
        - {id: changes, name: Analyse the changes, does: "List what changed in this release and what it touches.", kind: think}
        - {id: risks, name: Map the risks, does: "Rank the areas most likely to break, with why.", kind: think}
        - {id: unit, name: Run unit tests, does: "Run the unit suite for the risky areas; collect failures.", kind: check}
        - {id: e2e, name: Run end-to-end tests, does: "Run the end-to-end flows that cross the risky areas.", kind: check}
        - {id: explore, name: Explore, does: "Explore the top risks by hand, following a charter; log anything odd.", kind: do}
        - {id: triage, name: Triage failures, does: "Separate real bugs from flaky tests and environment problems, with evidence.", kind: judge}
        - {id: report, name: File bug reports, does: "Write each real bug: steps, expected, actual, severity.", kind: do}
        - {id: retest, name: Re-test fixes, does: "Re-run the failing cases after fixes; confirm or reopen.", kind: check}
        - {id: signoff, name: Sign off, does: "Write the release recommendation: what was covered, open risks, go or no-go.", kind: judge}
      edges: [[changes, risks], [risks, unit], [risks, e2e], [risks, explore], [unit, triage], [e2e, triage], [explore, triage], [triage, report], [report, retest], [retest, signoff]]
      loops: [[retest, report, 2]]
    - id: discovery-to-roadmap
      discipline: product
      name: Discovery to roadmap
      source: "Continuous discovery practice (interviews, data, market), RICE prioritisation; Anthropic's evaluator-optimizer loop for the critique"
      steps:
        - {id: question, name: Frame the question, does: "State the decision this discovery informs and what evidence would change it.", kind: think}
        - {id: interviews, name: Synthesise interviews, does: "Cluster interview notes into problems with counts and quotes.", kind: do}
        - {id: data, name: Analyse usage data, does: "Find where users drop off or struggle, with the numbers.", kind: do}
        - {id: market, name: Scan the market, does: "Summarise how alternatives solve the same problems.", kind: do}
        - {id: opportunities, name: Size the opportunities, does: "Turn the problems into opportunities with reach and impact estimates.", kind: think}
        - {id: prioritise, name: Prioritise, does: "Score by RICE (reach, impact, confidence, effort); pick and say why.", kind: think}
        - {id: prd, name: Write the PRD, does: "Write the PRD for the top opportunity: problem, users, requirements, metrics.", kind: do}
        - {id: critique, name: Critique, does: "Argue the strongest case against the plan; list what the evidence doesn't support.", kind: judge}
        - {id: brief, name: Brief stakeholders, does: "Write the one-page brief: decision, evidence, trade-offs, next step.", kind: do}
      edges: [[question, interviews], [question, data], [question, market], [interviews, opportunities], [data, opportunities], [market, opportunities], [opportunities, prioritise], [prioritise, prd], [prd, critique], [critique, brief]]
      loops: [[critique, prd, 2], [critique, prioritise, 1]]
    - id: anomaly-investigation
      discipline: data
      name: Metric anomaly investigation
      source: "Data incident practice (validate the data before the business); Anthropic's parallelization pattern for the drill-downs"
      steps:
        - {id: detect, name: State the anomaly, does: "Say which metric moved, by how much, since when, against what baseline.", kind: think}
        - {id: quality, name: Check the data, does: "Check freshness, row counts, nulls and joins for the metric's sources.", kind: check}
        - {id: segments, name: Drill down by segment, does: "Break the change down by platform, region, plan and channel.", kind: do}
        - {id: cohorts, name: Check cohorts, does: "Compare new and existing users' cohorts for the same period.", kind: do}
        - {id: events, name: Match to events, does: "List releases, campaigns, outages and seasonality in the window.", kind: do}
        - {id: hypothesis, name: Form hypotheses, does: "Write the most likely causes, each with the evidence for and against.", kind: think}
        - {id: test, name: Test the top hypothesis, does: "Run the query that would prove or rule it out.", kind: check}
        - {id: writeup, name: Write it up, does: "Write the cause, the evidence, the impact and what to do, with caveats.", kind: do}
      edges: [[detect, quality], [quality, segments], [quality, cohorts], [quality, events], [segments, hypothesis], [cohorts, hypothesis], [events, hypothesis], [hypothesis, test], [test, writeup]]
      loops: [[test, hypothesis, 2]]
    - id: incident-imag
      discipline: devops
      name: Incident response (IMAG roles)
      source: "Google SRE incident management (IMAG, based on the Incident Command System): incident commander, operations lead, communications lead; blameless postmortems"
      steps:
        - {id: declare, name: Declare and triage (IC), does: "As incident commander: state impact, severity and the first safe action; assign roles.", kind: think}
        - {id: mitigate, name: Mitigate (OL), does: "As operations lead: apply the smallest safe mitigation (rollback, failover, flag) and confirm it.", kind: do}
        - {id: comms, name: Update stakeholders (CL), does: "As communications lead: post a status update for technical and non-technical readers.", kind: do}
        - {id: diagnose, name: Find the root cause, does: "Follow logs, metrics and recent changes back to the cause.", kind: think}
        - {id: fix, name: Fix, does: "Fix the cause and add a guard or alert so it can't recur unnoticed.", kind: do}
        - {id: verify, name: Verify, does: "Check the fix with the same signal that caught the incident.", kind: check}
        - {id: resolve, name: Announce resolution (CL), does: "Post the all-clear with impact and duration.", kind: do}
        - {id: postmortem, name: Blameless postmortem, does: "Write the timeline, causes, what went well and badly, without blame.", kind: do}
        - {id: actions, name: Action items, does: "List the follow-ups with owners and dates; check each prevents a cause.", kind: judge}
      edges: [[declare, mitigate], [declare, comms], [mitigate, diagnose], [diagnose, fix], [fix, verify], [verify, resolve], [comms, resolve], [resolve, postmortem], [postmortem, actions]]
      loops: [[verify, fix, 2], [actions, postmortem, 1]]
    - id: vuln-management
      discipline: security
      name: Vulnerability management
      source: "Vulnerability management lifecycle (discover, triage, prioritise, remediate, verify, report); KEV and EPSS for exploitability, SLA tiers"
      steps:
        - {id: ingest, name: Ingest findings, does: "Collect scanner findings and dependency alerts; de-duplicate them.", kind: do}
        - {id: triage, name: Triage, does: "Drop false positives with evidence; note reachability and exposure for the rest.", kind: judge}
        - {id: exploit, name: Rate exploitability, does: "Check each finding against KEV and its EPSS score; mark actively exploited ones.", kind: check}
        - {id: prioritise, name: Prioritise and set SLAs, does: "Rank by exploitability, exposure and data sensitivity; assign the SLA tier.", kind: think}
        - {id: patch, name: Patch, does: "Upgrade or patch the highest-priority findings, smallest safe change first.", kind: do}
        - {id: mitigate, name: Compensating controls, does: "Where a patch isn't possible yet, add a control (WAF rule, isolation, feature off) and document the exception.", kind: do}
        - {id: verify, name: Verify, does: "Rescan and re-run the tests; confirm each fix and that nothing broke.", kind: check}
        - {id: report, name: Report, does: "Report what was fixed, what's open with its SLA, and mean time to remediate.", kind: do}
      edges: [[ingest, triage], [triage, exploit], [exploit, prioritise], [prioritise, patch], [prioritise, mitigate], [patch, verify], [mitigate, verify], [verify, report]]
      loops: [[verify, patch, 2]]
    - id: tiered-support
      discipline: support
      name: Tiered support with escalation
      source: "Tiered support practice; Anthropic's routing pattern (classify, then send to the right path) and evaluator-optimizer for the reply"
      steps:
        - {id: classify, name: Classify and route, does: "Classify the ticket (billing, bug, how-to, account) and its urgency.", kind: think}
        - {id: policy, name: Look up the policy, does: "Find the policy or known answer that applies.", kind: do}
        - {id: history, name: Check the account, does: "Check plan, past tickets and anything already promised.", kind: do}
        - {id: draft, name: Draft the reply, does: "Write the reply: the answer first, then the steps.", kind: do}
        - {id: check, name: Check against policy, does: "Check the reply's decision against the policy and the account facts.", kind: judge}
        - {id: escalate, name: Escalate if needed, does: "If the policy says a person decides, hand over with a summary; promise nothing.", kind: think}
        - {id: kb, name: Update the knowledge base, does: "If this was new, add the answer to the knowledge base.", kind: do}
      edges: [[classify, policy], [classify, history], [policy, draft], [history, draft], [draft, check], [check, escalate], [escalate, kb]]
      loops: [[check, draft, 2]]
    - id: release-docs
      discipline: docs
      name: Docs for a release
      source: "Docs-as-code practice (docs change with the code, examples tested in CI)"
      steps:
        - {id: diff, name: Read the changes, does: "List user-visible changes from the release diff and PRs.", kind: think}
        - {id: pages, name: Find affected pages, does: "List every page, example and screenshot the changes affect.", kind: do}
        - {id: guides, name: Update guides, does: "Update the task guides for the changes.", kind: do}
        - {id: reference, name: Update the reference, does: "Update the API or CLI reference from the code.", kind: do}
        - {id: changelog, name: Write the changelog, does: "Write the changelog entries, grouped by impact.", kind: do}
        - {id: examples, name: Run the examples, does: "Run every example and command; fix what fails.", kind: check}
        - {id: edit, name: Edit, does: "Edit for a newcomer: task first, no filler, consistent terms.", kind: judge}
      edges: [[diff, pages], [pages, guides], [pages, reference], [pages, changelog], [guides, examples], [reference, examples], [changelog, edit], [examples, edit]]
      loops: [[examples, guides, 2], [edit, guides, 1]]
    - id: evidence-synthesis
      discipline: research
      name: Evidence synthesis
      source: "Systematic review practice (protocol, search, extraction, conflict check, synthesis, citation check)"
      steps:
        - {id: scope, name: Scope the question, does: "Write the question, what counts as evidence, and what's out of scope.", kind: think}
        - {id: plan, name: Plan the search, does: "List the source types to search and the terms.", kind: think}
        - {id: primary, name: Gather primary sources, does: "Collect studies and data sets; note method and sample for each.", kind: do}
        - {id: secondary, name: Gather secondary sources, does: "Collect reviews, reports and expert summaries.", kind: do}
        - {id: extract, name: Extract claims, does: "Extract each claim with its number, source and strength.", kind: do}
        - {id: conflicts, name: Cross-check conflicts, does: "Find where sources disagree and why (method, sample, date).", kind: judge}
        - {id: synthesise, name: Synthesise, does: "Combine into an answer with confidence matched to the evidence.", kind: think}
        - {id: cite, name: Check citations, does: "Check every claim against its cited source.", kind: check}
        - {id: brief, name: Write the brief, does: "Write the answer, evidence, uncertainties and what's unknown.", kind: do}
      edges: [[scope, plan], [plan, primary], [plan, secondary], [primary, extract], [secondary, extract], [extract, conflicts], [conflicts, synthesise], [synthesise, cite], [cite, brief]]
      loops: [[cite, synthesise, 2]]
    - id: launch-campaign
      discipline: marketing
      name: Launch campaign
      source: "Integrated launch practice (one message, many channels, one claims review)"
      steps:
        - {id: positioning, name: Positioning, does: "Write who it's for, the problem, the one message and the proof points.", kind: think}
        - {id: blog, name: Blog post, does: "Write the launch post from the positioning.", kind: do}
        - {id: email, name: Email, does: "Write the customer email: subject, preview, body, one call to action.", kind: do}
        - {id: social, name: Social posts, does: "Write three short posts for different audiences.", kind: do}
        - {id: landing, name: Landing page copy, does: "Write the hero, benefits and FAQ.", kind: do}
        - {id: claims, name: Claims and brand check, does: "Check every claim against the facts and the brand rules; list violations.", kind: judge}
        - {id: plan, name: Channel plan, does: "Write the schedule: what goes where, when, to whom.", kind: do}
      edges: [[positioning, blog], [positioning, email], [positioning, social], [positioning, landing], [blog, claims], [email, claims], [social, claims], [landing, claims], [claims, plan]]
      loops: [[claims, positioning, 1]]
    - id: design-handoff
      discipline: design
      name: Design review to handoff
      source: "Heuristic evaluation, WCAG audit and content review in parallel; evaluator-optimizer loop on the build"
      steps:
        - {id: brief, name: Read the brief, does: "List goals, users, constraints and success measures.", kind: think}
        - {id: heuristics, name: Heuristic review, does: "Review against usability heuristics; list issues with severity.", kind: judge}
        - {id: a11y, name: Accessibility audit, does: "Check contrast, targets, focus, labels and semantics against WCAG.", kind: check}
        - {id: content, name: Content review, does: "Review labels, errors and microcopy for clarity.", kind: judge}
        - {id: prioritise, name: Prioritise fixes, does: "Merge the findings and rank by impact on the task.", kind: think}
        - {id: build, name: Build the fixes, does: "Implement the fixes in the components.", kind: do}
        - {id: verify, name: Verify, does: "Re-run the accessibility checks and the key task.", kind: check}
        - {id: handoff, name: Handoff notes, does: "Write what changed, why, and what's left for the next round.", kind: do}
      edges: [[brief, heuristics], [brief, a11y], [brief, content], [heuristics, prioritise], [a11y, prioritise], [content, prioritise], [prioritise, build], [build, verify], [verify, handoff]]
      loops: [[verify, build, 2]]
    - id: strategic-decision
      discipline: leadership
      name: Strategic decision with red team
      source: "Decision memo practice with a red-team review; Anthropic's evaluator-optimizer loop"
      steps:
        - {id: situation, name: Situation brief, does: "State the decision, the deadline and the facts that matter.", kind: think}
        - {id: options, name: Develop options, does: "Develop at least three real options.", kind: think}
        - {id: model, name: Financial model, does: "Cost each option over the same horizon with its assumptions.", kind: do}
        - {id: risks, name: Risk assessment, does: "List each option's risks with likelihood and impact.", kind: do}
        - {id: redteam, name: Red team, does: "Argue the strongest case against the leading option.", kind: judge}
        - {id: recommend, name: Recommend, does: "Make the call, the first step, and what would change it.", kind: think}
        - {id: memo, name: Write the memo, does: "Write the one-page memo for the board.", kind: do}
      edges: [[situation, options], [options, model], [options, risks], [model, redteam], [risks, redteam], [redteam, recommend], [recommend, memo]]
      loops: [[redteam, options, 1]]
    - id: invoice-three-way-match
      discipline: finance
      name: Invoice three-way match
      source: "Accounts payable three-way match (PO, goods receipt, invoice) with tolerances, exception routing to the accountable owner, and an audit trail"
      steps:
        - {id: capture, name: Capture the invoice, does: "Extract supplier, PO number, lines, quantities, prices, totals and terms.", kind: do}
        - {id: po, name: Find the PO, does: "Find the purchase order; flag a missing or invalid PO number.", kind: check}
        - {id: receipt, name: Find the goods receipt, does: "Find the receiving record for the PO lines.", kind: check}
        - {id: match, name: Match within tolerance, does: "Compare quantities and prices across PO, receipt and invoice against the tolerances.", kind: check}
        - {id: route, name: Route exceptions, does: "Send price variances to the buyer, missing receipts to the receiver, term breaks to procurement.", kind: think}
        - {id: resolve, name: Resolve, does: "Record the resolution (adjust, credit note, approve variance) with evidence.", kind: do}
        - {id: approve, name: Approve for payment, does: "Check the audit trail is complete and approve, or hold with the reason.", kind: judge}
      edges: [[capture, po], [capture, receipt], [po, match], [receipt, match], [match, route], [route, resolve], [resolve, approve]]
      loops: [[approve, route, 1]]
    - id: month-end-close
      discipline: finance
      name: Month-end close
      source: "Month-end close practice: cut-off, reconciliations tied to the GL, accruals with preparer/reviewer split, flux review against materiality, sign-off"
      steps:
        - {id: cutoff, name: Cut off, does: "Confirm all period transactions are in and the cut-off is right.", kind: check}
        - {id: cash, name: Reconcile cash, does: "Reconcile bank to GL; explain every difference.", kind: check}
        - {id: subledgers, name: Tie out subledgers, does: "Tie AR, AP, fixed assets and prepaids to the GL; investigate, never plug.", kind: check}
        - {id: accruals, name: Post accruals, does: "Prepare accruals, deferrals and depreciation entries with support.", kind: do}
        - {id: review, name: Review entries, does: "As a second person, review every entry and its support.", kind: judge}
        - {id: flux, name: Flux review, does: "Compare to budget and prior period; explain each variance over materiality in one line.", kind: judge}
        - {id: package, name: Close package, does: "Produce the statements and the close summary for sign-off.", kind: do}
      edges: [[cutoff, cash], [cutoff, subledgers], [cutoff, accruals], [accruals, review], [cash, flux], [subledgers, flux], [review, flux], [flux, package]]
      loops: [[review, accruals, 2], [flux, subledgers, 1]]
    - id: kyc-onboarding
      discipline: compliance
      name: KYC onboarding
      source: "KYC/AML onboarding: identity (CIP), beneficial owners, sanctions/PEP/adverse-media screening, risk rating, CDD or EDD, sign-off and monitoring"
      steps:
        - {id: collect, name: Collect and verify identity, does: "Collect the customer's details and documents; verify identity (pass or stop).", kind: check}
        - {id: owners, name: Identify beneficial owners, does: "For entities, identify and verify owners above the threshold.", kind: do}
        - {id: sanctions, name: Sanctions screening, does: "Screen the customer and owners against sanctions lists; record every hit.", kind: check}
        - {id: pep, name: PEP screening, does: "Screen for politically exposed persons and close associates.", kind: check}
        - {id: media, name: Adverse media, does: "Search adverse media; summarise relevant findings with sources.", kind: do}
        - {id: rate, name: Rate the risk, does: "Rate risk (low, medium, high) from identity, geography, product and screening, with reasons.", kind: judge}
        - {id: edd, name: Enhanced due diligence, does: "For high risk: source of wealth and funds, deeper checks, senior sign-off needed.", kind: do}
        - {id: decide, name: Decide, does: "Approve, refer or decline, citing the rule; set the review cycle.", kind: think}
      edges: [[collect, owners], [owners, sanctions], [owners, pep], [owners, media], [sanctions, rate], [pep, rate], [media, rate], [rate, edd], [edd, decide]]
      loops: [[decide, rate, 1]]
---

# Business workflows

Complex workflows, each modelled on a published operating procedure or agent pattern (named in
`source`), with the shape real work has: several steps in parallel, joins that wait for them,
and loops back to fix. They load as starters next to the simple ones, marked as business cases.

Models follow the step kind (starter-workflows: `model_for`), and library skills attach by the
step's words like any other step. Every one of them can be opened in the builder and changed.

Sources consulted for the shapes (operating practice, not legal advice):
- Google SRE Incident Management Guide (IMAG roles; blameless postmortems): sre.google
- Anthropic, "Building effective agents" (routing, parallelization, orchestrator-workers,
  evaluator-optimizer)
- MetaGPT (Code = SOP(Team): documents handed between roles)
- Vulnerability management lifecycle guides (KEV, EPSS, SLA tiers)
- KYC/AML onboarding guides (CIP, CDD, EDD, screening, risk rating)
- Accounts payable three-way match guides (tolerances, exception routing, audit trail)
- Month-end close guides (reconciliation, accruals, flux review, sign-off)
