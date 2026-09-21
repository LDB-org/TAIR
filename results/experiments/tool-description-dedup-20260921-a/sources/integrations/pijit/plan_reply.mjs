/** A prewritten reply is a one-use continuation, never a cached tool result. */
export class PlanReply {
  pending;
  rejectionReason;

  clear() { this.pending = undefined; this.rejectionReason = undefined; }

  reject(reason) { this.rejectionReason = reason; return false; }

  offer(id, text, history, steps, results, session, expectedOutputs = []) {
    this.clear();
    if (typeof text !== 'string' || !text.trim() || text.length > 600 || !steps.length
        || results.length !== steps.length) return this.reject('invalid_completion_metadata');
    const expected = new Map();
    if (!Array.isArray(expectedOutputs)) return this.reject('invalid_expected_outputs');
    for (const output of expectedOutputs) {
      if (!Number.isInteger(output.step) || steps[output.step]?.name !== 'bash'
          || typeof output.text !== 'string' || expected.has(output.step)) return this.reject('invalid_expected_outputs');
      expected.set(output.step, output.text);
    }
    const safe = steps.every((step, index) => {
      const entry = results[index];
      if (entry.name !== step.name || entry.result.isError) return this.reject('tool_result_mismatch_or_failure');
      if (step.name === 'write' || step.name === 'edit') return true;
      // Only a predeclared exact receipt can bypass interpretation of nonempty output.
      if (step.name !== 'bash') return this.reject('tool_requires_interpretation');
      if (entry.result.details?.truncated || entry.result.details?.truncation?.truncated
          || entry.result.details?.fullOutputPath) return this.reject('truncated_output');
      if (!entry.result.content.every(block => block.type === 'text')) return this.reject('nontext_output');
      if (expected.has(index)) return entry.result.content.map(block => block.text).join('') === expected.get(index)
        || this.reject('expected_output_mismatch');
      return entry.result.content.every(block => ['', '(no output)'].includes(block.text.trim()))
        || this.reject('unacknowledged_output');
    });
    if (!safe) return false;
    this.pending = { id, text, history: JSON.stringify(history), steps: JSON.stringify(steps), session };
    return true;
  }

  take(messages, session, aborted = false) {
    const pending = this.pending;
    this.clear();
    if (!pending || aborted || session !== pending.session || messages.length < 2) return;
    const [assistant, result] = messages.slice(-2);
    if (JSON.stringify(messages.slice(0, -2)) !== pending.history
        || assistant.role !== 'assistant' || result.role !== 'toolResult'
        || result.toolCallId !== pending.id || result.toolName !== 'plan' || result.isError) return;
    const calls = assistant.content.filter(block => block.type === 'toolCall');
    if (calls.length !== 1 || calls[0].id !== pending.id || calls[0].name !== 'plan'
        || JSON.stringify(calls[0].arguments.steps) !== pending.steps) return;
    return pending.text;
  }
}
