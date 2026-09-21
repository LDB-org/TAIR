/** Metadata only; never stores model responses or tool results. */
export class CapabilitiesCache {
  entry;
  clear() { this.entry = undefined; }
  remember(key, session, snapshot) {
    this.clear();
    if (!session || snapshot?.session_id !== session) return;
    this.entry = { key, snapshot: structuredClone(snapshot) };
  }
  get(key, session, now = Date.now() / 1000) {
    const entry = this.entry;
    const age = now - entry?.snapshot.observed_at;
    if (!entry || entry.key !== key || entry.snapshot.session_id !== session
        || !Number.isFinite(age) || age < 0 || age >= 30) {
      this.clear();
      return;
    }
    return structuredClone(entry.snapshot);
  }
}
