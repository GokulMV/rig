function validateSku(sku: string): void {
  if (!/^[A-Za-z][A-Za-z0-9-]{2,11}$/.test(sku)) throw new Error(`invalid SKU: ${sku}`);
}

export class Inventory {
  private stock = new Map<string, number>();

  add(sku: string, qty: number): void {
    validateSku(sku);
    this.stock.set(sku, (this.stock.get(sku) ?? 0) + qty);
  }

  available(sku: string): number {
    validateSku(sku);
    return this.stock.get(sku) ?? 0;
  }

  reserve(sku: string, qty: number): void {
    validateSku(sku);
    const have = this.available(sku);
    if (have < qty) throw new Error(`out of stock: ${sku}`);
    this.stock.set(sku, have - qty);
  }

  release(sku: string, qty: number): void {
    validateSku(sku);
    this.stock.set(sku, this.available(sku) + qty);
  }
}
