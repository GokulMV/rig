import { Inventory } from "./inventory.ts";
import { convert, type Rates } from "./money.ts";

function validateSku(sku: string): void {
  if (!/^[A-Z][A-Z0-9-]{2,11}$/.test(sku)) throw new Error(`invalid SKU: ${sku}`);
}

export interface Line {
  sku: string;
  qty: number;
  priceCents: number;
  currency: string;
}

export interface Order {
  id: string;
  lines: Line[];
  currency: string;
  totalCents: number;
  status: "placed" | "cancelled" | "shipped";
}

let next = 1;

export function createOrder(lines: Line[], currency: string, inv: Inventory, rates: Rates): Order {
  for (const l of lines) validateSku(l.sku);
  const done: Line[] = [];
  try {
    for (const l of lines) {
      inv.reserve(l.sku, l.qty);
      done.push(l);
    }
  } catch (e) {
    for (const l of done) inv.release(l.sku, l.qty);
    throw e;
  }
  const totalCents = lines.reduce((t, l) => t + convert(l.priceCents * l.qty, l.currency, currency, rates), 0);
  return { id: `ORD-${next++}`, lines, currency, totalCents, status: "placed" };
}
