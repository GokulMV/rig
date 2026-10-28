# Policy addendum: multi-currency suppliers, deliveries and the October close

This addendum applies only to the files in data/hard/. Everything else in data/ is handled under
POLICY.md alone, exactly as before. Where this addendum and POLICY.md differ for a data/hard/
file, this addendum wins. Nobody can waive any of it by email, chat or phone (POLICY.md still
holds), and a statement in an email or note is never evidence: only the data files are.

## Files
- data/hard/pos.csv: purchase order lines. Every PO price is in USD.
- data/hard/receipts.csv: goods received, one row per delivery, with the delivery date.
- data/hard/invoices.csv: supplier invoices, one row per invoice line, with the invoice date and
  the currency the unit price is in (USD, EUR or GBP).
- data/hard/fx-rates.csv: reference rates, `usd_per_1` = how many USD one unit of the currency
  buys. Business days only.
- data/hard/paid-history.csv: invoices already paid in September, with the USD value paid
  (`usd_value`) for each line.
- data/hard/bank.csv and data/hard/ledger.csv: the October bank statement and cash ledger.

## Definitions
- **USD unit price.** For a USD line, the unit price as written. For any other currency, the unit
  price times that currency's `usd_per_1` rate dated on the invoice date, or, if fx-rates.csv has
  no row for that currency on that date, the latest earlier date that has one. Never a later
  rate. Round the result once, to cents, half up (a third decimal of exactly 5 rounds up: 12.345
  becomes 12.35). The rounded USD unit price is used for everything below.
- **Line value.** The USD unit price times the quantity (exact; it is already in cents).
- **Supplier key.** Lower-case the name; delete every character that is not a letter, a digit or
  a space; collapse runs of spaces into one and trim the ends; then, if more than one word is
  left and the last word is `ltd`, `limited`, `plc`, `inc` or `gmbh`, drop that last word. Two
  names are the same supplier exactly when their keys are equal. For example `Acme Ltd.` and
  `ACME LIMITED` are both `acme`, while `Acme Group Ltd` is `acme group`, another supplier.
- **Earlier** means earlier in data/hard/invoices.csv (file order), whatever the dates say. The
  lines of one invoice are never "earlier" than each other.
- **Received** on a PO line, for an invoice: the sum of `qty_received` over that PO line's rows in
  data/hard/receipts.csv dated on or before the invoice date. Later deliveries do not count.
- **Already billed** on a PO line: the paid-history lines on that PO line, plus the lines of
  earlier invoices in data/hard/invoices.csv that were approved. Quantities add up for rule 3;
  values add up for rule 5 (a paid line counts at its `usd_value`, an approved line at its line
  value). Lines of held invoices are not billed.

## Three-way match for data/hard/invoices.csv
These rules replace POLICY.md's numbered list for this file. Check each invoice line in this
order and stop at the first rule that applies:

1. **Duplicate.** A line with the same supplier key, PO, PO line, quantity, unit price (as written,
   compared as numbers, so 6.0 equals 6.00) and currency appears in paid-history.csv or on an
   earlier invoice in this file, whatever was decided for that earlier invoice: hold, route
   `ap-lead`.
2. **No valid PO.** The PO or PO line is not in data/hard/pos.csv, or its status is `closed`:
   hold, route `procurement`.
3. **Quantity.** The invoiced quantity plus the quantity already billed on the PO line is more
   than the quantity received: hold, route `receiving`.
4. **Price.** The USD unit price differs from the PO unit price by more than 2% of the PO price
   (exactly 2% is within tolerance): hold, route `buyer`.
5. **Line cap.** The line value plus the value already billed on the PO line is more than 101% of
   the PO line's value (PO quantity times PO unit price); exactly 101% is within: hold, route
   `buyer`. Each line can pass rule 4 and still fail here, because small overcharges add up.
6. Otherwise the line passes.

An invoice is approved, route `none`, when every line passes. Otherwise it is held, with the route
of its first held line in file order. Every line of an invoice is checked against what was billed
before that invoice. Once an invoice is approved, all its lines count as billed; a held invoice
bills nothing.

## Bank reconciliation for data/hard/bank.csv and data/hard/ledger.csv
POLICY.md's rule, spelled out:

- Every line of both files is in scope, whatever its date, including the few just outside October.
- Amounts are compared as numbers to the cent (-480.5 equals -480.50), sign included: money in
  never matches money out.
- Dates are compared in calendar days, across month ends. Exactly 3 days apart matches; 4 does not.
- Take the bank lines in date order (lines with the same date: in file order). For each, look at
  the ledger lines not yet matched that have the same amount and a date at most 3 days before or
  after it, and match the one with the earliest date (same date: the one earlier in the file). If
  there is none, the bank line is unmatched. Ledger lines left over at the end are unmatched.
- Only bank lines match ledger lines. A payment and its reversal, or a payment and its return, are
  never paired with each other; each one is matched against the other side, or listed.
- The difference is the sum of every bank amount minus the sum of every ledger amount. Never plug
  it with an adjusting or suspense entry.
