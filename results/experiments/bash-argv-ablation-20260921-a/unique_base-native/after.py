/**
 * Returns a new array containing the first occurrence of each distinct string
 * from the input, preserving original order and spelling.
 *
 * Deduplication is case-sensitive (e.g. "a" and "A" are distinct).
 * Whitespace is not trimmed. The input array is not mutated.
 *
 * @param {string[]} values - Array of strings to deduplicate.
 * @returns {string[]} A new array with unique strings in original order.
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
