# orders

`data/orders.csv` is an export with problems. Cleaning rules:

1. Columns out: `order_id,date,customer,amount_cents`.
2. `date` in ISO `YYYY-MM-DD`. The input has `2026-01-05`, `05/01/2026` (day/month/year) and
   `Jan 5 2026`.
3. `customer`: trimmed, each word capitalised (`  ada LOVELACE` → `Ada Lovelace`).
4. `amount_cents`: an integer. The input has `12.50`, `$12.50`, `12,50` (comma decimal) and
   `-3.00` (refunds are negative; keep them).
5. Drop rows with no amount or no customer.
6. Drop exact duplicate `order_id`s, keeping the first.
7. Sort by date, then order_id.
