import assert from "node:assert/strict";
import { test } from "node:test";

import { cancelOrder, createOrder, Inventory } from "../src/index.ts";

const rates = { EUR: 1 };

function placed() {
  const inv = new Inventory();
  inv.add("BOLT-1", 10);
  inv.add("NUT-1", 10);
  const o = createOrder(
    [
      { sku: "BOLT-1", qty: 3, priceCents: 100, currency: "EUR" },
      { sku: "NUT-1", qty: 4, priceCents: 10, currency: "EUR" },
    ],
    "EUR",
    inv,
    rates,
  );
  return { inv, o };
}

test("cancelling a placed order releases its stock", () => {
  const { inv, o } = placed();
  cancelOrder(o, inv);
  assert.equal(o.status, "cancelled");
  assert.equal(inv.available("BOLT-1"), 10);
  assert.equal(inv.available("NUT-1"), 10);
});

test("only a placed order can be cancelled", () => {
  const { inv, o } = placed();
  cancelOrder(o, inv);
  assert.throws(() => cancelOrder(o, inv), /cannot cancel a cancelled order/);
  assert.equal(inv.available("BOLT-1"), 10); // not released twice
  const s = placed();
  s.o.status = "shipped";
  assert.throws(() => cancelOrder(s.o, s.inv), /cannot cancel a shipped order/);
  assert.equal(s.inv.available("BOLT-1"), 7);
});
