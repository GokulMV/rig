---
name: architecture-catalog
description: A catalog of RAG and agent architectures (parts, links, knobs, trade-offs, sources) and the rules that
  rank them for a use case.
values:
  families:
  - rag
  - agent
  max_results: 10
  explain_model: claude-haiku-5-5
  explain_top: 3
  explain_max_tokens: 900
  explain_usd: 0.01            # roughly what one explanation call costs, said on its button and while it runs
  signal_weight: 3
  signal_cap: 4
  preference_weight: 1
  preference_levels:
    low: 0
    medium: 1
    high: 2
  preferences:
    latency:
      low:
      - fast
      - low latency
      - real-time
      - realtime
      - interactive
      - instant
      - chat
    cost:
      low:
      - cheap
      - budget
      - low cost
      - low-cost
      - high volume
      - cost
      - at scale
    accuracy:
      high:
      - accurate
      - accuracy
      - high stakes
      - high-stakes
      - precise
      - must be right
      - compliance
      - legal
      - medical
      - audit
      - citations
    complexity:
      low:
      - simple
      - prototype
      - quick
      - mvp
      - small team
      - first version
  repo_rules:
    docs_words_min: 20000
    docs_signals:
    - documents
    - knowledge base
    files_min: 400
    files_signals:
    - codebase
    - many files
    stack_as_signals: true
  # Ranking by what the use case asks for (catalog_arch.recommend). Each intent is said by
  # `phrases` (whole words, any form of the first and last word: "documents" finds
  # "document", "hand off" finds "hands off"; an inflected first word needs a space after it,
  # so "hands-off" doesn't) or `patterns` (regular expressions, e.g. an amount over a limit),
  # and adds `fits` points to the designs it calls
  # for, once per intent; the reason quotes the use case's own words. Entry `signals` the use
  # case says add `use_case_signal` each (at most signal_cap); signals only the repo's files
  # point at add `repo_signal` each and never put a design on the list alone. `fit_levels`:
  # the points for each label; an entry needs `min_points` and at least one intent or use-case
  # signal to be listed. With the local embedding model ready (skill_models), its similarity
  # between the use case and the design adds up to `embedding_weight` points.
  use_case_signal: 1
  repo_signal: 0.5
  min_points: 2
  embedding_weight: 2
  fit_levels: {strong: 6, good: 4}
  fit_labels: {strong: Strong Fit, good: Good Fit, possible: Possible}
  intents:
    documents:
      says: answer from documents
      ask: which documents the answers come from
      phrases: [document, documents, docs, documentation, policy, policies, knowledge base, handbook, manual, manuals, wiki, faq, faqs, pdf, pdfs, help center, help articles, articles, contracts, from our, cite, cites, cited, citation, citations, sources, source]
      fits: {naive-rag: 3, hybrid-rag: 4, reranked-rag: 4, corrective-rag: 3, self-rag: 3, agentic-rag: 2, adaptive-rag: 2, graph-rag: 1, multimodal-rag: 1, hyde-rag: 1, rag-fusion: 2}
    policy:
      says: answers that follow a written policy
      ask: which written rules the answers must follow
      phrases: [policy, policies, refund policy, terms of service, rules we, our rules, guidelines, sop, procedures]
      fits: {reranked-rag: 2, naive-rag: 2, hybrid-rag: 1, corrective-rag: 1}
    must-cite:
      says: answers that must be right and cited
      ask: whether answers must be cited
      phrases: [cite, cites, cited, citation, citations, must be right, accurate, accuracy, hallucinate, hallucination, grounded, quote the, compliance, legal, audit]
      fits: {reranked-rag: 2, self-rag: 3, corrective-rag: 3, hybrid-rag: 1}
    approval:
      says: a person must approve some actions
      ask: which actions a person must approve
      phrases: [approval, approve, approves, approved, approver, manager, managers, sign-off, sign off, signoff, human review, human in the loop, human-in-the-loop, escalate, escalation, needs a person, a person must, supervisor approval]
      patterns: ['(?:over|above|more than|exceed\w*|greater than|beyond)\s+[$€£]\s?\d', '[$€£]\s?\d[\d,.]*\s?[km]?\s+(?:or more|and up|and above)']
      fits: {human-in-the-loop: 6}
    risky-actions:
      says: actions that cost money or change data
      ask: which actions cost money or change data
      phrases: [refund, refunds, payment, payments, pay out, charge, charges, delete, deletes, send emails, wire, transfer, transfers, credit, credits]
      fits: {human-in-the-loop: 2}
    many-sources:
      says: several sources or tools
      ask: which sources or tools it draws on
      phrases: [several sources, multiple sources, many sources, many tools, several tools, different sources, across sources, apis and docs, docs and the database, database and docs, sql and docs, web and docs, compare sources, multi-hop, follow-up searches]
      fits: {agentic-rag: 5, react: 2, supervisor: 1}
    relationships:
      says: questions about how things connect
      ask: whether questions are about how things connect
      phrases: [relationship, relationships, connected, connections between, entities, entity, graph, multi-hop, whole corpus, themes across, across all]
      fits: {graph-rag: 5}
    exact-terms:
      says: exact names, codes or ids
      ask: whether people ask by exact names, codes or ids
      phrases: [exact terms, product codes, error codes, part numbers, sku, skus, ids, keyword, keywords, acronyms]
      fits: {hybrid-rag: 4}
    visual-docs:
      says: tables, scans or images in the documents
      ask: whether the documents have tables, scans or images
      phrases: [table, tables, chart, charts, scan, scans, scanned, image, images, diagram, diagrams, slides, screenshot, screenshots]
      fits: {multimodal-rag: 5}
    vague-questions:
      says: short or vague questions
      ask: whether questions come in short or vague
      phrases: [vague, short questions, unclear questions, one-word, badly worded]
      fits: {hyde-rag: 4, rag-fusion: 3}
    mixed-difficulty:
      says: a mix of easy and hard questions
      ask: whether some questions are easy and some hard
      phrases: [easy and hard, simple and complex, mixed questions, some questions, sometimes complex]
      fits: {adaptive-rag: 4}
    routing:
      says: different kinds of request handled differently
      ask: what kinds of request come in and who handles each
      phrases: [route, routes, routing, router, categories, category, categorize, categorise, classify, classification, triage, different kinds, types of request, types of tickets, kinds of tickets]
      fits: {router: 5, swarm-handoffs: 1}
    plan-then-do:
      says: plan first, then do the steps
      ask: whether the work is several steps in order
      phrases: [plan then, plan first, plan and execute, step by step, multi-step, several steps, steps in order, break down, breaks down, migration, migrate, refactor, refactoring, feature, features]
      fits: {plan-and-execute: 5, orchestrator-workers: 1}
    code-change:
      says: changes to code that tests can check
      ask: whether it changes code that tests can check
      phrases: [bug, bugs, bugfix, bug fix, fix the, failing test, failing tests, tests, test suite, code review, reviews code, review the code, pull request, pull requests, pr review, coding, code changes, junit, pytest, regression]
      fits: {plan-and-execute: 3, evaluator-optimizer: 3, reflexion: 3, react: 2}
    quality-loop:
      says: work judged against criteria and improved
      ask: what the work is judged against
      phrases: [review, reviews, reviewer, critique, feedback, rubric, quality, polish, iterate, improve the draft, style guide, standards, guidelines]
      fits: {evaluator-optimizer: 5, reflexion: 1}
    retry-learn:
      says: learn from failed attempts
      ask: whether it should learn from failed attempts
      phrases: [retry, retries, try again, learn from mistakes, keeps failing, same mistake, flaky]
      fits: {reflexion: 4}
    hard-search:
      says: hard problems with several possible approaches
      ask: whether problems have several possible approaches
      phrases: [hard problems, puzzle, puzzles, search over, explore options, several approaches, alternatives, best of several, optimization]
      fits: {lats: 5}
    big-parallel:
      says: a big job that splits into parts
      ask: whether the job splits into independent parts
      phrases: [large, big job, many files, whole codebase, in parallel, parallel, independent parts, split the work, batch, bulk]
      fits: {orchestrator-workers: 4, hierarchical: 2}
    specialists:
      says: several kinds of expertise
      ask: which kinds of expertise it needs
      phrases: [specialist, specialists, experts, team of, several roles, roles, different expertise]
      fits: {supervisor: 4, hierarchical: 2, swarm-handoffs: 1}
    handoffs:
      says: work handed between agents
      ask: when the work is handed to another agent or a person
      phrases: [hand off, handoff, handoffs, hand over, transfer to, pass to, escalate to another]
      fits: {swarm-handoffs: 5}
    shared-board:
      says: open problems pieced together from many angles
      ask: whether it pieces together an open problem
      phrases: [brainstorm, open-ended, open ended, pieces together, shared notes, investigation, investigate]
      fits: {blackboard: 3, orchestrator-workers: 1}
    tool-use:
      says: an agent that uses tools step by step
      ask: which tools it calls
      phrases: [tool, tools, api, apis, browse, browser, search the web, look up, lookup, call]
      fits: {react: 3, agentic-rag: 1}
    research:
      says: research that gathers and compares
      ask: what it gathers and compares
      phrases: [research, compare, comparison, report, analyst, investigate, survey]
      fits: {agentic-rag: 2, orchestrator-workers: 2, supervisor: 1}
  # When nothing reaches min_points (catalog_arch.empty_state): the designs the use case's own
  # words did point at, below the bar, are shown as close, never as picks, with the words that
  # matched and what to add. `ask` comes from each close design's strongest intent (its `ask`
  # above, the intents the use case hasn't said); `words` are its signals not yet said, those
  # shared by more close designs first. Each such word or intent would add points for real.
  empty_state:
    max_near: 3
    max_words: 4
    title: No fits yet           # in place of "Best fits", which would promise a list
    heading: Close, not a fit yet
    matched: Only {words} matched, too little to rank on.
    asks_lead: 'To rank one, say:'
    words: 'Words like {words} count too.'
    nothing: None of its words point at a design.
    browse: Say more about the documents, the users or the tools involved, or browse below.
    browse_near: Or browse them all below.
  # Explain asked with no picks: no model is called, and the note says so.
  explain_nothing: Nothing was asked; there are no picks to explain yet.
  # Opening a design in "Nothing yet" loads its `lab_workflow` (rag:<rag-workflows id> or
  # pattern:<workflow-patterns id>) on the Lab canvas; `lab_note` says what it leaves out.
  # A pattern is set to the discipline the use case points at: the discipline whose label or
  # step words appear in it most often (at least `min_hits`), else the family's default.
  lab_handoff:
    min_hits: 1
    default_discipline:
      rag: research
      agent: development
  entries:
  - id: naive-rag
    family: rag
    name: Naive RAG
    lab_workflow: rag:naive-rag
    summary: Split documents into chunks, find the closest few to the question, and answer from them.
    when_to_use: 'A first version over a clean text knowledge base: FAQs, docs, wikis. The baseline every other
      RAG is measured against.'
    when_not_to_use: Questions that need several hops, tables, or whole-corpus summaries; or when a wrong retrieval
      would be costly.
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: ingest
      label: Ingest pipeline
      type: backend
      role: Splits documents into chunks and indexes them
    - id: docs
      label: Document store
      type: database
      role: Holds the source documents
    - id: vectors
      label: Vector index
      type: database
      role: Finds passages by meaning
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: retriever
      label: Retriever
      type: backend
      role: Embeds the question and takes the top matches
    connections:
    - - docs
      - ingest
      - files
    - - ingest
      - vectors
      - chunks
    - - question
      - retriever
      - query
    - - retriever
      - vectors
      - search
    - - vectors
      - retriever
      - top chunks
    - - retriever
      - llm
      - question + chunks
    - - llm
      - answer
      - grounded answer
    parameters:
    - &id002
      name: chunk_size
      default: 512
      what: Tokens per chunk. Small chunks find exact facts; big ones keep context but dilute matches.
      range:
      - 128
      - 2048
    - &id001
      name: top_k
      default: 5
      what: Passages handed to the model. More recall, more cost and noise.
      range:
      - 1
      - 30
    - name: embedding_model
      default: general-text
      what: Which embedding model turns text into vectors; sets what 'similar' means.
      options:
      - general-text
      - domain-tuned
      - multilingual
    - name: chunk_overlap
      default: 64
      what: Tokens shared between neighbouring chunks, so facts at a boundary aren't cut in half.
      range:
      - 0
      - 256
    tradeoffs:
      latency: low
      cost: low
      accuracy: medium
      complexity: low
    signals:
    - faq
    - knowledge base
    - wiki
    - documentation
    - docs
    - prototype
    - simple
    - questions
    - search
    - support articles
    sources:
    - title: Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks (Lewis et al.)
      url: https://arxiv.org/abs/2005.11401
    - title: 'Retrieval-Augmented Generation for Large Language Models: A Survey'
      url: https://arxiv.org/abs/2312.10997
  - id: multimodal-rag
    family: rag
    name: Multimodal RAG
    lab_workflow: rag:naive-rag
    lab_note: "The Lab's benches are text documents with no page images, so it runs the text-only core of this design (Naive RAG). Measure the vision parts on your own documents."
    summary: Index pages as images (or images plus text) so tables, charts and figures can be found and read.
    when_to_use: PDFs, slides and scans where the answer sits in a table, chart or layout that plain text extraction
      loses.
    when_not_to_use: Plain-text corpora; or when storage and vector count matter (page images produce far more vectors
      per page).
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: docs
      label: Document store
      type: database
      role: Holds the source documents
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: render
      label: Page renderer
      type: backend
      role: Turns each page into an image and extracts text
    - id: vision
      label: Vision embedder
      type: cloud
      role: Embeds page images for retrieval
    - id: pageidx
      label: Page index
      type: database
      role: Finds pages by visual and text similarity
    - id: reader
      label: Vision reader
      type: cloud
      role: Reads the retrieved page images to answer
    connections:
    - - docs
      - render
      - pdfs
    - - render
      - vision
      - page images
    - - vision
      - pageidx
      - page vectors
    - - question
      - pageidx
      - query
    - - pageidx
      - reader
      - top pages
    - - reader
      - llm
      - extracted facts
    - - llm
      - answer
      - answer with page cites
    parameters:
    - name: page_dpi
      default: 150
      what: Render resolution. Higher reads small print, costs more tokens.
      range:
      - 72
      - 300
    - name: top_k
      default: 3
      what: Pages shown to the vision reader.
      range:
      - 1
      - 10
    - name: retrieval_mode
      default: page-image
      what: What gets embedded. Page-image skips parsing; text-only is cheapest.
      options:
      - page-image
      - text+image
      - text-only
    tradeoffs:
      latency: high
      cost: high
      accuracy: high
      complexity: high
    signals:
    - pdf
    - tables
    - charts
    - figures
    - images
    - scans
    - slides
    - invoice
    - diagram
    - layout
    sources:
    - title: 'ColPali: Efficient Document Retrieval with Vision Language Models'
      url: https://arxiv.org/abs/2407.01449
    - title: 'Retrieval-Augmented Generation for Large Language Models: A Survey'
      url: https://arxiv.org/abs/2312.10997
  - id: hyde-rag
    family: rag
    name: HyDE (hypothetical answer first)
    lab_workflow: rag:hyde
    summary: Have the model draft a fake answer, then retrieve with the draft instead of the short question.
    when_to_use: Short or vague questions that look nothing like the documents; a new domain with no labelled search
      data.
    when_not_to_use: Questions about fresh facts the model doesn't know (the draft can mislead); tight latency budgets.
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: vectors
      label: Vector index
      type: database
      role: Finds passages by meaning
    - id: docs
      label: Document store
      type: database
      role: Holds the source documents
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: drafter
      label: Draft writer
      type: cloud
      role: Writes a hypothetical answer to the question
    - id: retriever
      label: Retriever
      type: backend
      role: Searches with the draft's embedding
    connections:
    - - question
      - drafter
      - question
    - - drafter
      - retriever
      - hypothetical answer
    - - retriever
      - vectors
      - search
    - - vectors
      - retriever
      - real passages
    - - retriever
      - llm
      - question + passages
    - - llm
      - answer
      - answer
    parameters:
    - name: drafts
      default: 1
      what: Hypothetical answers averaged into one search vector.
      range:
      - 1
      - 5
    - name: draft_model_tier
      default: small
      what: Model tier for the draft. Small is usually enough.
      options:
      - small
      - medium
      - large
    - *id001
    tradeoffs:
      latency: medium
      cost: medium
      accuracy: medium
      complexity: low
    signals:
    - vague
    - short queries
    - new domain
    - no training data
    - zero-shot
    - unlabelled
    - jargon
    sources:
    - title: Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE)
      url: https://arxiv.org/abs/2212.10496
  - id: corrective-rag
    family: rag
    name: Corrective RAG (CRAG)
    lab_workflow: rag:corrective-rag
    summary: Grade what was retrieved; if it is weak, fall back to web search and filter out irrelevant passages
      before answering.
    when_to_use: The knowledge base has gaps or goes stale and a confidently wrong answer is worse than a slower
      one.
    when_not_to_use: Closed corpora that must not leak queries to the web; very tight latency.
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: vectors
      label: Vector index
      type: database
      role: Finds passages by meaning
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: retriever
      label: Retriever
      type: backend
      role: Finds candidate passages
    - id: grader
      label: Relevance grader
      type: cloud
      role: 'Scores each passage: correct, ambiguous or wrong'
    - id: web
      label: Web search
      type: external
      role: Fallback source when retrieval is weak
    - id: filter
      label: Passage filter
      type: backend
      role: Keeps only the useful parts
    connections:
    - - question
      - retriever
      - query
    - - retriever
      - vectors
      - search
    - - retriever
      - grader
      - passages
    - - grader
      - web
      - if weak
    - - grader
      - filter
      - if good
    - - web
      - filter
      - web results
    - - filter
      - llm
      - clean context
    - - llm
      - answer
      - answer
    parameters:
    - name: relevance_threshold
      default: 0.6
      what: Grader score below which retrieval counts as failed.
      range:
      - 0.1
      - 0.95
    - name: web_fallback
      default: true
      what: Whether weak retrieval triggers a web search.
      options:
      - true
      - false
    - *id001
    tradeoffs:
      latency: high
      cost: medium
      accuracy: high
      complexity: medium
    signals:
    - outdated
    - stale
    - fresh
    - news
    - gaps
    - hallucination
    - wrong answers
    - accuracy
    - high stakes
    - fallback
    sources:
    - title: Corrective Retrieval Augmented Generation
      url: https://arxiv.org/abs/2401.15884
  - id: graph-rag
    family: rag
    name: GraphRAG
    lab_workflow: rag:graph-rag
    summary: Build an entity graph from the corpus, summarise its communities, and answer broad questions from those
      summaries.
    when_to_use: '''What are the main themes?'' questions over a whole corpus; data full of entities and relationships;
      multi-hop questions.'
    when_not_to_use: Small or fast-changing corpora; lookups of single facts. Building the graph costs many model
      calls.
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: docs
      label: Document store
      type: database
      role: Holds the source documents
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: extractor
      label: Entity extractor
      type: cloud
      role: Pulls entities and relations out of each chunk
    - id: graph
      label: Knowledge graph
      type: database
      role: Stores entities, relations and communities
    - id: summaries
      label: Community summaries
      type: database
      role: Pre-written summaries of each cluster
    - id: combine
      label: Answer combiner
      type: backend
      role: Merges partial answers from the relevant clusters
    connections:
    - - docs
      - extractor
      - chunks
    - - extractor
      - graph
      - entities, relations
    - - graph
      - summaries
      - community reports
    - - question
      - combine
      - query
    - - combine
      - summaries
      - pick clusters
    - - summaries
      - llm
      - partial answers
    - - llm
      - answer
      - final answer
    parameters:
    - name: chunk_size
      default: 600
      what: Chunks read by the extractor. Bigger means fewer calls but missed entities.
      range:
      - 200
      - 1200
    - name: community_level
      default: 1
      what: How coarse the clusters are. Higher is broader, cheaper, vaguer.
      range:
      - 0
      - 3
    - name: max_hops
      default: 2
      what: Relations followed from a matched entity.
      range:
      - 1
      - 4
    tradeoffs:
      latency: high
      cost: high
      accuracy: high
      complexity: high
    signals:
    - graph
    - entities
    - relationships
    - multi-hop
    - themes
    - summarize corpus
    - investigation
    - network
    - connections
    - whole dataset
    sources:
    - title: 'From Local to Global: A Graph RAG Approach to Query-Focused Summarization'
      url: https://arxiv.org/abs/2404.16130
  - id: hybrid-rag
    family: rag
    name: Hybrid retrieval (vector + keyword)
    lab_workflow: rag:hybrid-rag
    summary: Search by meaning and by exact words, then merge the two ranked lists.
    when_to_use: Corpora with codes, names, SKUs, error strings or legal terms that embeddings blur; mixed natural
      and exact queries.
    when_not_to_use: Purely conversational text where meaning is enough; the extra index adds upkeep.
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: docs
      label: Document store
      type: database
      role: Holds the source documents
    - id: vectors
      label: Vector index
      type: database
      role: Finds passages by meaning
    - id: keywords
      label: Keyword index
      type: database
      role: Finds passages by exact words
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: fuse
      label: Rank fusion
      type: backend
      role: Merges both lists with reciprocal rank fusion
    connections:
    - - question
      - vectors
      - semantic query
    - - question
      - keywords
      - keyword query
    - - vectors
      - fuse
      - ranked list
    - - keywords
      - fuse
      - ranked list
    - - fuse
      - llm
      - question + top passages
    - - llm
      - answer
      - answer
    parameters:
    - name: bm25_weight
      default: 0.5
      what: Share of the keyword side in the merge.
      range:
      - 0
      - 1
    - name: rrf_k
      default: 60
      what: Reciprocal rank fusion constant; higher flattens the gap between ranks.
      range:
      - 10
      - 100
    - *id001
    - *id002
    tradeoffs:
      latency: low
      cost: low
      accuracy: high
      complexity: medium
    signals:
    - sku
    - codes
    - identifiers
    - error messages
    - exact match
    - names
    - legal
    - part numbers
    - logs
    - keyword
    - jargon
    sources:
    - title: 'Hybrid Search for RAG: Combining BM25 and Dense Vector Search'
      url: https://denser.ai/blog/hybrid-search-for-rag/
    - title: 'RAGLight docs: hybrid search (semantic + BM25, merged with reciprocal rank fusion)'
      url: https://raglight.mintlify.app/documentation/hybrid-search
  - id: adaptive-rag
    family: rag
    name: Adaptive RAG
    lab_workflow: rag:adaptive-rag
    summary: Classify each question's difficulty, then answer directly, with one retrieval, or with iterative retrieval.
    when_to_use: Traffic mixes trivial and hard questions, and paying for multi-step retrieval on every one is wasteful.
    when_not_to_use: Uniform questions; no way to label a few hundred queries to calibrate the router.
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: vectors
      label: Vector index
      type: database
      role: Finds passages by meaning
    - id: classifier
      label: Complexity router
      type: backend
      role: Labels the question simple, moderate or complex
    - id: direct
      label: Direct answer
      type: cloud
      role: Answers with no retrieval
    - id: single
      label: Single-step retrieval
      type: backend
      role: One search then answer
    - id: iter
      label: Iterative retrieval
      type: backend
      role: Several search-and-think rounds
    connections:
    - - question
      - classifier
      - question
    - - classifier
      - direct
      - simple
    - - classifier
      - single
      - moderate
    - - classifier
      - iter
      - complex
    - - single
      - vectors
      - search
    - - iter
      - vectors
      - search
    - - direct
      - llm
      - prompt
    - - single
      - llm
      - prompt + passages
    - - iter
      - llm
      - prompt + passages
    - - llm
      - answer
      - answer
    parameters:
    - name: router_model_tier
      default: small
      what: Model that labels difficulty. Small keeps the router cheap.
      options:
      - small
      - medium
    - name: max_rounds
      default: 4
      what: Rounds allowed on complex questions.
      range:
      - 2
      - 8
    - *id001
    tradeoffs:
      latency: medium
      cost: low
      accuracy: high
      complexity: medium
    signals:
    - mixed questions
    - cost
    - high volume
    - varied
    - multi-hop
    - routing
    - scale
    - simple and complex
    sources:
    - title: 'Adaptive-RAG: Learning to Adapt Retrieval-Augmented LLMs through Question Complexity'
      url: https://arxiv.org/abs/2403.14403
  - id: agentic-rag
    family: rag
    name: Agentic RAG
    lab_workflow: rag:agentic-rag
    summary: An agent decides what to search, which source to use, and whether to search again before it answers.
    when_to_use: Several data sources or tools; questions needing decomposition, comparison or follow-up searches.
    when_not_to_use: Single-source lookups; strict latency or cost caps; when you can't afford an unpredictable
      number of steps.
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: vectors
      label: Vector index
      type: database
      role: Finds passages by meaning
    - id: tools
      label: Tools
      type: external
      role: Search, APIs and code the agent can call
    - id: memory
      label: Memory
      type: database
      role: Keeps notes and past steps
    - id: agent
      label: Retrieval agent
      type: cloud
      role: Plans searches, reads results, decides when it knows enough
    - id: sql
      label: Structured data
      type: database
      role: 'A second source: tables or a SQL database'
    connections:
    - - question
      - agent
      - question
    - - agent
      - vectors
      - semantic search
    - - agent
      - sql
      - query
    - - agent
      - tools
      - web / API
    - - vectors
      - agent
      - passages
    - - sql
      - agent
      - rows
    - - tools
      - agent
      - results
    - - agent
      - memory
      - notes
    - - agent
      - answer
      - answer with sources
    parameters:
    - name: max_iterations
      default: 6
      what: Search rounds before the agent must answer.
      range:
      - 1
      - 15
    - name: sources_enabled
      default: docs+sql
      what: Which sources the agent may use.
      options:
      - docs
      - docs+sql
      - docs+sql+web
    - *id001
    tradeoffs:
      latency: high
      cost: high
      accuracy: high
      complexity: high
    signals:
    - multiple sources
    - sql
    - database
    - compare
    - research
    - multi-hop
    - tools
    - follow-up
    - complex questions
    - analyst
    sources:
    - title: 'Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG'
      url: https://arxiv.org/abs/2501.09136
    - title: Active Retrieval Augmented Generation (FLARE)
      url: https://arxiv.org/abs/2305.06983
  - id: self-rag
    family: rag
    name: Self-RAG
    lab_workflow: rag:self-rag
    summary: The model decides when to retrieve, then critiques its own passages and draft for support and usefulness.
    when_to_use: Answers must be cited and checked against sources; some questions need no retrieval at all.
    when_not_to_use: You can't fine-tune or prompt a critic reliably; latency-bound chat.
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: vectors
      label: Vector index
      type: database
      role: Finds passages by meaning
    - id: decide
      label: Retrieve? gate
      type: cloud
      role: Decides whether this question needs retrieval
    - id: retriever
      label: Retriever
      type: backend
      role: Fetches passages when the gate says yes
    - id: critic
      label: Self-critic
      type: cloud
      role: 'Rates each passage and draft: relevant, supported, useful'
    - id: select
      label: Best-supported draft
      type: backend
      role: Keeps the draft the critic rates highest
    connections:
    - - question
      - decide
      - question
    - - decide
      - retriever
      - if needed
    - - retriever
      - vectors
      - search
    - - vectors
      - llm
      - passages
    - - decide
      - llm
      - if not
    - - llm
      - critic
      - drafts
    - - critic
      - select
      - scores
    - - select
      - answer
      - answer with citations
    parameters:
    - name: candidates
      default: 3
      what: Drafts generated and compared per question.
      range:
      - 1
      - 6
    - name: support_threshold
      default: 0.7
      what: Minimum 'supported by source' rating to keep a claim.
      range:
      - 0.3
      - 0.95
    - *id001
    tradeoffs:
      latency: high
      cost: high
      accuracy: high
      complexity: high
    signals:
    - citations
    - cite
    - sources
    - fact-check
    - hallucination
    - grounded
    - faithful
    - compliance
    - evidence
    - verify
    sources:
    - title: 'Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection'
      url: https://arxiv.org/abs/2310.11511
  - id: reranked-rag
    family: rag
    name: Reranked (two-stage) retrieval
    lab_workflow: rag:reranked-rag
    summary: Fetch a wide set cheaply, then re-score them with a stronger reranker and keep the best few.
    when_to_use: The right passage is usually in the top 50 but not the top 5; precision matters more than a few
      hundred ms.
    when_not_to_use: Tiny corpora; strict latency; when first-stage recall is already poor (reranking can't find
      what wasn't fetched).
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: vectors
      label: Vector index
      type: database
      role: Finds passages by meaning
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: retriever
      label: First-stage retriever
      type: backend
      role: Fetches a wide candidate set quickly
    - id: reranker
      label: Reranker
      type: cloud
      role: Scores each question-passage pair with a cross-encoder
    connections:
    - - question
      - retriever
      - query
    - - retriever
      - vectors
      - search
    - - vectors
      - retriever
      - top 50
    - - retriever
      - reranker
      - candidates
    - - reranker
      - llm
      - top 5
    - - llm
      - answer
      - answer
    parameters:
    - name: candidates
      default: 50
      what: Passages the first stage fetches.
      range:
      - 10
      - 200
    - name: rerank_top_n
      default: 5
      what: Passages kept after reranking.
      range:
      - 1
      - 20
    - name: reranker
      default: cross-encoder
      what: Which reranker scores the pairs.
      options:
      - cross-encoder
      - llm-reranker
      - none
    tradeoffs:
      latency: medium
      cost: medium
      accuracy: high
      complexity: medium
    signals:
    - precision
    - accuracy
    - relevance
    - large corpus
    - many documents
    - search quality
    - legal
    - long documents
    sources:
    - title: Passage Re-ranking with BERT
      url: https://arxiv.org/abs/1901.04085
    - title: 'Retrieval-Augmented Generation for Large Language Models: A Survey'
      url: https://arxiv.org/abs/2312.10997
  - id: rag-fusion
    family: rag
    name: Multi-query RAG-Fusion
    lab_workflow: rag:rag-fusion
    summary: Rewrite the question several ways, search each, and merge the results with rank fusion.
    when_to_use: Ambiguous questions where one phrasing misses relevant passages.
    when_not_to_use: Precise factual lookups; the rewrites can drift off topic and add cost.
    components:
    - id: question
      label: Question
      type: frontend
      role: Takes the user's question in
    - id: vectors
      label: Vector index
      type: database
      role: Finds passages by meaning
    - id: answer
      label: Answer
      type: external
      role: Returns the answer to the user
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: rewriter
      label: Query rewriter
      type: cloud
      role: Writes several variants of the question
    - id: fuse
      label: Rank fusion
      type: backend
      role: Merges the result lists
    connections:
    - - question
      - rewriter
      - question
    - - rewriter
      - vectors
      - 3-5 queries
    - - vectors
      - fuse
      - result lists
    - - fuse
      - llm
      - top passages
    - - llm
      - answer
      - answer
    parameters:
    - name: query_variants
      default: 4
      what: Rewrites per question.
      range:
      - 2
      - 8
    - name: rrf_k
      default: 60
      what: Fusion constant.
      range:
      - 10
      - 100
    - *id001
    tradeoffs:
      latency: medium
      cost: medium
      accuracy: medium
      complexity: low
    signals:
    - ambiguous
    - vague
    - broad
    - exploratory
    - recall
    - synonyms
    - search
    sources:
    - title: 'RAG-Fusion: a New Take on Retrieval-Augmented Generation'
      url: https://arxiv.org/abs/2402.03367
  - id: react
    family: agent
    name: ReAct loop
    lab_workflow: pattern:react
    summary: The model alternates between thinking and calling a tool, reading each result before the next step.
    when_to_use: 'Open-ended tasks where the next step depends on what the last tool returned: lookups, debugging,
      small automations.'
    when_not_to_use: Long fixed procedures (plan them); tasks that need parallel work; no step cap.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: tools
      label: Tools
      type: external
      role: Search, APIs and code the agent can call
    - id: loop
      label: Think-act loop
      type: backend
      role: Runs think, act, observe until done
    connections:
    - - task
      - loop
      - goal
    - - loop
      - llm
      - history
    - - llm
      - loop
      - thought + action
    - - loop
      - tools
      - call
    - - tools
      - loop
      - observation
    - - loop
      - result
      - final answer
    parameters:
    - name: max_iterations
      default: 10
      what: Steps before the loop must stop.
      range:
      - 2
      - 30
    - name: model_tier
      default: medium
      what: Reasoning strength of the single model.
      options:
      - small
      - medium
      - large
    - name: tool_set
      default: core
      what: Tools exposed; more tools mean more wrong picks.
      options:
      - core
      - extended
    tradeoffs:
      latency: medium
      cost: medium
      accuracy: medium
      complexity: low
    signals:
    - code
    - repo
    - codebase
    - tool use
    - search the code
    - shell
    - tools
    - api
    - lookup
    - search
    - debug
    - assistant
    - automation
    - open-ended
    - exploratory
    - chatbot
    sources:
    - title: 'ReAct: Synergizing Reasoning and Acting in Language Models'
      url: https://arxiv.org/abs/2210.03629
    - title: Building effective agents (Anthropic)
      url: https://www.anthropic.com/engineering/building-effective-agents
  - id: plan-and-execute
    family: agent
    name: Plan-and-execute
    lab_workflow: pattern:plan-act-verify
    summary: Write the whole plan first, run its steps with tools, and re-plan only if a step fails.
    when_to_use: 'Multi-step jobs with a predictable shape: reports, migrations, data pulls. Cheaper than thinking
      at every step.'
    when_not_to_use: Tasks where early results change everything; a plan made blind tends to break.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: tools
      label: Tools
      type: external
      role: Search, APIs and code the agent can call
    - id: planner
      label: Planner
      type: cloud
      role: Writes the ordered list of steps
    - id: executor
      label: Executor
      type: backend
      role: Runs one step at a time with tools
    - id: replanner
      label: Re-planner
      type: cloud
      role: Revises the plan when a step fails
    connections:
    - - task
      - planner
      - goal
    - - planner
      - executor
      - steps
    - - executor
      - tools
      - call
    - - tools
      - executor
      - result
    - - executor
      - replanner
      - on failure
    - - replanner
      - executor
      - new steps
    - - executor
      - result
      - outputs
    parameters:
    - name: max_steps
      default: 8
      what: Longest plan accepted.
      range:
      - 2
      - 25
    - name: planner_tier
      default: large
      what: Planning needs the strongest model; execution can use a cheaper one.
      options:
      - medium
      - large
    - name: replan_on_failure
      default: true
      what: Whether a failed step triggers a new plan.
      options:
      - true
      - false
    tradeoffs:
      latency: medium
      cost: medium
      accuracy: medium
      complexity: medium
    signals:
    - feature
    - implement
    - build a
    - roadmap
    - multi-step
    - workflow
    - report
    - migration
    - pipeline
    - batch
    - steps
    - process
    - etl
    - long task
    sources:
    - title: Plan-and-Solve Prompting
      url: https://arxiv.org/abs/2305.04091
    - title: 'ReWOO: Decoupling Reasoning from Observations for Efficient Augmented Language Models'
      url: https://arxiv.org/abs/2305.18323
    - title: Building effective agents (Anthropic)
      url: https://www.anthropic.com/engineering/building-effective-agents
  - id: reflexion
    family: agent
    name: Reflexion
    lab_workflow: pattern:reflect-retry
    summary: After a failed try, the agent writes what went wrong into memory and uses it on the next attempt.
    when_to_use: 'Tasks with a clear pass/fail signal (tests, checks) where retries can learn: coding, puzzles,
      games.'
    when_not_to_use: No reliable feedback signal; one-shot answers; costs that can't take several full attempts.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: tools
      label: Tools
      type: external
      role: Search, APIs and code the agent can call
    - id: memory
      label: Memory
      type: database
      role: Keeps notes and past steps
    - id: actor
      label: Actor
      type: cloud
      role: Attempts the task using past reflections
    - id: evaluator
      label: Evaluator
      type: backend
      role: Runs tests or checks and scores the attempt
    - id: reflector
      label: Self-reflection
      type: cloud
      role: Writes lessons from the failure
    connections:
    - - task
      - actor
      - goal
    - - memory
      - actor
      - past lessons
    - - actor
      - tools
      - act
    - - actor
      - evaluator
      - attempt
    - - evaluator
      - reflector
      - failure details
    - - reflector
      - memory
      - lesson
    - - evaluator
      - result
      - if passing
    parameters:
    - name: max_trials
      default: 3
      what: Attempts before giving up.
      range:
      - 1
      - 8
    - name: memory_size
      default: 3
      what: Past reflections kept in the prompt.
      range:
      - 1
      - 10
    - name: evaluator
      default: unit-tests
      what: How an attempt is scored.
      options:
      - unit-tests
      - llm-judge
      - exact-match
    tradeoffs:
      latency: high
      cost: high
      accuracy: high
      complexity: medium
    signals:
    - failing tests
    - flaky
    - tests
    - coding
    - retry
    - pass/fail
    - benchmark
    - learn from mistakes
    - bug fix
    - verifiable
    - check
    sources:
    - title: 'Reflexion: Language Agents with Verbal Reinforcement Learning'
      url: https://arxiv.org/abs/2303.11366
  - id: lats
    family: agent
    name: Tree search (LATS)
    lab_workflow: pattern:tree-search
    summary: Explore several branches of actions, score them, and back up to the best one, like a game-playing search.
    when_to_use: 'Hard problems with a checkable result where one path often dead-ends: tough coding, web navigation,
      math.'
    when_not_to_use: Anything latency- or cost-sensitive; it runs many branches, each a full agent trace.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: tools
      label: Tools
      type: external
      role: Search, APIs and code the agent can call
    - id: expander
      label: Branch generator
      type: cloud
      role: Proposes several next actions from a state
    - id: valuer
      label: Value scorer
      type: cloud
      role: Estimates how promising each branch is
    - id: tree
      label: Search tree
      type: database
      role: Keeps visited states, scores and reflections
    - id: env
      label: Environment
      type: external
      role: Runs actions and returns real feedback
    connections:
    - - task
      - tree
      - root state
    - - tree
      - expander
      - pick a node
    - - expander
      - env
      - actions
    - - env
      - valuer
      - feedback
    - - valuer
      - tree
      - scores
    - - tree
      - result
      - best path
    - - expander
      - tools
      - call
    parameters:
    - name: branching_factor
      default: 3
      what: Actions tried per node.
      range:
      - 2
      - 6
    - name: max_depth
      default: 5
      what: Longest path explored.
      range:
      - 2
      - 10
    - name: search_budget
      default: 20
      what: Total node expansions allowed.
      range:
      - 5
      - 100
    tradeoffs:
      latency: high
      cost: high
      accuracy: high
      complexity: high
    signals:
    - hard problems
    - search
    - backtracking
    - math
    - puzzle
    - web navigation
    - verifiable
    - competitive
    - best of n
    - dead ends
    sources:
    - title: Language Agent Tree Search Unifies Reasoning Acting and Planning in Language Models
      url: https://arxiv.org/abs/2310.04406
  - id: router
    family: agent
    name: Router
    lab_workflow: pattern:router
    summary: Classify the request once and send it to the one specialist prompt, model or workflow that handles
      it best.
    when_to_use: Distinct request types (billing, bug, how-to) each needing different handling; easy and hard cases
      that deserve different models.
    when_not_to_use: Requests that mix categories; categories you can't define; a single generalist already does
      well.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: llm
      label: Model
      type: cloud
      role: Writes the answer from what it is given
    - id: classifier
      label: Classifier
      type: cloud
      role: Labels the request and picks a route
    - id: billing
      label: Specialist A
      type: backend
      role: Handles one category
    - id: tech
      label: Specialist B
      type: backend
      role: Handles another category
    - id: general
      label: Fallback
      type: backend
      role: Handles anything unrecognised
    connections:
    - - task
      - classifier
      - request
    - - classifier
      - billing
      - category A
    - - classifier
      - tech
      - category B
    - - classifier
      - general
      - other
    - - billing
      - llm
      - prompt
    - - tech
      - llm
      - prompt
    - - general
      - llm
      - prompt
    - - llm
      - result
      - reply
    parameters:
    - name: router_tier
      default: small
      what: Model that classifies. Small and fast is usually enough.
      options:
      - small
      - medium
    - name: routes
      default: 3
      what: How many specialist routes exist.
      range:
      - 2
      - 12
    - name: confidence_floor
      default: 0.6
      what: Below this the request goes to the fallback.
      range:
      - 0.3
      - 0.95
    tradeoffs:
      latency: low
      cost: low
      accuracy: medium
      complexity: low
    signals:
    - triage
    - categories
    - classify
    - routing
    - support
    - tickets
    - intents
    - inbox
    - customer
    - different types
    sources:
    - title: Building effective agents (Anthropic)
      url: https://www.anthropic.com/engineering/building-effective-agents
    - title: 'Multi-agent (LangChain docs: subagents, handoffs, router)'
      url: https://docs.langchain.com/oss/python/langchain/multi-agent
  - id: orchestrator-workers
    family: agent
    name: Orchestrator-workers
    lab_workflow: pattern:orchestrator-workers
    summary: A lead model splits the job at run time, hands pieces to workers (in parallel), and merges what they
      return.
    when_to_use: 'Subtasks can''t be listed in advance: research across many sources, edits across many files.'
    when_not_to_use: Small tasks (overhead exceeds gain); subtasks that depend tightly on each other.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: tools
      label: Tools
      type: external
      role: Search, APIs and code the agent can call
    - id: memory
      label: Memory
      type: database
      role: Keeps notes and past steps
    - id: lead
      label: Orchestrator
      type: cloud
      role: Plans and splits the job, then merges results
    - id: w1
      label: Worker 1
      type: cloud
      role: Does one subtask
    - id: w2
      label: Worker 2
      type: cloud
      role: Does another subtask
    - id: w3
      label: Worker 3
      type: cloud
      role: Does another subtask
    connections:
    - - task
      - lead
      - goal
    - - lead
      - w1
      - subtask
    - - lead
      - w2
      - subtask
    - - lead
      - w3
      - subtask
    - - w1
      - tools
      - call
    - - w2
      - tools
      - call
    - - w3
      - tools
      - call
    - - w1
      - lead
      - findings
    - - w2
      - lead
      - findings
    - - w3
      - lead
      - findings
    - - lead
      - memory
      - plan
    - - lead
      - result
      - merged output
    parameters:
    - name: max_workers
      default: 3
      what: Workers running at once.
      range:
      - 1
      - 10
    - name: orchestrator_tier
      default: large
      what: Strength of the splitting model.
      options:
      - medium
      - large
    - name: worker_tier
      default: medium
      what: Cheaper tier for the pieces.
      options:
      - small
      - medium
    - name: max_iterations
      default: 3
      what: Rounds of split and merge.
      range:
      - 1
      - 8
    tradeoffs:
      latency: medium
      cost: high
      accuracy: high
      complexity: high
    signals:
    - large codebase
    - parallel tasks
    - monorepo
    - research
    - many files
    - parallel
    - codebase
    - multiple sources
    - report
    - large task
    - breadth
    - survey
    - refactor
    sources:
    - title: Building effective agents (Anthropic)
      url: https://www.anthropic.com/engineering/building-effective-agents
    - title: How we built our multi-agent research system (Anthropic)
      url: https://www.anthropic.com/engineering/multi-agent-research-system
  - id: evaluator-optimizer
    family: agent
    name: Evaluator-optimizer
    lab_workflow: pattern:evaluator-optimizer
    summary: One model drafts, another critiques against clear criteria, and the draft is revised until it passes.
    when_to_use: 'Quality criteria are explicit and iteration measurably helps: translation, writing, code with
      tests.'
    when_not_to_use: No clear criteria; first drafts are already good; judge and writer share the same blind spots.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: writer
      label: Generator
      type: cloud
      role: Writes or revises the draft
    - id: critic
      label: Evaluator
      type: cloud
      role: Scores the draft against the criteria and says what to fix
    - id: rubric
      label: Criteria
      type: database
      role: The checklist the evaluator uses
    connections:
    - - task
      - writer
      - brief
    - - writer
      - critic
      - draft
    - - rubric
      - critic
      - criteria
    - - critic
      - writer
      - feedback
    - - critic
      - result
      - if passing
    parameters:
    - name: max_iterations
      default: 3
      what: Revision rounds.
      range:
      - 1
      - 6
    - name: critic_model_tier
      default: medium
      what: Tier of the critic. A stronger critic catches more, costs more.
      options:
      - small
      - medium
      - large
    - name: pass_score
      default: 8
      what: Score out of 10 that ends the loop.
      range:
      - 5
      - 10
    tradeoffs:
      latency: high
      cost: medium
      accuracy: high
      complexity: medium
    signals:
    - fix
    - bug
    - tests
    - failing test
    - refactor
    - code review
    - quality bar
    - quality
    - writing
    - translation
    - review
    - rubric
    - polish
    - draft
    - edit
    - tone
    - criteria
    - content
    sources:
    - title: Building effective agents (Anthropic)
      url: https://www.anthropic.com/engineering/building-effective-agents
    - title: 'Self-Refine: Iterative Refinement with Self-Feedback'
      url: https://arxiv.org/abs/2303.17651
  - id: supervisor
    family: agent
    name: Supervisor multi-agent
    lab_workflow: pattern:supervisor
    summary: One supervisor agent picks which specialist acts next and gets every result back.
    when_to_use: A few clearly different skills (research, code, write) and you want one place to control flow and
      keep context.
    when_not_to_use: One skill is enough; the supervisor becomes the bottleneck and each hop adds cost.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: supervisor
      label: Supervisor
      type: cloud
      role: Chooses the next specialist and decides when done
    - id: researcher
      label: Researcher
      type: cloud
      role: Finds information
    - id: coder
      label: Coder
      type: cloud
      role: Writes and runs code
    - id: writer
      label: Writer
      type: cloud
      role: Drafts the final text
    - id: tools
      label: Tools
      type: external
      role: Search, code runner and files
    connections:
    - - task
      - supervisor
      - goal
    - - supervisor
      - researcher
      - delegate
    - - supervisor
      - coder
      - delegate
    - - supervisor
      - writer
      - delegate
    - - researcher
      - supervisor
      - result
    - - coder
      - supervisor
      - result
    - - writer
      - supervisor
      - result
    - - researcher
      - tools
      - call
    - - coder
      - tools
      - call
    - - supervisor
      - result
      - final
    parameters:
    - name: specialists
      default: 3
      what: Agents the supervisor can call.
      range:
      - 2
      - 8
    - name: max_handoffs
      default: 8
      what: Delegations before it must finish.
      range:
      - 2
      - 25
    - name: supervisor_tier
      default: large
      what: Routing quality sets overall quality.
      options:
      - medium
      - large
    tradeoffs:
      latency: high
      cost: high
      accuracy: high
      complexity: high
    signals:
    - multi-agent
    - specialists
    - roles
    - team of agents
    - research and write
    - delegate
    - coordination
    - several skills
    sources:
    - title: 'Multi-agent (LangChain docs: subagents, handoffs, router)'
      url: https://docs.langchain.com/oss/python/langchain/multi-agent
    - title: 'AutoGen: Enabling Next-Gen LLM Applications via Multi-Agent Conversation'
      url: https://arxiv.org/abs/2308.08155
    - title: 'MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework'
      url: https://arxiv.org/abs/2308.00352
  - id: hierarchical
    family: agent
    name: Hierarchical multi-agent
    lab_workflow: pattern:hierarchical
    summary: Supervisors manage their own teams, and a top-level agent manages the supervisors.
    when_to_use: Many agents or tools (say 10+) that don't fit one supervisor's context, grouped into clear domains.
    when_not_to_use: Small teams; each added layer adds latency, cost and places for the message to get garbled.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: top
      label: Top supervisor
      type: cloud
      role: Splits the goal by domain
    - id: sup_a
      label: Team lead A
      type: cloud
      role: Runs the research team
    - id: sup_b
      label: Team lead B
      type: cloud
      role: Runs the build team
    - id: a1
      label: Researcher
      type: cloud
      role: Team A specialist
    - id: a2
      label: Analyst
      type: cloud
      role: Team A specialist
    - id: b1
      label: Developer
      type: cloud
      role: Team B specialist
    - id: b2
      label: Tester
      type: cloud
      role: Team B specialist
    connections:
    - - task
      - top
      - goal
    - - top
      - sup_a
      - domain A
    - - top
      - sup_b
      - domain B
    - - sup_a
      - a1
      - subtask
    - - sup_a
      - a2
      - subtask
    - - sup_b
      - b1
      - subtask
    - - sup_b
      - b2
      - subtask
    - - a1
      - sup_a
      - result
    - - a2
      - sup_a
      - result
    - - b1
      - sup_b
      - result
    - - b2
      - sup_b
      - result
    - - sup_a
      - top
      - report
    - - sup_b
      - top
      - report
    - - top
      - result
      - final
    parameters:
    - name: depth
      default: 2
      what: Levels of management.
      range:
      - 2
      - 4
    - name: team_size
      default: 2
      what: Specialists per team lead.
      range:
      - 2
      - 6
    - name: max_handoffs
      default: 12
      what: Total delegations allowed.
      range:
      - 4
      - 40
    tradeoffs:
      latency: high
      cost: high
      accuracy: high
      complexity: high
    signals:
    - large system
    - many agents
    - enterprise
    - departments
    - software team
    - domains
    - scale
    - complex projects
    sources:
    - title: 'Multi-agent (LangChain docs: subagents, handoffs, router)'
      url: https://docs.langchain.com/oss/python/langchain/multi-agent
    - title: 'MetaGPT: Meta Programming for A Multi-Agent Collaborative Framework'
      url: https://arxiv.org/abs/2308.00352
  - id: swarm-handoffs
    family: agent
    name: Swarm / handoffs
    lab_workflow: pattern:handoffs
    summary: Agents pass the conversation to each other directly; whoever is best placed takes over, with no central
      boss.
    when_to_use: A conversation that moves between roles (sales to support to billing), where the current agent
      knows who is next.
    when_not_to_use: You need central control, audit of every decision, or parallel work; loops between agents are
      possible.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: tools
      label: Tools
      type: external
      role: Search, APIs and code the agent can call
    - id: triage
      label: Triage agent
      type: cloud
      role: Greets, then hands off
    - id: sales
      label: Sales agent
      type: cloud
      role: Owns the sales stage
    - id: support
      label: Support agent
      type: cloud
      role: Owns the support stage
    - id: billing
      label: Billing agent
      type: cloud
      role: Owns refunds and invoices
    connections:
    - - task
      - triage
      - message
    - - triage
      - sales
      - handoff
    - - triage
      - support
      - handoff
    - - support
      - billing
      - handoff
    - - billing
      - support
      - hand back
    - - support
      - tools
      - call
    - - billing
      - tools
      - call
    - - support
      - result
      - reply
    parameters:
    - name: max_handoffs
      default: 6
      what: Passes allowed per conversation, to stop ping-pong.
      range:
      - 1
      - 15
    - name: history_shared
      default: full
      what: What the next agent sees of the conversation.
      options:
      - full
      - summary
      - none
    - name: agents
      default: 3
      what: Agents in the swarm.
      range:
      - 2
      - 8
    tradeoffs:
      latency: medium
      cost: medium
      accuracy: medium
      complexity: medium
    signals:
    - customer
    - conversation
    - handoff
    - sales
    - support
    - chat
    - roles
    - voice
    - stages
    - tickets
    sources:
    - title: Swarm (experimental, educational), OpenAI
      url: https://github.com/openai/swarm
    - title: Handoffs, OpenAI Agents SDK
      url: https://openai.github.io/openai-agents-python/handoffs/
    - title: 'Multi-agent (LangChain docs: subagents, handoffs, router)'
      url: https://docs.langchain.com/oss/python/langchain/multi-agent
  - id: blackboard
    family: agent
    name: Blackboard
    lab_workflow: pattern:blackboard
    summary: Agents read and write a shared board; whoever has something useful to add acts next.
    when_to_use: 'Problems with no fixed order where partial results help others: data discovery, diagnosis, investigations.'
    when_not_to_use: Simple pipelines; you need predictable cost or order; a noisy board fills with junk.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: board
      label: Blackboard
      type: messagebus
      role: Shared state every agent reads and writes
    - id: controller
      label: Controller
      type: cloud
      role: Picks which agent acts next from the board
    - id: a1
      label: Specialist 1
      type: cloud
      role: Adds findings it can contribute
    - id: a2
      label: Specialist 2
      type: cloud
      role: Adds findings it can contribute
    - id: a3
      label: Specialist 3
      type: cloud
      role: Adds findings it can contribute
    connections:
    - - task
      - board
      - goal
    - - board
      - controller
      - state
    - - controller
      - a1
      - your turn
    - - controller
      - a2
      - your turn
    - - controller
      - a3
      - your turn
    - - a1
      - board
      - post
    - - a2
      - board
      - post
    - - a3
      - board
      - post
    - - board
      - result
      - agreed answer
    parameters:
    - name: max_rounds
      default: 6
      what: Select-and-act rounds.
      range:
      - 2
      - 15
    - name: agents
      default: 3
      what: Specialists that can post.
      range:
      - 2
      - 10
    - name: stop_rule
      default: consensus
      what: What ends the work.
      options:
      - consensus
      - budget
      - controller-decides
    tradeoffs:
      latency: high
      cost: medium
      accuracy: medium
      complexity: high
    signals:
    - data lake
    - discovery
    - diagnosis
    - investigation
    - shared state
    - no fixed order
    - collaboration
    - incident
    - root cause
    sources:
    - title: Exploring Advanced LLM Multi-Agent Systems Based on Blackboard Architecture
      url: https://arxiv.org/abs/2507.01701
    - title: LLM-Based Multi-Agent Blackboard System for Information Discovery in Data Science
      url: https://arxiv.org/abs/2510.01285
  - id: human-in-the-loop
    family: agent
    name: Human-in-the-loop approvals
    lab_workflow: pattern:approval-gate
    summary: The agent works on its own but stops at risky steps and waits for a person to approve, edit or reject.
    when_to_use: Actions that cost money, change data or contact customers; regulated work; early trust-building
      with a new agent.
    when_not_to_use: High volume with low risk (approval fatigue); nobody available to answer in time.
    components:
    - id: task
      label: Task
      type: frontend
      role: Takes the task in
    - id: result
      label: Result
      type: external
      role: Returns the finished work
    - id: tools
      label: Tools
      type: external
      role: Search, APIs and code the agent can call
    - id: memory
      label: Memory
      type: database
      role: Keeps notes and past steps
    - id: agent
      label: Agent
      type: cloud
      role: Plans and acts
    - id: gate
      label: Approval gate
      type: security
      role: Pauses risky actions and saves state
    - id: human
      label: Reviewer
      type: frontend
      role: Approves, edits or rejects
    - id: policy
      label: Risk rules
      type: database
      role: Which actions need a person
    connections:
    - - task
      - agent
      - request
    - - agent
      - gate
      - proposed action
    - - policy
      - gate
      - rules
    - - gate
      - human
      - needs approval
    - - human
      - gate
      - approve / edit / reject
    - - gate
      - tools
      - approved action
    - - tools
      - agent
      - result
    - - gate
      - memory
      - paused state
    - - agent
      - result
      - outcome
    parameters:
    - name: approval_required_for
      default: writes
      what: Which actions pause for a person.
      options:
      - writes
      - spend
      - external-messages
      - all
    - name: timeout_hours
      default: 24
      what: How long a paused run waits before it is dropped.
      range:
      - 1
      - 168
    - name: allow_edit
      default: true
      what: Whether the reviewer can change the action, not just approve it.
      options:
      - true
      - false
    tradeoffs:
      latency: high
      cost: low
      accuracy: high
      complexity: medium
    signals:
    - approval
    - human review
    - compliance
    - risky
    - refund
    - payments
    - regulated
    - sign-off
    - tickets
    - escalation
    - safety
    - audit
    sources:
    - title: Interrupts, LangGraph docs
      url: https://docs.langchain.com/oss/python/langgraph/interrupts
    - title: Building effective agents (Anthropic)
      url: https://www.anthropic.com/engineering/building-effective-agents
---

# Architecture catalog

A garage of known RAG and agent architectures. Each entry is a car you can swap in: its
parts (as canvas blocks), the links between them, the knobs worth turning, what it costs,
and where it comes from. Nothing here calls a model; the catalog and the ranking are plain
data and rules.

## Entries

Every entry in the frontmatter has: `id`, `family` (rag or agent), `name`, `summary`,
`when_to_use`, `when_not_to_use`, `components` (id, label, type, role), `connections`
(from, to, label), `parameters` (name, default, range or options, what it changes),
`tradeoffs` (latency, cost, accuracy, complexity: low, medium or high), `signals` and
`sources` (title and URL). Component `type` is one of the canvas block kinds: frontend,
backend, database, cloud, security, messagebus, external. By convention here: models are
`cloud`, tools and search are `external`, stores and indexes are `database`, approval
gates are `security`, shared boards are `messagebus`.

Every connection must name components that exist, and every entry must cite at least one
source. The tests check both.

## Ranking

The ranking is deterministic and explains itself in the use case's own words.

- Intents (`intents`): what the use case asks for, read from its phrases (any word form) and
  patterns. "Answer from our policy docs" is the documents intent (retrieval designs); "refunds
  over $200 need a manager" is approval (human-in-the-loop); "several sources or tools" is
  agentic RAG; "route tickets by category" the router; "plan then do" plan-and-execute; a code
  review or a bug fix the loops that check and improve code. Each intent adds its `fits` points
  once, and its reason quotes only the words that said it, not the whole sentence: a short
  clause whole ("because you said 'anything over $200 needs a manager'"), in a long one the
  matched words and up to three after them (never across "and", "before" and the like), else
  the two before. Quotes of one design that overlap are joined into one reason, so each design
  shows its own matched phrases ("from our help center docs", "answers must be cited").
- Signals: an entry signal the use case says adds `use_case_signal`, at most `signal_cap` per
  entry. Signals the repo's files point at (`repo_rules`: stack, languages, lots of docs or
  files) add `repo_signal` each and never list a design alone: 900 `.sql` files are not a
  reason to pick agentic RAG for fixing bugs.
- Preferences: words that ask for speed, low cost, accuracy or simplicity (`preferences`)
  favour entries whose trade-off is on that side, `preference_weight` per level of fit, and a
  clash subtracts the same.
- The local embedding model (skill_models), when it is on this machine, adds its similarity
  between the use case and the design as one more signal (up to `embedding_weight`); without
  it, the rules alone decide.
- An entry needs `min_points` and an intent or a signal from the use case itself. Its fit is a
  label, not a number: Strong Fit, Good Fit or Possible (`fit_levels`). Ties go by id, so the
  order never changes.
- When nothing reaches `min_points` (`empty_state`), say why instead of a bare "nothing
  matched": the words that did match ("Only 'support' matched, too little to rank on"), the
  designs they pointed at under "Close, not a fit yet" (never as picks), and what to add: the
  `ask` of each close design's strongest intent the use case hasn't said, and a few of its
  signals. Both are true: each would add points to that design. When no word matched, say
  that, and point at the catalog below.

## Trying a design in the Lab

Every entry names the Lab workflow that runs it (`lab_workflow`), so "Use this design" in
"Nothing yet" opens something measurable rather than a generic starter. RAG entries open the
matching rag-workflows workflow, measured on the document Q&A bench as they are. Agent entries
open their workflow-patterns pattern, set to the use case's discipline (`lab_handoff`) so the
skills matched to its steps and the bench it is measured on fit the work. Where the Lab can't
run the whole design (`lab_note`), the note says what is left out; never open a stand-in
without saying so.

## Explaining

On request only, one helper-model call writes a short paragraph for each of the top three
picks, in terms of the use case. The ranking never depends on it.
With no picks there is nothing to explain: the offer isn't shown, and if asked anyway no
model is called and the note says so (`explain_nothing`).

## Explain prompt

You explain why an agent architecture fits a use case. For each architecture given, write
two or three plain sentences about THIS use case: what the architecture would do for it and
the main thing to watch. Use only the facts given about the architecture and the use case.
Do not invent numbers, benchmarks or product names. No headings, no bullet lists.

## Sources

Each entry lists its own sources. The research behind them:

- Anthropic, "Building effective agents": https://www.anthropic.com/engineering/building-effective-agents
- Anthropic, "How we built our multi-agent research system": https://www.anthropic.com/engineering/multi-agent-research-system
- RAG survey (naive, advanced, modular): https://arxiv.org/abs/2312.10997
- Agentic RAG survey: https://arxiv.org/abs/2501.09136
- LangChain multi-agent patterns: https://docs.langchain.com/oss/python/langchain/multi-agent
- OpenAI Agents SDK handoffs: https://openai.github.io/openai-agents-python/handoffs/
- Papers for RAG, HyDE, CRAG, GraphRAG, Adaptive-RAG, Self-RAG, ColPali, ReAct, Reflexion, LATS,
  Plan-and-Solve, ReWOO, Self-Refine, AutoGen, MetaGPT and blackboard systems are linked
  from the entries that use them.

Trade-off ratings are judgement calls from these sources, not benchmarks: measure them in
the garage before trusting them.
