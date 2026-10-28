# Invoicing from the command line

Create an invoice, add lines, check the total, then mark it paid. Data is saved to invoices.json.

```bash
python3 invoice.py new 2026-001 --client "Acme Ltd"
python3 invoice.py add-line 2026-001 "Design sprint" 1200 --qty 2
python3 invoice.py add-line 2026-001 "Hosting" 49.5
python3 invoice.py show 2026-001
python3 invoice.py mark-paid 2026-001
```

`show` prints each line and the total (here 2449.50). `--qty` defaults to 1.
