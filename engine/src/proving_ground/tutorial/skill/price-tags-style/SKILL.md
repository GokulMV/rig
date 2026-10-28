---
name: price-tags-style
description: "The shop's house style for shelf labels in pricetags/tags.py: how prices, units, refunds, discounts, ranges, sales and free items are written. Use it for any change to a label."
---

# Price tag house style

Every label is built from `price(cents)` in `pricetags/tags.py`, which already writes one
price the house way: euro sign first, dot between thousands, comma before the cents
(`price(123456) == "€1.234,56"`). Reuse it; never format a price by hand.

## Rules

- **Per unit:** the price, a space, a slash, a space, the unit: `€2,50 / kg`.
- **Per 100 g** (from a price per kg): divide by 10, round half up to a whole cent, then
  `€1,25 / 100 g`.
- **Refunds:** a minus sign straight before the euro sign: `-€3,00`. Takes the refund as a
  positive number of cents.
- **Discounts:** a minus sign, the whole percent, a percent sign, no spaces: `-15%`.
- **Ranges:** the low price, the word `to`, the high price: `€5,00 to €9,00`.
- **Sales:** the new price, then the old one in brackets after `was`: `€7,99 (was €9,99)`.
- **Free items:** zero cents is the word `free`, lowercase. Any other amount is `price()`.
- **Rounding:** always half up to a whole cent (`282.5` cents is `283`). Never Python's
  `round()`, which rounds halves to even.
- **Tax:** a price with tax added is net × (100 + rate) ÷ 100, rounded half up, then `price()`.

## Check your work

Run `python3 -m unittest` from the project root, and add a test for the new label in
`tests/test_tags.py`.
