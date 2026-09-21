/**
 * Returns a new array retaining the first occurrence of each distinct string
 * in original order, without mutating the input.
 *
 * Deduplication is case-sensitive; upper and lower case remain distinct.
 * Whitespace is not trimmed and original spelling is preserved.
 *
 * @param {string[]} values - Array of strings to deduplicate.
 * @returns {string[]} A new array with the first occurrence of each distinct string.
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
