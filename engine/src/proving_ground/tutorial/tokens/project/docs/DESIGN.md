# textkit design notes

## Why it exists

textkit started as a handful of string helpers copied between scripts. Gathering them in one
package means each is written once, tested once and named the same way everywhere.

## Layout

One module per kind of job: `case.py` changes the case of words, `clean.py` removes what you
don't want, `count.py` counts things. A helper goes in the module whose job it does; a new kind
of job gets a new module. Nothing in one module imports another.

## Conventions

- Every helper takes the text as its first argument and returns a new value; nothing is changed
  in place, and nothing prints.
- Words are split on whitespace (`str.split()` with no argument), so runs of spaces, tabs and
  newlines all count as one break.
- Empty text gives an empty result (`""`, `0` or `[]`), never an error.
- Only the standard library. No regular expressions where a plain loop or a string method reads
  as well.
- Each helper has a one-line docstring with an example that is also true as code.

## Tests

`tests/test_textkit.py` holds one test per helper. Run them all with `python3 -m unittest` from
the project root. They take well under a second.

## Not in scope

Natural-language work (stemming, spelling, languages other than English) and anything that
needs a dependency. Those belong in a bigger library.
