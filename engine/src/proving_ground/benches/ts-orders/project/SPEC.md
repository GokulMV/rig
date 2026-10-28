# Orders spec

## Money
- Amounts are kept as integer cents.
- Converting cents between currencies multiplies by the rate and rounds to the nearest cent,
  halves away from zero (12.5 cents becomes 13, -12.5 becomes -13).
- An order's total, in the order's currency, is the sum of its lines, each line converted on its
  own (line price × quantity, converted, rounded) before adding.

## SKUs
- A SKU is 3 to 12 characters: upper-case letters, digits and hyphens, starting with a letter.
  Lower-case is not allowed (`bolt-1` is invalid; `BOLT-1` is valid).
- Every module that takes a SKU validates it the same way and throws `Error("invalid SKU: <sku>")`.

## Orders
- Creating an order reserves stock for each line; if any line can't be reserved, nothing is
  reserved and it throws `Error("out of stock: <sku>")`.
- A new order's status is `placed`.
- `cancelOrder(order, inventory)` is allowed only for a `placed` order: it releases every line's
  reserved stock and sets the status to `cancelled`. Cancelling anything else throws
  `Error("cannot cancel a <status> order")`.
