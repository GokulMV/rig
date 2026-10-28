import assert from "node:assert/strict";
import { test } from "node:test";

import { convert, createOrder, Inventory } from "../src/index.ts";

const rates = { EUR: 1, USD: 0.92, GBP: 1.17 };

test("rounds to the nearest cent, halves away from zero", () => {
  assert.equal(convert(250, "GBP", "EUR", rates), 293); // 292.5
  assert.equal(convert(-250, "GBP", "EUR", rates), -293);
  assert.equal(convert(1000, "EUR", "USD", rates), 1087); // 1086.96
  assert.equal(convert(1000, "EUR", "EUR", rates), 1000);
});

test("each line converted on its own before adding", () => {
  const inv = new Inventory();
  inv.add("TEA-1", 5);
  inv.add("CUP-1", 5);
  const o = createOrder(
    [
      { sku: "TEA-1", qty: 1, priceCents: 250, currency: "GBP" },
      { sku: "CUP-1", qty: 1, priceCents: 250, currency: "GBP" },
    ],
    "EUR",
    inv,
    rates,
  );
  assert.equal(o.totalCents, 586);
});
