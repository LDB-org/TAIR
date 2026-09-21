/**
 * Return a new array retaining the first occurrence of each distinct string
 * in original order, without mutating the input.
 *
 * Deduplication uses s.toLowerCase() as the key, so ASCII case differences
 * are ignored. Original spelling is preserved and whitespace is not trimmed.
 *
 * @param {string[]} values - Array of strings.
 * @returns {string[]} New array with unique strings in original order.
 */
export function uniqueStrings(values) {
  const seen = new Set();
  const result = [];

  for (const value of values) {
    const key = value.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      result.push(value);
    }
  }

  return result;
}
