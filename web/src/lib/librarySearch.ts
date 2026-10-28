/**
 * Search for the Library's own lists (your skills, the Lab's skill picker): the same rules as the
 * GitHub catalog's search in the engine (curate-catalog `search`). Name word > topic >
 * description; whole words, other forms of a word (bugs, bugfix), word starts, one typo. A word
 * most items match ("code") only adds score. Exact name, then phrase, then all words, then the rest.
 */

/** Mirrors the curate-catalog skill's `search` values (engine test_catalog_library checks). */
export const SEARCH = {
  exact_name: 100,
  phrase: 6,
  name: 8,
  topics: 3,
  description: 1,
  prefix: 0.8,
  fuzzy: 0.5,
  min_prefix: 4,
  min_name_prefix: 3,
  min_fuzzy: 5,
  common_share: 0.5,
  common_weight: 0.25,
  common_min_items: 8,
  stem: 0.9,
  strong_min: 0.9,
};

/** Mirrors curate-catalog `compound_tails`: "bug" finds "bugfix". */
export const COMPOUND_TAILS = ["fix", "fixes", "fixing", "fixer", "fixed", "s", "es", "ed", "ing", "er", "ers", "tracker", "tracking", "report", "reports", "hunt", "hunting"];

/** A word without its plural or verb ending: bugs, bug; reviewing, review (catalog word_stem). */
export function wordStem(w: string): string {
  for (const suf of ["ings", "ing", "ies", "es", "ed", "s"]) {
    if (w.endsWith(suf) && w.length - suf.length >= 3 && !/(ss|us|is)$/.test(w)) {
      w = w.slice(0, -suf.length) + (suf === "ies" ? "y" : "");
      break;
    }
  }
  if (w.length > 3 && w[w.length - 1] === w[w.length - 2] && !"aeiouls".includes(w[w.length - 1])) w = w.slice(0, -1);
  return w;
}

export interface Searchable {
  name: string;
  description?: string;
  topics?: string[];
  /** Extra words that count like a description, e.g. why it was suggested. */
  extra?: string;
}

export function tokens(text: string): string[] {
  return text.toLowerCase().match(/[a-z0-9]+/g) ?? [];
}

function oneTypo(a: string, b: string): boolean {
  if (a === b) return true;
  if (Math.abs(a.length - b.length) > 1) return false;
  if (a.length === b.length) {
    const diff: number[] = [];
    for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) diff.push(i);
    return (
      diff.length === 1 ||
      (diff.length === 2 &&
        diff[1] === diff[0] + 1 &&
        a[diff[0]] === b[diff[1]] &&
        a[diff[1]] === b[diff[0]])
    );
  }
  const [short, long] = a.length < b.length ? [a, b] : [b, a];
  for (let i = 0; i < long.length; i++)
    if (long.slice(0, i) + long.slice(i + 1) === short) return true;
  return false;
}

/** 1 for the same word, less for a word start or one typo, 0 for no match. */
export function wordMatch(
  q: string,
  w: string,
  minPrefix: number = SEARCH.min_prefix,
): number {
  if (q === w) return 1;
  if (q.length >= 3 && w.length >= 3 && wordStem(q) === wordStem(w)) return SEARCH.stem;
  if (q.length >= 3 && w.startsWith(q) && COMPOUND_TAILS.includes(w.slice(q.length))) return SEARCH.stem; // "bug" in "bugfix"
  if (q.length >= minPrefix && w.startsWith(q)) return SEARCH.prefix;
  if (
    q.length >= SEARCH.min_fuzzy &&
    w.length >= SEARCH.min_fuzzy - 1 &&
    q[0] === w[0]
  ) {
    // The whole word, or its start with one letter more or less (a typo in a prefix).
    for (const n of [w.length, q.length, q.length + 1])
      if (n <= w.length && oneTypo(q, w.slice(0, n))) return SEARCH.fuzzy;
  }
  return 0;
}

function best(q: string, words: string[], minPrefix?: number): number {
  let b = 0;
  for (const w of words) b = Math.max(b, wordMatch(q, w, minPrefix));
  return b;
}

/** The items matching a query, best first; ties keep the order they came in. Strong matches
 * come before weak ones (searchSplit tells them apart). */
export function searchItems<T extends Searchable>(items: T[], q: string): T[] {
  const { strong, weak } = searchSplit(items, q);
  return [...strong, ...weak];
}

/** The matches in two groups (curate-catalog `search`, strong): the query's distinctive words
 * said in the name or description (several as a phrase, in a topic like code-review, or all in
 * the name; one in the name, or in the description as the word or another form of it), and the
 * weak rest (only a topic, a theme or scattered words), shown folded under "Weaker matches". */
export function searchSplit<T extends Searchable>(items: T[], q: string): { strong: T[]; weak: T[] } {
  const words = tokens(q);
  if (!words.length) return { strong: items, weak: [] };
  const rows = items.map((it) => {
    const name = tokens(it.name);
    const desc = tokens(`${it.description ?? ""} ${it.extra ?? ""}`);
    const topicList = (it.topics ?? []).map((t) => tokens(t).join(" "));
    const topics = tokens((it.topics ?? []).join(" "));
    const own = words.map((w) => Math.max(SEARCH.name * best(w, name, SEARCH.min_name_prefix), SEARCH.description * best(w, desc)));
    return {
      name,
      exact: name.join(" "),
      text: ` ${name.join(" ")} ${desc.join(" ")} `,
      topicList,
      own,
      per: words.map((w, k) => Math.max(own[k], SEARCH.topics * best(w, topics))),
    };
  });
  const n = items.length;
  const common = words.map(
    (_, k) =>
      n >= SEARCH.common_min_items &&
      rows.filter((r) => r.per[k] > 0).length > SEARCH.common_share * n,
  );
  let required = words.map((_, k) => k).filter((k) => !common[k]);
  if (!required.length) required = words.map((_, k) => k);
  const phrase = words.join(" ");
  const ranked = rows
    .map((r, i) => ({ i, r }))
    .filter(({ r }) => required.every((k) => r.per[k] > 0))
    .map(({ i, r }) => {
      const exact = r.exact === phrase;
      const said = words.length > 1 && r.text.includes(` ${phrase} `);
      // Phrase and AND before OR: exact name, the phrase, every word in the name, the phrase
      // as one topic, every word.
      const tier = exact
        ? 5
        : said
          ? 4
          : words.every((w) => best(w, r.name, SEARCH.min_name_prefix) > 0)
            ? 3
            : words.length > 1 && r.topicList.includes(phrase)
              ? 2
              : r.per.every((v) => v > 0)
                ? 1
                : 0;
      const strong = words.length > 1 ? tier >= 2 : required.every((k) => r.own[k] >= SEARCH.strong_min);
      return {
        i,
        strong,
        tier,
        score:
          r.per.reduce((s, v, k) => s + v * (common[k] ? SEARCH.common_weight : 1), 0) +
          (exact ? SEARCH.exact_name : 0) +
          (said ? SEARCH.phrase : 0),
      };
    })
    .sort((a, b) => b.tier - a.tier || b.score - a.score || a.i - b.i);
  return {
    strong: ranked.filter((x) => x.strong).map(({ i }) => items[i]),
    weak: ranked.filter((x) => !x.strong).map(({ i }) => items[i]),
  };
}
