/** Execute already-decoded native Pi calls. Never continue after a failed step. */
export async function executePlan(id, steps, tools, signal, onUpdate, onEvent = () => {}) {
  const results = [];
  const emit = event => { try { onEvent(event); } catch {} };
  emit({ event: 'plan_start', step_count: steps.length });
  for (let index = 0; index < steps.length; index++) {
    const step = steps[index];
    const started = performance.now();
    emit({ event: 'step_start', step: index, tool: step.name });
    try {
      if (signal?.aborted) throw new Error('Plan cancelled');
      const tool = tools.get(step.name);
      if (!tool) throw new Error('Unknown inner tool: ' + step.name);
      onUpdate?.({ content: [{ type: 'text', text: `plan ${index + 1}/${steps.length}: ${step.name}` }], details: {} });
      const result = await tool.execute(`${id}:${index}`, step.arguments, signal);
      if (result.isError) throw new Error(JSON.stringify(result.content));
      results.push({ name: step.name, result });
      emit({ event: 'step_success', step: index, tool: step.name, seconds: (performance.now()-started)/1000 });
    } catch (error) {
      emit({ event: 'step_failure', step: index, tool: step.name, seconds: (performance.now()-started)/1000,
        cancelled: Boolean(signal?.aborted), completed_steps: results.length, skipped_steps: steps.length-index-1 });
      emit({ event: 'plan_failure', completed_steps: results.length, skipped_steps: steps.length-index-1 });
      throw new Error(JSON.stringify({ completed: results, failed_step: index, tool: step.name,
        error: error.message, remaining_steps_skipped: steps.length - index - 1 }));
    }
  }
  emit({ event: 'plan_success', completed_steps: results.length });
  return results;
}
