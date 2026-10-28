---
name: glossary
description: The plain-language meaning of every measurement word Rig shows (pts, pairs, arms, trial, change, baseline, lift, interval, pilot vs full, Docker sandbox ...), one short line each, used by the (?) next to a term the first time a page shows it.
values:
  # key: {term: as the page shows it, short: one plain sentence, aliases: older keys for it}. The
  # web app reads these from /api/glossary; a page passes the key to its (?) the first time it
  # shows the word.
  terms:
    pts:
      term: pts (pass-rate points)
      short: "Percentage points of tasks passed. Going from 40% of tasks passed to 52% is +12 pts."
    pair:
      term: pair
      short: "One task run twice, once with the change and once without, on the same setup. Comparing within a pair cancels out how hard that task is."
    pairs:
      term: pairs
      short: "How many tasks were run both ways, with the change and without it. More pairs give a narrower interval: 5 pairs is a hint, 30 a result."
    arms:
      term: arms
      short: "The two sides of a run: one arm with the change, one without (the baseline). Both arms run the same tasks on the same setup."
    trial:
      term: trial
      short: "One run of the agent on one task, which passes or fails its check."
    change:
      term: change
      short: "What is being tested: a skill, a workflow, a hook, a model or anything else you add to the agent."
      # The engine's word for it (a run's "treatment"): /api/glossary also answers under it.
      aliases: [treatment]
    baseline:
      term: baseline
      short: "The plain agent without the change, run on the same tasks, so there is something to compare against."
    held-out:
      term: held-out tasks
      short: "Tasks kept aside while a change was built or tuned, so its result isn't flattered by tasks it was shaped on."
    lift:
      term: lift
      short: "How much the change raised the share of tasks passed over the baseline, in pts. Negative lift means it made things worse."
    interval:
      term: 95% interval
      short: "The range the true lift most likely lies in, given how many pairs were run. If it spans zero, the result could be luck."
    pilot:
      term: pilot
      short: "A small first run, a few pairs, to see whether a full run is worth paying for. Its number is rough."
    full:
      term: full run
      short: "At least 20 pairs, and more as the budget pays for them, up to the pairs that tell a ±25 pts change from noise. Only then is it conclusive; its label says what the budget buys."
    pilot-vs-full:
      term: pilot vs full
      short: "A pilot runs each task once, to see if the change looks worth it. A full run grows with the budget up to the pairs a ±25 pts change needs, and its label says what the budget buys. Start with a pilot; pay for a full run if it looks promising."
    sandbox:
      term: Docker sandbox
      short: "An isolated test copy: each trial runs in a throwaway container with its own copy of the repo, so nothing touches your files and every trial starts the same."
    bench:
      term: bench
      short: "A fixed set of tasks with checks, the same every time, so different setups are measured on equal terms."
    task:
      term: task
      short: "One job for the agent with a check (a command) that decides pass or fail. Rig's files and API call it a scenario."
      # Older words for the same thing: /api/glossary also answers under these keys.
      aliases: [scenario]
    judged:
      term: judged
      short: "Scored by a model reading the result against written criteria, instead of by a command. Useful where no command can tell."
    rig-score:
      term: Rig score
      short: "One 0-100 number for how far the measured result can be trusted to help: the lift, how sure it is, and whether the run was valid."
    prior:
      term: prior
      short: "A starting guess of the effect before anything is measured. A run replaces it."
---

# Glossary

Rig measures changes to an agent, and the words for that (pts, pairs, intervals) are not
everyday words. Each one has a single plain sentence here. Pages show a small (?) next to a
term the first time it appears on that page; opening it shows the sentence. The same words
are used everywhere: a page never explains a term its own way.

## Rules

- One sentence (two at most), no other jargon in it: a definition that needs another term
  defines that one too, or says it in plain words.
- An example with numbers where it helps ("40% to 52% is +12 pts").
- Only the first appearance on a page gets the (?): a page full of them is noise.
- The (?) opens on hover and on keyboard focus after a short delay, and on a click or tap; it
  closes when the pointer or focus leaves, and on Esc. The sentence is read out with the term.
- A number with a unit says its unit where it first appears: "+2 pts (pass-rate points)", by
  the term's name in the (?).
