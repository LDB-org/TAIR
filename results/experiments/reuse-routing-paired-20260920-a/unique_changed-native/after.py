/**
 * Returns a new array containing the first occurrence of each distinct string
 * in the input, preserving original order and spelling.
 *
 * Deduplication is case-insensitive for ASCII characters (using
 * `s.toLowerCase()` as the key). Whitespace is not trimmed. The input array is
 * not mutated.
 *
 * @param {string[]} values - Array of strings to deduplicate.
 * @returns {string[]} A new array with the first occurrence of each distinct string.
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
