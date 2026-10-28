// GET /api/tutorial/tokens as the engine returned it (this branch): the words, the example and the
// recorded run. Regenerate with: curl -s 127.0.0.1:<port>/api/tutorial/tokens
import type { TokensTutorial } from "../lib/types";

export const TOKENS_TUTORIAL = {
    "text": {
        "home": {
            "title": "Rig Your Own Repo: Fewer Tokens",
            "title_done": "The Repo Tutorial: Fewer Tokens",
            "lead": "The same five steps in repo mode, on a tiny example repo: which goal to pick, where a skill or CLAUDE.md goes, what tasks to write, why a token run needs about 39 pairs, and how to read the result. Each step says what to do on yours.",
            "start": "Start the Repo Tutorial",
            "replay": "Replay the Repo Tutorial"
        },
        "eyebrow": "Repo tutorial · step {step} of 5",
        "leave": "Leave the Tutorial",
        "stepper": "Repo tutorial steps",
        "yours_title": "On Your Repo",
        "steps": [
            {
                "id": "describe",
                "title": "Describe: Pick the Goal, and Say It in Plain Words",
                "lead": "In repo mode the goal is what the coding agent should get better at in your repo. Here it is the one-click goal \"Fewer Tokens at the Same Pass Rate\": the example repo textkit stays as it is, and the agent should spend fewer tokens on it without getting fewer tasks right.",
                "goal_title": "Goal",
                "goal": "Use fewer tokens on each task in this repo, without lowering how many tasks the agent gets right.",
                "template": "Picked from \"Start from one:\" as \"Fewer Tokens at the Same Pass Rate\". Picking it also tells Measure to score the run on Tokens per Solved Task.",
                "repo": "Where it lives: the repo textkit",
                "tasks_line": ".proving-ground/scenarios/ (10 tasks)",
                "yours": [
                    "Pick \"My Repo\" and add your repo (\"Add Your Repo\": its folder on this Mac).",
                    "Under the goal box, click \"Fewer Tokens at the Same Pass Rate\" after \"Start from one:\". It fills the box with: Use fewer tokens on each task in this repo, without lowering how many tasks the agent gets right.",
                    "Add your own words after it if you like (\"in the billing service\", \"on bug fixes\"): the goal keeps its token metric as long as it still starts with the template's text. There is no separate use case or scenario to fill in: the goal is the use case, and the tasks (Measure) are the scenarios.",
                    "Click Save Goal. Until you do, it is a draft in this browser only."
                ],
                "note": "A goal typed from scratch works too, but Measure then starts on the pass rate; pick Tokens there yourself."
            },
            {
                "id": "design",
                "title": "Design: Keep Your Design",
                "lead": "Saving tokens is about the agent, not the app, so there is nothing to redesign: the car stays the same and the part being tested is one skill, lean-context. It tells the agent to read only what the task names, check once and answer in one line.",
                "car": "The Car",
                "car_text": "textkit as it is, with Claude Code as the agent. Nothing in the code changes.",
                "part": "The Part Being Tested",
                "part_text": "The skill lean-context, in .claude/skills/lean-context/. The \"with\" arm has it; the \"without\" arm never sees it.",
                "yours": [
                    "Click \"Keep <your repo>'s Design\". A goal about tokens is about the agent, so that card is marked Recommended.",
                    "Leave \"Start from a Blueprint Instead\" folded: blueprints are for what the app does, and they change the code.",
                    "The part you test is a skill, a CLAUDE.md, a hook or an MCP server: something the agent reads or runs. This example uses a skill; a CLAUDE.md with the same rules is the other natural choice (it is loaded on every turn, with no skill to open)."
                ],
                "note": "An agent you accepted on Design (a ranked architecture) is a blueprint: it changes the app, so it goes in the build brief rather than in a with-and-without run."
            },
            {
                "id": "build",
                "title": "Build: Put the Skill on the Canvas, and Read the Badges",
                "lead": "Build shows your repo's agent setup as a canvas. The skill lean-context goes in its Skills block and is marked Measurable: Measure can run the tasks with it and without it. Everything else on the canvas says, in one badge, whether Measure can test it.",
                "places_title": "Where Things Go, and What Their Badges Mean",
                "places": [
                    {
                        "what": "A new skill (like lean-context)",
                        "where": "Agent setup · Skills. Drag it from the Library, or its + button.",
                        "badge": "Measurable",
                        "tone": "positive"
                    },
                    {
                        "what": "Your CLAUDE.md, hooks and MCP servers as they are",
                        "where": "Agent setup · CLAUDE.md, Hooks, MCP servers",
                        "badge": "In Every Run",
                        "tone": "neutral"
                    },
                    {
                        "what": "A CLAUDE.md, hook or MCP server you add or edit",
                        "where": "The same blocks; picked as the change on Measure",
                        "badge": "Measurable",
                        "tone": "positive"
                    },
                    {
                        "what": "A suggestion you accepted that adds a skill or a task",
                        "where": "Canvas · With Accepted",
                        "badge": "Measurable / Adds a Task",
                        "tone": "positive"
                    },
                    {
                        "what": "A suggestion you accepted that splits, merges or moves code",
                        "where": "Canvas · With Accepted",
                        "badge": "Changes the Code",
                        "tone": "warning"
                    },
                    {
                        "what": "A skill suggested from GitHub, not installed yet",
                        "where": "Library · Picked for This Repo",
                        "badge": "Not Installed",
                        "tone": "warning"
                    }
                ],
                "skill_title": "The Skill, as It Goes in the Repo",
                "yours": [
                    "Open Library and drag your token-saving skill onto the canvas (or click its +). It lands in Agent setup · Skills with the badge Measurable.",
                    "Your existing CLAUDE.md, hooks and MCP servers say In Every Run: both arms start with them, so they aren't what is being measured. To measure a change to your CLAUDE.md, edit it (don't commit) or add a new one, then pick it as the change on Measure.",
                    "Switch the canvas to \"With Accepted\" to see the suggestions you accepted. Only the ones marked Measurable or Adds a Task can go in this run; Changes the Code and Brief Only go in the build brief on Ship."
                ],
                "note": "A hook or an MCP server that saves tokens (one that trims tool output, say) is measured exactly the same way: it is the change, the rest is the same."
            },
            {
                "id": "measure",
                "title": "Measure: Tasks with Checks, Then a Run Scored on Tokens",
                "lead": "Each task ran 4 times with the skill and 4 times without, each in its own Docker sandbox: 40 pairs. Scored on Tokens per Solved Task, a saving only counts once the pass rate is shown to be at most 10 pts worse, and that takes about 39 pairs.",
                "tasks_heading": "First, the Tasks",
                "tasks_lead": "Tokens per solved task only counts tasks that pass, so every task needs a check: a command that exits 0 when the job is done right. Each of these 10 tasks asks for one small helper in a named file, and its check runs the tests and calls the new function.",
                "tasks_title": "Tasks",
                "check_title": "One Task's Check",
                "tasks_yours": [
                    "Under \"Tasks to Measure On\": \"+ Add Task\" for one you write, or \"Generate tasks from the repo and docs\" to have Rig draft them from your code.",
                    "Write the jobs you hand the agent every day: fix this bug, add this endpoint, rename this field. A token saving on tasks you never give it saves nothing.",
                    "A real check runs your own tests, then asserts the new behaviour, like the one shown here. On your repo: `pytest tests/test_invoice.py -q`, `npm test -- billing`, `go test ./billing/...`, followed by a line that calls the new code and compares its answer.",
                    "Click \"Approve Check\" on each one. A check that already passes on the untouched repo measures nothing: Rig runs it first and says so.",
                    "Keep them small and sure: a task the agent fails at random makes the pass-rate guard hard to clear."
                ],
                "run_heading": "Then, the Run",
                "task": "Task",
                "without": "Without",
                "with": "With",
                "passed": "passed",
                "tokens": "tokens",
                "per_trial": "median tokens per trial",
                "tokens_note": "Tokens: the median per trial, in + out as the agent reported them. The score counts them per solved task, over all the pairs.",
                "total": "Passed",
                "metric_title": "Tokens per Solved Task",
                "guard_title": "The Guard: The Pass Rate",
                "score_title": "The Rig Score",
                "yours": [
                    "\"Change to measure\": pick your skill (or the CLAUDE.md, hook or MCP server you edited).",
                    "\"Run on\": your signed-in agent, or a local model you added under Local Models (free: no budget to set, and the skill nudge starts on). This run was on one.",
                    "\"Score the run on\": Tokens. A goal from the template has picked it already (\"Picked from your goal.\").",
                    "Size: Full. A pilot is a few pairs, far short of the about 39 the guard needs, so it can never credit a saving. With 10 tasks, about 4 runs of each.",
                    "\"Tell the agent to open the skill in the prompt\": off is real use (the agent has to find the skill); on makes sure it reads it, at the price of a turn spent opening it. This run had it on, as a small model never opens a skill it is only offered.",
                    "Review the Run: on your agent it shows the price and how many pairs the budget buys before anything starts; on a local model it says the run is free."
                ],
                "note": "Tokens are in + out as the agent reports them, cached input included: every turn sends the whole conversation again, so fewer turns is most of a saving."
            },
            {
                "id": "ship",
                "title": "Ship: Read the Result, Then Keep Only What Earned It",
                "lead": "The skill scored 17 out of 100: Not Proven — more pairs would settle the cut (40 so far). The verdict: Can't Tell Yet. Tokens per Solved Task: with 70.9k vs without 68.4k (+4%, 95% interval -17% to +27%): the cut isn't settled.",
                "result_title": "What It Rests On",
                "without_arm": "Without the skill",
                "with_arm": "With the skill",
                "brief_title": "The Build Brief, for This Example",
                "yours": [
                    "Read the verdict line first, then the guard: a cut in tokens with the guard \"past the margin\" is not a saving yet, it's \"Can't Tell Yet\". Run more pairs, or make the tasks surer.",
                    "\"Which design\": As It Is, or With the Accepted Suggestions. Pick the second only if you accepted any on Build.",
                    "\"Save to the Repo\" writes BUILD.md (the brief, with the evidence beside each change) and rig.json (the same as data). Hand BUILD.md to any coding agent.",
                    "A change that didn't earn its place stays out of the brief. A \"Not Proven\" is an answer too: it says what would settle it."
                ],
                "note": "Next: run more pairs (40 so far).",
                "brief": [
                    "Leave the skill lean-context out: it hasn't earned its place.",
                    "Measured on 40 pairs with Qwen3.5 9B (Q4_0): 70.9k tokens per solved task with it, 68.4k without (+4%); 40 of 40 passed with it, 37 of 40 without.",
                    "Rig score 17/100: Not Proven — more pairs would settle the cut (40 so far).",
                    "To try again: change the skill (or put its rules in CLAUDE.md, which costs no turn to open) and measure that."
                ]
            }
        ],
        "finish": {
            "eyebrow": "Repo tutorial · Done",
            "title": "Now Do It on Your Repo",
            "lead": "Goal from the template, keep your design, the change on the canvas, tasks with checks, Tokens and Full on Measure, then Ship what earned it.",
            "options": [
                {
                    "id": "repo",
                    "label": "Rig Your Own Repo",
                    "text": "Step 1 in repo mode: add your repo and pick the goal.",
                    "to": "repo"
                },
                {
                    "id": "first",
                    "label": "The First Tutorial",
                    "text": "One skill measured on the pass rate, on a price-tags example.",
                    "to": "first"
                },
                {
                    "id": "home",
                    "label": "Back to Home",
                    "text": "The start page, with your runs.",
                    "to": "home"
                }
            ]
        },
        "stale": "The example changed after this run was recorded, so these numbers are from the earlier version.",
        "not_recorded": "No run has been recorded for this example yet, so there are no numbers to show. Record one with `python -m proving_ground.tutorial.record --track tokens` on a local model.",
        "recorded_note": "Recorded on 2026-10-28 with Qwen3.5 9B (Q4_0), in 2 h 3 min. This page only reads that record; it runs nothing.",
        "settings_title": "How It Was Run",
        "settings": [
            "Model: Qwen3.5-9B-Q4_0.gguf, served by llama.cpp 0.7.0 (build 11669): -c 65536 --jinja, Qwen 3.5's own chat template with its system-message check turned into a system turn; thinking on (Claude Code asks for it)",
            "Agent: Claude Code in a Docker sandbox, pointed at the local server; the \"with\" arm told to open the skill",
            "Run through the same engine as a repo run, scored on Tokens per Solved Task (prepare_experiment with the run's metric set to tokens). In the app, pick a local model in Measure's \"Run on\" to run yours the same way, for free.",
            "Time limit: 3× each task's own, as for any local model"
        ]
    },
    "example": {
        "name": "textkit",
        "files": [
            {
                "path": "README.md",
                "text": "# textkit\n\nSmall helpers for cleaning and reshaping text, in plain Python with no dependencies.\n\n- `textkit/case.py`: changing the case of words\n- `textkit/clean.py`: removing what you don't want from text\n- `textkit/count.py`: counting things in text\n\nRun the tests with `python3 -m unittest`. The design notes are in `docs/DESIGN.md`.\n"
            },
            {
                "path": "textkit/case.py",
                "text": "\"\"\"Changing the case of words.\"\"\"\n\n\ndef title(text: str) -> str:\n    \"\"\"Each word starts with a capital: title(\"hello world\") == \"Hello World\".\"\"\"\n    return \" \".join(w[:1].upper() + w[1:].lower() for w in text.split())\n\n\ndef camel(text: str) -> str:\n    \"\"\"Words joined, each after the first capitalised: camel(\"hello big world\") == \"helloBigWorld\".\"\"\"\n    words = text.split()\n    if not words:\n        return \"\"\n    return words[0].lower() + \"\".join(w[:1].upper() + w[1:].lower() for w in words[1:])\n"
            },
            {
                "path": "docs/DESIGN.md",
                "text": "# textkit design notes\n\n## Why it exists\n\ntextkit started as a handful of string helpers copied between scripts. Gathering them in one\npackage means each is written once, tested once and named the same way everywhere.\n\n## Layout\n\nOne module per kind of job: `case.py` changes the case of words, `clean.py` removes what you\ndon't want, `count.py` counts things. A helper goes in the module whose job it does; a new kind\nof job gets a new module. Nothing in one module imports another.\n\n## Conventions\n\n- Every helper takes the text as its first argument and returns a new value; nothing is changed\n  in place, and nothing prints.\n- Words are split on whitespace (`str.split()` with no argument), so runs of spaces, tabs and\n  newlines all count as one break.\n- Empty text gives an empty result (`\"\"`, `0` or `[]`), never an error.\n- Only the standard library. No regular expressions where a plain loop or a string method reads\n  as well.\n- Each helper has a one-line docstring with an example that is also true as code.\n\n## Tests\n\n`tests/test_textkit.py` holds one test per helper. Run them all with `python3 -m unittest` from\nthe project root. They take well under a second.\n\n## Not in scope\n\nNatural-language work (stemming, spelling, languages other than English) and anything that\nneeds a dependency. Those belong in a bigger library.\n"
            }
        ],
        "skill": {
            "name": "lean-context",
            "description": "How to work on a small token budget: read only the file the task names, change it in one edit, check once, and answer in one line. Use it for every task.",
            "path": ".claude/skills/lean-context/SKILL.md",
            "text": "---\nname: lean-context\ndescription: \"How to work on a small token budget: read only the file the task names, change it in one edit, check once, and answer in one line. Use it for every task.\"\n---\n\n# Lean context\n\nEverything you read or write stays in the conversation and is sent again on every later turn,\nso each extra file and each extra turn is paid for many times over. Do the task with as little\nas you can.\n\n## Rules\n\n- **Read only what the task names.** The task says which file to change: open that file and\n  nothing else. Don't list folders, search the repo, or open the README, the docs or other\n  modules to get your bearings.\n- **One edit.** Write the change in a single edit to that file. Don't rewrite code the task\n  didn't ask about.\n- **Check once.** Run `python3 -m unittest -q` from the project root once, after the edit. If\n  it fails, fix only what it reports and run it again.\n- **Nothing extra.** No new tests, comments, docs or files unless the task asks for them.\n- **Answer in one line.** When it's done, say what you changed in one sentence. No plan before,\n  no summary after.\n",
            "body": "# Lean context\n\nEverything you read or write stays in the conversation and is sent again on every later turn,\nso each extra file and each extra turn is paid for many times over. Do the task with as little\nas you can.\n\n## Rules\n\n- **Read only what the task names.** The task says which file to change: open that file and\n  nothing else. Don't list folders, search the repo, or open the README, the docs or other\n  modules to get your bearings.\n- **One edit.** Write the change in a single edit to that file. Don't rewrite code the task\n  didn't ask about.\n- **Check once.** Run `python3 -m unittest -q` from the project root once, after the edit. If\n  it fails, fix only what it reports and run it again.\n- **Nothing extra.** No new tests, comments, docs or files unless the task asks for them.\n- **Answer in one line.** When it's done, say what you changed in one sentence. No plan before,\n  no summary after."
        },
        "tasks": [
            {
                "id": "char-count",
                "title": "Character count",
                "kind": "typical",
                "instruction": "Add `char_count(text)` to textkit/count.py: how many characters the text has that aren't whitespace, as an int.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.count import char_count\ngot = char_count(\"a b  c\")\nassert got == 3, f'char_count(\"a b  c\") gave {got!r}'\ngot = char_count(\" hi\\n\")\nassert got == 2, f'char_count(\" hi\\n\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "initials",
                "title": "Initials",
                "kind": "typical",
                "instruction": "Add `initials(name)` to textkit/case.py: the first letter of each word, in capitals, with nothing between them, such as `AL` for \"ada lovelace\".",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.case import initials\ngot = initials(\"ada lovelace\")\nassert got == 'AL', f'initials(\"ada lovelace\") gave {got!r}'\ngot = initials(\"grace brewster hopper\")\nassert got == 'GBH', f'initials(\"grace brewster hopper\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "kebab",
                "title": "Kebab case",
                "kind": "typical",
                "instruction": "Add `kebab(text)` to textkit/case.py: the words of the text in lowercase, joined by hyphens, such as `hello-big-world` for \"Hello Big World\".",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.case import kebab\ngot = kebab(\"Hello Big World\")\nassert got == 'hello-big-world', f'kebab(\"Hello Big World\") gave {got!r}'\ngot = kebab(\"A\")\nassert got == 'a', f'kebab(\"A\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "line-count",
                "title": "Line count",
                "kind": "typical",
                "instruction": "Add `line_count(text)` to textkit/count.py: how many lines the text has, as an int: 0 for empty text, and a final newline doesn't start a new line.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.count import line_count\ngot = line_count(\"a\\nb\\nc\")\nassert got == 3, f'line_count(\"a\\nb\\nc\") gave {got!r}'\ngot = line_count(\"a\\nb\\n\")\nassert got == 2, f'line_count(\"a\\nb\\n\") gave {got!r}'\ngot = line_count(\"\")\nassert got == 0, f'line_count(\"\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "only-ascii",
                "title": "Only ASCII",
                "kind": "typical",
                "instruction": "Add `only_ascii(text)` to textkit/clean.py: the text with every character that isn't ASCII removed.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.clean import only_ascii\ngot = only_ascii(\"café olé\")\nassert got == 'caf ol', f'only_ascii(\"café olé\") gave {got!r}'\ngot = only_ascii(\"plain\")\nassert got == 'plain', f'only_ascii(\"plain\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "snake",
                "title": "Snake case",
                "kind": "typical",
                "instruction": "Add `snake(text)` to textkit/case.py: the words of the text in lowercase, joined by underscores, such as `hello_big_world` for \"Hello Big World\".",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.case import snake\ngot = snake(\"Hello Big World\")\nassert got == 'hello_big_world', f'snake(\"Hello Big World\") gave {got!r}'\ngot = snake(\"  one  \")\nassert got == 'one', f'snake(\"  one  \") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "squeeze",
                "title": "Squeeze spaces",
                "kind": "typical",
                "instruction": "Add `squeeze(text)` to textkit/clean.py: the text with each run of whitespace turned into one space and none at either end.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.clean import squeeze\ngot = squeeze(\"  a   b\\t\\tc  \")\nassert got == 'a b c', f'squeeze(\"  a   b\\t\\tc  \") gave {got!r}'\ngot = squeeze(\"one\")\nassert got == 'one', f'squeeze(\"one\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "strip-digits",
                "title": "Strip digits",
                "kind": "typical",
                "instruction": "Add `strip_digits(text)` to textkit/clean.py: the text with every digit 0 to 9 removed.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.clean import strip_digits\ngot = strip_digits(\"r2d2 c3po\")\nassert got == 'rd cpo', f'strip_digits(\"r2d2 c3po\") gave {got!r}'\ngot = strip_digits(\"abc\")\nassert got == 'abc', f'strip_digits(\"abc\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "swap",
                "title": "Swap case",
                "kind": "typical",
                "instruction": "Add `swap(text)` to textkit/case.py: the text with every lowercase letter made uppercase and every uppercase letter made lowercase.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.case import swap\ngot = swap(\"Hello World\")\nassert got == 'hELLO wORLD', f'swap(\"Hello World\") gave {got!r}'\ngot = swap(\"abc\")\nassert got == 'ABC', f'swap(\"abc\") gave {got!r}'\nprint('ok')\nPY\n"
            },
            {
                "id": "vowel-count",
                "title": "Vowel count",
                "kind": "typical",
                "instruction": "Add `vowel_count(text)` to textkit/count.py: how many vowels (a, e, i, o, u, in either case) the text has, as an int.",
                "check": "python3 -m unittest -q && python3 - <<'PY'\nfrom textkit.count import vowel_count\ngot = vowel_count(\"Hello World\")\nassert got == 3, f'vowel_count(\"Hello World\") gave {got!r}'\ngot = vowel_count(\"AEIOU xyz\")\nassert got == 5, f'vowel_count(\"AEIOU xyz\") gave {got!r}'\nprint('ok')\nPY\n"
            }
        ]
    },
    "run": {
        "recorded": "2026-10-28",
        "model": {
            "file": "Qwen3.5-9B-Q4_0.gguf",
            "id": "qwen3.5-9b",
            "server": "llama.cpp 0.7.0 (build 11669): -c 65536 --jinja, Qwen 3.5's own chat template with its system-message check turned into a system turn; thinking on (Claude Code asks for it)",
            "agent": "claude-code",
            "nudge": true,
            "timeout_factor": 3,
            "label": "Qwen3.5 9B (Q4_0)"
        },
        "skill": "lean-context",
        "repeats": 4,
        "took_s": 7371,
        "tasks": [
            {
                "id": "char-count",
                "title": "Character count",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        98.4,
                        74.7,
                        95.4,
                        102.6
                    ],
                    "tokens": [
                        58347,
                        59321,
                        58655,
                        173923
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 3,
                    "trials": 4,
                    "outcomes": [
                        "fail",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        78.6,
                        105.8,
                        50.7,
                        116.9
                    ],
                    "tokens": [
                        57740,
                        57866,
                        34170,
                        94537
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            },
            {
                "id": "initials",
                "title": "Initials",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        139.1,
                        76.9,
                        113.1,
                        98.4
                    ],
                    "tokens": [
                        59478,
                        72175,
                        72354,
                        136203
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        78.5,
                        99.9,
                        62.5,
                        105.7
                    ],
                    "tokens": [
                        58898,
                        34634,
                        46708,
                        82622
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            },
            {
                "id": "kebab",
                "title": "Kebab case",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        123.1,
                        68.4,
                        101.8,
                        65.3
                    ],
                    "tokens": [
                        71623,
                        59407,
                        59407,
                        59409
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        66.3,
                        118.7,
                        68.2,
                        98.8
                    ],
                    "tokens": [
                        46787,
                        70963,
                        59206,
                        58489
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            },
            {
                "id": "line-count",
                "title": "Line count",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        144.2,
                        136.3,
                        100.3,
                        59.6
                    ],
                    "tokens": [
                        60738,
                        176380,
                        58995,
                        58918
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 3,
                    "trials": 4,
                    "outcomes": [
                        "fail",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        106.4,
                        126.9,
                        110.2,
                        118.7
                    ],
                    "tokens": [
                        96306,
                        83841,
                        98378,
                        71233
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            },
            {
                "id": "only-ascii",
                "title": "Only ASCII",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        114.9,
                        66.4,
                        96.6,
                        63.0
                    ],
                    "tokens": [
                        59020,
                        59007,
                        58781,
                        58918
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        54.7,
                        102.3,
                        50.9,
                        85.6
                    ],
                    "tokens": [
                        34181,
                        57794,
                        34267,
                        34191
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            },
            {
                "id": "snake",
                "title": "Snake case",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        130.8,
                        68.6,
                        97.1,
                        61.7
                    ],
                    "tokens": [
                        97067,
                        59412,
                        59070,
                        59156
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        80.1,
                        131.0,
                        53.1,
                        96.8
                    ],
                    "tokens": [
                        71221,
                        120935,
                        34538,
                        58423
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            },
            {
                "id": "squeeze",
                "title": "Squeeze spaces",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        106.0,
                        73.9,
                        93.8,
                        62.6
                    ],
                    "tokens": [
                        58849,
                        59210,
                        58623,
                        59000
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 3,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "fail"
                    ],
                    "seconds": [
                        59.8,
                        186.4,
                        81.1,
                        96.2
                    ],
                    "tokens": [
                        46168,
                        204732,
                        95146,
                        46183
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            },
            {
                "id": "strip-digits",
                "title": "Strip digits",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        99.8,
                        56.0,
                        93.9,
                        64.4
                    ],
                    "tokens": [
                        58863,
                        58454,
                        58470,
                        70906
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        49.4,
                        103.1,
                        57.7,
                        89.4
                    ],
                    "tokens": [
                        34174,
                        69961,
                        57716,
                        45958
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            },
            {
                "id": "swap",
                "title": "Swap case",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        110.9,
                        62.6,
                        99.5,
                        68.7
                    ],
                    "tokens": [
                        71562,
                        59166,
                        59237,
                        59537
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        84.2,
                        91.9,
                        54.2,
                        128.1
                    ],
                    "tokens": [
                        59734,
                        34598,
                        34520,
                        97098
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            },
            {
                "id": "vowel-count",
                "title": "Vowel count",
                "with": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        99.9,
                        65.8,
                        98.8,
                        86.7
                    ],
                    "tokens": [
                        58489,
                        59168,
                        58878,
                        120019
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                },
                "without": {
                    "passed": 4,
                    "trials": 4,
                    "outcomes": [
                        "pass",
                        "pass",
                        "pass",
                        "pass"
                    ],
                    "seconds": [
                        67.4,
                        94.0,
                        55.2,
                        94.4
                    ],
                    "tokens": [
                        58005,
                        45999,
                        46011,
                        58016
                    ],
                    "details": [
                        "",
                        "",
                        "",
                        ""
                    ]
                }
            }
        ],
        "n": 40,
        "with": 40,
        "without": 37,
        "diff": 0.07499999999999996,
        "ci_low": -0.02547209243373645,
        "ci_high": 0.19864233524310537,
        "verdict": "inconclusive",
        "ledger": {
            "total": 80,
            "with": 40,
            "without": 40,
            "pairs": 40,
            "logs_read": 40,
            "clean": 80,
            "timed_out": 0,
            "errored": 0,
            "broken": 0
        },
        "metric": {
            "id": "tokens",
            "name": "Tokens per Solved Task",
            "n": 40,
            "margin_pts": 10,
            "guard": "Pass rate: 40 of 40 passed with vs 37 of 40 passed without (+7 pts; at worst -3 pts, within the 10-pt margin)",
            "noninferior": true,
            "with": 70854.875,
            "without": 68431.0,
            "ratio": 1.0354207157574784,
            "low": 0.8328790611302388,
            "high": 1.265250678289281,
            "headline": "Tokens per Solved Task: with 70.9k vs without 68.4k (+4%, 95% interval -17% to +27%)"
        },
        "rig": {
            "score": 17,
            "band": "not_proven",
            "tone": "warning",
            "label": "Not Proven — more pairs would settle the cut (40 so far)",
            "reason": "No cut in tokens per solved task shown",
            "provisional": false,
            "pairs": 40,
            "parts": [
                {
                    "id": "lift",
                    "name": "Lift",
                    "weight": 0.6,
                    "score": 0.0,
                    "detail": "no cut in tokens per solved task shown (the interval reaches +27%)",
                    "counted": true,
                    "weight_used": 0.7059
                },
                {
                    "id": "cost",
                    "name": "Cost",
                    "weight": 0.0,
                    "score": null,
                    "detail": "in Lift: Tokens per solved task is what is measured",
                    "folded": true,
                    "counted": false,
                    "weight_used": 0.0
                },
                {
                    "id": "followed",
                    "name": "Followed",
                    "weight": 0.15,
                    "score": 95.0,
                    "detail": "opened the skill in 38 of the 40 \"with\" trials whose logs could be read",
                    "counted": true,
                    "weight_used": 0.1765
                },
                {
                    "id": "holds_up",
                    "name": "Holds Up",
                    "weight": 0.15,
                    "score": null,
                    "detail": "This bench has no held-out tasks, so it's unknown whether this holds on unseen tasks",
                    "counted": false,
                    "weight_used": 0.0
                },
                {
                    "id": "reliable",
                    "name": "Reliable",
                    "weight": 0.1,
                    "score": 100.0,
                    "detail": "80 of 80 trials ran cleanly (40 with, 40 without)",
                    "counted": false,
                    "note": "counts once a cut is shown and the pass rate holds",
                    "weight_used": 0.1176
                }
            ],
            "gates": [
                {
                    "id": "not_cut",
                    "cap": 49,
                    "text": "Capped at 49: no cut in tokens per solved task shown (the interval reaches 0).",
                    "binding": false
                }
            ],
            "formula": {
                "text": "60% × 0 (Lift takes Cost's 20%: the measure is tokens) + 15% × 95 + 10% × 0 (Reliable: no credit yet) = 14.2; ÷ 85% (weights rescaled to the measured parts; holds up not measured) = 16.8; rounded: 17",
                "measured_weight": 0.85,
                "raw": 16.76,
                "not_measured": [
                    "holds up"
                ]
            },
            "ledger": {
                "total": 80,
                "with": 40,
                "without": 40,
                "pairs": 40,
                "logs_read": 40,
                "clean": 80,
                "timed_out": 0,
                "errored": 0,
                "broken": 0
            },
            "ledger_text": "80 trials (40 with, 40 without) · 40 complete pairs · 80 ran cleanly · logs read for 40 of the 40 \"with\" trials",
            "verdict": {
                "id": "cant",
                "word": "Can't Tell Yet",
                "tone": "neutral",
                "reason": "Tokens per Solved Task: with 70.9k vs without 68.4k (+4%, 95% interval -17% to +27%): the cut isn't settled.",
                "next": "Next: run more pairs (40 so far).",
                "facts": [
                    "Quality: 40 of 40 passed with, 37 of 40 passed without (+7 pts, 95% interval -3 to +20)",
                    "Cost: nothing (a local model)",
                    "Time: 1.5 min vs 89 s per trial (1.0×)",
                    "Reliability: with, all 40 ran cleanly; without, all 40 ran cleanly"
                ]
            },
            "quality": "pass_rate",
            "metric": {
                "id": "tokens",
                "name": "Tokens per Solved Task",
                "n": 40,
                "margin_pts": 10,
                "guard": "Pass rate: 40 of 40 passed with vs 37 of 40 passed without (+7 pts; at worst -3 pts, within the 10-pt margin)",
                "noninferior": true,
                "with": 70854.875,
                "without": 68431.0,
                "ratio": 1.0354207157574784,
                "low": 0.8328790611302388,
                "high": 1.265250678289281,
                "headline": "Tokens per Solved Task: with 70.9k vs without 68.4k (+4%, 95% interval -17% to +27%)"
            }
        },
        "stale": false
    }
} as unknown as TokensTutorial;
