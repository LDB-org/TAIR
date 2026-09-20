/** Execute already-decoded native Pi calls. Never continue after a failed step. */
export async function executePlan(id, steps, tools, signal, onUpdate) {
  const results = [];
  for (let index = 0; index < steps.length; index++) {
    const step = steps[index];
    try {
      if (signal?.aborted) throw new Error('Plan cancelled');
      const tool = tools.get(step.name);
      if (!tool) throw new Error('Unknown inner tool: ' + step.name);
      onUpdate?.({ content: [{ type: 'text', text: `plan ${index + 1}/${steps.length}: ${step.name}` }], details: {} });
      const result = await tool.execute(`${id}:${index}`, step.arguments, signal);
      if (result.isError) throw new Error(JSON.stringify(result.content));
      results.push({ name: step.name, result });
    } catch (error) {
      throw new Error(JSON.stringify({ completed: results, failed_step: index, tool: step.name,
        error: error.message, remaining_steps_skipped: steps.length - index - 1 }));
    }
  }
  return results;
}
