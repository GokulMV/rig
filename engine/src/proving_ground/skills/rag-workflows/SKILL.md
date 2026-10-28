---
name: rag-workflows
description: Retrieval-augmented generation architectures (naive, HyDE, corrective, hybrid, adaptive, agentic, graph, self-critiquing, reranked, fused) as runnable Lab workflows for the research discipline, each modelled on a published method, with the source named.
values:
  workflows:
    - id: naive-rag
      discipline: research
      name: Naive RAG
      source: "Lewis et al. 2020, Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks (retrieve, then generate)"
      steps:
        - {id: search, name: Search, does: "Search the documents for the question's key terms and list the best matches.", kind: do}
        - {id: read, name: Read the top documents, does: "Read the top few matching documents in full and note the passages that bear on the question.", kind: do}
        - {id: answer, name: Answer with citations, does: "Answer from the passages only, as shortly as the question allows, and cite the path of each document used. If they do not answer it, say it is not in the docs.", kind: do}
      edges: [[search, read], [read, answer]]
      harness: [cite-evidence]
    - id: hyde
      discipline: research
      name: HyDE (hypothetical answer first)
      source: "Gao et al. 2022, Precise Zero-Shot Dense Retrieval without Relevance Labels (HyDE: search with a hypothetical answer)"
      steps:
        - {id: hypothesise, name: Write a hypothetical answer, does: "Write the answer you expect the documents to give, in the documents' own words and shape, without looking anything up.", kind: think}
        - {id: search, name: Search with it, does: "Search the documents using phrases from the hypothetical answer, not only the question; list the best matches.", kind: do}
        - {id: read, name: Read the matches, does: "Read the matching documents in full; note where they confirm or contradict the hypothetical answer.", kind: do}
        - {id: answer, name: Answer from what was found, does: "Answer from the documents only, never from the hypothetical answer, and cite each document used. If they do not answer it, say it is not in the docs.", kind: do}
      edges: [[hypothesise, search], [search, read], [read, answer]]
      harness: [cite-evidence]
    - id: corrective-rag
      discipline: research
      name: Corrective RAG (grade, rewrite, search again)
      source: "Yan et al. 2024, Corrective Retrieval Augmented Generation (a retrieval evaluator triggers a corrective action)"
      steps:
        - {id: query, name: Write the search query, does: "Turn the question into search terms; on a retry, use what the grading said was missing.", kind: think}
        - {id: search, name: Search, does: "Search the documents with the query and list the best matches.", kind: do}
        - {id: grade, name: Grade relevance, does: "Judge whether the matches hold the answer: relevant, partly relevant or irrelevant, with the reason. If weak, send back to rewrite the query.", kind: judge}
        - {id: read, name: Read the relevant documents, does: "Read the documents graded relevant in full and note the passages that answer the question.", kind: do}
        - {id: answer, name: Answer with citations, does: "Answer from those passages only and cite each document used. If the search never found an answer, say it is not in the docs.", kind: do}
      edges: [[query, search], [search, grade], [grade, read], [read, answer]]
      loops: [[grade, query, 2]]
      harness: [cite-evidence]
    - id: hybrid-rag
      discipline: research
      name: Hybrid RAG (keyword and reading in parallel)
      source: "Hybrid retrieval practice: lexical and semantic rankings merged by reciprocal rank fusion (Cormack et al. 2009)"
      steps:
        - {id: terms, name: List the terms and the idea, does: "List exact terms, names and numbers to search for, and restate the question as a plain meaning.", kind: think}
        - {id: keyword, name: Keyword search, does: "Grep the documents for the exact terms and rank the files by how many terms they hold.", kind: do}
        - {id: semantic, name: Read for meaning, does: "Browse the document titles and openings for pages about the same idea, even in different words; rank them.", kind: do}
        - {id: merge, name: Merge the rankings, does: "Merge the two rankings, ranking documents found by both highest; drop duplicates and keep the newest of near-identical documents.", kind: think}
        - {id: read, name: Read the merged top, does: "Read the top merged documents in full and note the passages that answer the question.", kind: do}
        - {id: answer, name: Answer with citations, does: "Answer from those passages only and cite each document used. If they do not answer it, say it is not in the docs.", kind: do}
        - {id: verify, name: Check the citations, does: "Check that every cited document holds the evidence for the answer; list any that do not.", kind: check}
      edges: [[terms, keyword], [terms, semantic], [keyword, merge], [semantic, merge], [merge, read], [read, answer], [answer, verify]]
      loops: [[verify, read, 1]]
      harness: [cite-evidence]
    - id: adaptive-rag
      discipline: research
      name: Adaptive RAG (route by question complexity)
      source: "Jeong et al. 2024, Adaptive-RAG: Learning to Adapt Retrieval-Augmented Large Language Models through Question Complexity"
      steps:
        - {id: classify, name: Classify the question, does: "Class the question: simple (one document answers it) or complex (needs two or more documents, a comparison or a table). Name the class before going on.", kind: think}
        - {id: simple, name: Simple path, does: "Only for a simple question: search once, read the best document and note the answer passage. Skip this step for a complex question.", kind: do}
        - {id: complex, name: Multi-step path, does: "Only for a complex question: split it into the facts needed, find each fact's document, and follow links between documents. Skip this step for a simple question.", kind: do}
        - {id: answer, name: Answer with citations, does: "Answer from the passages found, shortly, citing each document used. If they do not answer it, say it is not in the docs.", kind: do}
        - {id: verify, name: Check the answer, does: "Check that the answer matches the passages and that the newest of any conflicting documents was used; if the path was too light, say so.", kind: check}
      edges: [[classify, simple], [classify, complex], [simple, answer], [complex, answer], [answer, verify]]
      loops: [[verify, classify, 1]]
      harness: [cite-evidence]
    - id: agentic-rag
      discipline: research
      name: Agentic RAG (plan, look up in parallel, synthesise, check)
      source: "Agentic RAG survey (Singh et al. 2025); Anthropic's orchestrator-workers pattern in Building effective agents"
      steps:
        - {id: plan, name: Plan the sub-questions, does: "Split the question into the smallest sub-questions whose answers combine into the answer; on a retry, add what the citation check found missing.", kind: think}
        - {id: lookup-a, name: Look up sub-question 1, does: "Find and read the document for the first sub-question; return the answer and the document path.", kind: do}
        - {id: lookup-b, name: Look up sub-question 2, does: "Find and read the document for the second sub-question; return the answer and the document path.", kind: do}
        - {id: lookup-c, name: Look up sub-question 3, does: "Find and read the document for any further sub-question; follow links between documents. Return answers and paths.", kind: do}
        - {id: synthesise, name: Synthesise, does: "Combine the sub-answers into one short answer; prefer the newest of conflicting documents; say it is not in the docs if a needed fact is missing.", kind: think}
        - {id: cite-check, name: Check the citations, does: "Check that every cited document holds the evidence it is cited for and that no needed document is missing; send back to plan if one is.", kind: check}
      edges: [[plan, lookup-a], [plan, lookup-b], [plan, lookup-c], [lookup-a, synthesise], [lookup-b, synthesise], [lookup-c, synthesise], [synthesise, cite-check]]
      loops: [[cite-check, plan, 2]]
      harness: [cite-evidence]
    - id: graph-rag
      discipline: research
      name: GraphRAG (entities and links first)
      source: "Edge et al. 2024, From Local to Global: A Graph RAG Approach to Query-Focused Summarization (entity graph with community summaries)"
      steps:
        - {id: entities, name: Find the entities, does: "Search the documents for the people, products, policies and numbers the question names, and list each with the documents that mention it.", kind: do}
        - {id: links, name: Map how they link, does: "Write GRAPH.md: each entity, the entities it is linked to, and the document that says so.", kind: think}
        - {id: summarise, name: Summarise each cluster, does: "For each group of closely linked entities, write a two-line summary of what the documents say about it, with the paths.", kind: do}
        - {id: answer, name: Answer from the graph, does: "Answer from the cluster summaries and the documents behind them, citing each document used. If they do not answer it, say it is not in the docs.", kind: do}
        - {id: verify, name: Check the citations, does: "Check that every cited document holds the evidence it is cited for; list any that do not.", kind: check}
      edges: [[entities, links], [links, summarise], [summarise, answer], [answer, verify]]
      loops: [[verify, links, 1]]
      harness: [cite-evidence]
    - id: self-rag
      discipline: research
      name: Self-RAG (retrieve on demand, critique itself)
      source: "Asai et al. 2023, Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection"
      steps:
        - {id: decide, name: Decide what to look up, does: "Decide whether the question needs the documents at all and, if so, which facts to look up; on a retry, look up what the critique said was unsupported.", kind: think}
        - {id: retrieve, name: Retrieve, does: "Search for and read only the documents needed for those facts; note the passages.", kind: do}
        - {id: draft, name: Draft the answer, does: "Draft a short answer from the passages, citing each document used.", kind: do}
        - {id: critique, name: Critique the draft, does: "Mark each sentence supported, partly supported or unsupported by the cited passages, and say whether the answer is useful. Send back if anything is unsupported.", kind: judge}
      edges: [[decide, retrieve], [retrieve, draft], [draft, critique]]
      loops: [[critique, decide, 2]]
      harness: [cite-evidence]
    - id: reranked-rag
      discipline: research
      name: Reranked RAG (wide search, then rerank)
      source: "Nogueira and Cho 2019, Passage Re-ranking with BERT (retrieve many cheaply, rerank few precisely)"
      steps:
        - {id: wide, name: Search wide, does: "Search the documents broadly for the question's terms and synonyms; list up to twenty candidate documents.", kind: do}
        - {id: rerank, name: Rerank the candidates, does: "Score each candidate by how directly it answers the question, with a one-line reason; keep the top five.", kind: judge}
        - {id: read, name: Read the top five, does: "Read the kept documents in full and note the passages that answer the question.", kind: do}
        - {id: answer, name: Answer with citations, does: "Answer from those passages only and cite each document used. If they do not answer it, say it is not in the docs.", kind: do}
      edges: [[wide, rerank], [rerank, read], [read, answer]]
      harness: [cite-evidence]
    - id: rag-fusion
      discipline: research
      name: RAG-Fusion (several queries, fused)
      source: "Rackauckas 2024, RAG-Fusion: a New Take on Retrieval-Augmented Generation (multiple queries merged by reciprocal rank fusion)"
      steps:
        - {id: queries, name: Write three queries, does: "Rewrite the question as three different search queries: the literal one, a broader one and one in the documents' likely wording.", kind: think}
        - {id: search-a, name: Search query 1, does: "Search with the first query and rank the matching documents.", kind: do}
        - {id: search-b, name: Search query 2, does: "Search with the second query and rank the matching documents.", kind: do}
        - {id: search-c, name: Search query 3, does: "Search with the third query and rank the matching documents.", kind: do}
        - {id: fuse, name: Fuse the rankings, does: "Merge the three rankings, ranking documents found by several queries highest; keep the top five.", kind: think}
        - {id: answer, name: Answer with citations, does: "Read the fused top documents and answer from them only, citing each document used. If they do not answer it, say it is not in the docs.", kind: do}
      edges: [[queries, search-a], [queries, search-b], [queries, search-c], [search-a, fuse], [search-b, fuse], [search-c, fuse], [fuse, answer]]
      harness: [cite-evidence]
---

# RAG workflows

Retrieval-augmented generation architectures as Lab workflows, so a person can measure whether
retrieval design matters on their own questions. They are for the research discipline and are
measured on the rag-qa bench by default. They sit apart from business-workflows because that
list requires every entry to have a parallel stage, a join and a loop, and the simplest RAG
architectures (naive, HyDE, corrective) are plain chains, with or without a retry loop.

Each is modelled on a published method (named in `source`). The "search" here is whatever the
agent has in the sandbox: grep, file listing and reading, since there is no vector store.
Models follow the step kind (starter-workflows: `model_for`).
