/** A prewritten reply is a one-use continuation, never a cached tool result. */
export class PlanReply {
  pending;

  clear() { this.pending = undefined; }

  offer(id, text, history, steps, results, session) {
    this.clear();
    if (typeof text !== 'string' || !text.trim() || text.length > 600 || !steps.length
        || results.length !== steps.length) return false;
    const safe = steps.every((step, index) => {
      const entry = results[index];
      if (entry.name !== step.name || entry.result.isError) return false;
      if (step.name === 'write' || step.name === 'edit') return true;
      // Command output is new information. Hand it back to the model to interpret.
      return step.name === 'bash' && !entry.result.details?.truncated
        && !entry.result.details?.fullOutputPath
        && entry.result.content.every(block => block.type === 'text'
          && ['', '(no output)'].includes(block.text.trim()));
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
