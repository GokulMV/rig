export type Rates = Record<string, number>; // value of 1 unit of the currency in EUR

export function convert(cents: number, from: string, to: string, rates: Rates): number {
  if (from === to) return cents;
  const r = rates[from] / rates[to];
  return Math.floor(cents * r);
}

export function format(cents: number, currency: string): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, "0")} ${currency}`;
}
