/**
 * Returns a new array containing the first occurrence of each distinct string
 * from the input, preserving original order and spelling.
 *
 * - Does not mutate the input array.
 * - Does not trim whitespace.
 * - Deduplication is case-sensitive ("a" and "A" are distinct).
 *
 * @param {string[]} values - Array of strings.
 * @returns {string[]} New array with duplicates removed.
 */
export function uniqueStrings(values) {
  const seen = new Set();
  const result = [];

  for (const value of values) {
    if (!seen.has(value)) {
      seen.add(value);
      result.push(value);
    }
  }

  return result;
}
