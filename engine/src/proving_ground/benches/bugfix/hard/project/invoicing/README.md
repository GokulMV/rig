# invoicing

Builds customer invoices and instalment plans. It is its own component, separate from
`shop/`; run its tests from this folder:

    cd invoicing && python3 -m unittest

## Money (money.py)

- Amounts come in as strings in major units (`"19.99"`) and go out as integers in the
  currency's minor unit (cents, fils, yen). `currency` is an ISO 4217 code in capitals.
- Minor units per currency: JPY has 0 decimals (1 yen is 1 minor unit); KWD and BHD have 3
  (1 dinar is 1000 fils); every other currency has 2.
- "Round to minor units" always means to the nearest whole minor unit, half up (a tie goes to
  the larger amount): 2.675 USD is 268, 0.0005 KWD is 1, 0.5 JPY is 1.
- Everything is exact decimal arithmetic until a step says to round. Never go through binary
  floats.

## Invoices: `build_invoice(lines, currency, percent_off="0", amount_off="0")` (invoice.py)

Each line is `(unit_price, qty, tax_rate)`: `unit_price` a string in major units, `qty` an
int of at least 1, `tax_rate` a percent string (`"20"`, `"7.5"`, `"0"`). `percent_off` is a
percent string from `"0"` to `"100"`; `amount_off` is a string in major units, 0 or more.

1. Line amount = unit_price x qty. Subtotal = the sum of the line amounts. (Exact.)
2. Discount = subtotal x percent_off / 100, plus amount_off. The percentage is always taken
   of the full subtotal, never of what is left after amount_off. If the discount is more
   than the subtotal it is capped at the subtotal: an invoice never goes below zero.
3. Net = subtotal - discount, rounded to minor units.
4. Net is shared out over the lines in proportion to their line amounts, so that the line
   nets add up exactly to net. Each line first gets the whole minor units of its exact share
   (net x line amount / subtotal, rounded down). The minor units still left over then go one
   each to the lines with the largest leftover fraction; when two leftover fractions are
   equal, the earlier line gets its unit first. If the subtotal is 0, every line net is 0.
5. Line tax = line net x tax_rate / 100, rounded to a whole minor unit half to even
   (banker's rounding: 2.5 is 2, 3.5 is 4, 2.51 is 3). This is the only step that rounds
   half to even.
6. Tax = the sum of the line taxes. Total = net + tax.

It returns `{"lines": [(line_net, line_tax), ...], "net": ..., "tax": ..., "total": ...}`,
the lines in input order, every amount an integer in minor units.

## Instalments: `schedule(total, currency, n, fee="0")` (instalments.py)

1. `n` must be an int from 1 to 24 inclusive; anything else raises ValueError.
2. The total is rounded to minor units.
3. Each instalment gets total // n minor units. The remaining total mod n minor units go one
   each to the first instalments, so no two instalments differ by more than one minor unit
   and an earlier instalment is never smaller than a later one.
4. The fee is rounded to minor units and added to the first instalment only.

It returns the n instalments as a list of integers in minor units.
