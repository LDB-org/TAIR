export function uniqueStrings(values) {
  const seen = new Set();
  const result = [];
  for (const s of values) {
    const key = s.toLowerCase();
    if (!seen.has(key)) {
      seen.add(key);
      result.push(s);
    }
  }
  return result;
}
