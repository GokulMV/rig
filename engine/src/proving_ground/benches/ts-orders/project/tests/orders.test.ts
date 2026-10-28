import assert from "node:assert/strict";
import { test } from "node:test";

import { createOrder, format, Inventory } from "../src/index.ts";

const rates = { EUR: 1, USD: 0.92, GBP: 1.17 };

test("an order reserves stock", () => {
  const inv = new Inventory();
  inv.add("BOLT-1", 10);
  const o = createOrder([{ sku: "BOLT-1", qty: 3, priceCents: 250, currency: "EUR" }], "EUR", inv, rates);
  assert.equal(o.status, "placed");
  assert.equal(o.totalCents, 750);
  assert.equal(inv.available("BOLT-1"), 7);
});

test("out of stock reserves nothing", () => {
  const inv = new Inventory();
  inv.add("BOLT-1", 10);
  inv.add("NUT-1", 1);
  assert.throws(
    () =>
      createOrder(
        [
          { sku: "BOLT-1", qty: 3, priceCents: 250, currency: "EUR" },
          { sku: "NUT-1", qty: 2, priceCents: 10, currency: "EUR" },
        ],
        "EUR",
        inv,
        rates,
      ),
    /out of stock: NUT-1/,
  );
  assert.equal(inv.available("BOLT-1"), 10);
});

test("format", () => {
  assert.equal(format(123456, "EUR"), "1234.56 EUR");
  assert.equal(format(-5, "USD"), "-0.05 USD");
});
