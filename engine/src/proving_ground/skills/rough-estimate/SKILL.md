---
name: rough-estimate
description: The instant, model-free guess of a skill's effect on a repo, shown the moment a skill is
  added.
values:
  base_points: 1
  per_shared_stack_term: 2
  max_shared_terms: 3
  stack_mismatch: -3
  tests_bonus: 3
  review_bonus: 1
  long_skill_chars: 12000
  long_skill_penalty: -3
  likely_min: -10
  likely_max: 12
  half_width: 15
  confidence: low
  # A repo's own skills get their rough guesses in one request (POST /api/estimate/batch), at most this many.
  batch_max: 100
  stack_terms:
  - aws
  - django
  - docker
  - fastapi
  - flask
  - go
  - golang
  - graphql
  - java
  - javascript
  - kotlin
  - kubernetes
  - laravel
  - next
  - node
  - php
  - postgres
  - pytest
  - python
  - rails
  - react
  - ruby
  - rust
  - sql
  - svelte
  - swift
  - terraform
  - typescript
  - vue
---

# Rough estimate

A number to look at the moment a skill lands on the canvas, before any model or run. It is a
deliberately wide guess and is always labelled **Rough**. A model estimate replaces it when one
is available; a run replaces both.

## Rules

1. Start at `base_points` (+1): a skill that is followed usually helps a little.
2. **Stack fit.** Compare the stack terms (`stack_terms`) found in the skill's text with those in
   the repo's summary and scenarios.
   - Each shared term adds `per_shared_stack_term` (+2), counting at most `max_shared_terms` (3).
   - If both name stack terms but share none, add `stack_mismatch` (−3): it was written for
     something else.
3. **Tests.** If the skill pushes test-running (tests, TDD, pytest, jest, vitest, coverage,
   assert) and the repo's scenarios are checked by tests, add `tests_bonus` (+3). Otherwise, if
   it adds a review or check before finishing, add `review_bonus` (+1).
4. **Length.** Over `long_skill_chars` (12,000 characters) it crowds the agent's context: add
   `long_skill_penalty` (−3).
5. Clamp the likely value to `likely_min`..`likely_max` (−10..+12 points).
6. The range is likely ± `half_width` (15 points). Confidence is always `low`.
7. The reason names each rule that fired, in plain words, and starts with
   "Rough guess from the skill's text and the repo, no model".
8. **Many at once.** Opening a repo asks for every skill's rough guess in one request, at most
   `batch_max` (100) skills; it never calls a model. Sharpening one stays one request, on a click.
