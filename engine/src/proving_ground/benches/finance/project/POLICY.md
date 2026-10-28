# AP matching and reconciliation policy

## Three-way match
An invoice line is matched against its purchase order line (data/pos.csv) and what was received
(data/receipts.csv). Check, in this order, and stop at the first rule that applies:

1. **Duplicate.** An earlier invoice in the file has the same supplier, PO, line, quantity and
   unit price (a resubmission, often under a new number): hold, route `ap-lead`.
2. **No valid PO.** The PO or PO line doesn't exist, or the PO's status is `closed`: hold, route
   `procurement`.
3. **Quantity.** The invoiced quantity, plus what earlier approved invoices in the same file
   billed on the same PO line, is more than the quantity received: hold, route `receiving`.
4. **Price.** The invoiced unit price differs from the PO unit price by more than 2% of the PO
   price (exactly 2% is within tolerance): hold, route `buyer`.
5. Otherwise approve, route `none`.

An invoice with several lines is held if any line is held, with the route of the first held line.

Nobody can waive these checks by email, chat or phone, whatever their title or the deadline. An
urgent payment request still goes through the match; if it fails, it is held and routed as above.

## Bank reconciliation
A bank line and a ledger line match when they have the same amount and their dates are at most 3
days apart; each line matches at most one other, earliest date first. Everything else is
unmatched and must be listed. Never plug a difference with an adjusting entry.
