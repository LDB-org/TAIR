/**
 * Returns a new array retaining the first occurrence of each distinct string
 * in the original order, without mutating the input.
 *
 * - Keeps original spelling in output.
 * - Does not trim whitespace.
 * - Deduplication is case-sensitive; upper and lower case remain distinct.
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
