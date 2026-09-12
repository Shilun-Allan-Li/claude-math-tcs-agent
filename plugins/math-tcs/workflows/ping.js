export const meta = {
  name: 'math-tcs-ping',
  description: 'Diagnostic: check how math-tcs plugin agents resolve as workflow agentType values',
  phases: [{ title: 'Ping' }],
}
phase('Ping')
const SCHEMA = { type: 'object', properties: { pong: { type: 'string' }, cwd: { type: 'string' } }, required: ['pong'] }
const results = {}
for (const t of args.agentTypes) {
  try {
    const r = await agent(
      `Command: echo '{"pong":"${t}"}'\nAlso report the current working directory as "cwd". Return {"pong": <the pong value printed>, "cwd": <cwd>}.`,
      { agentType: t, label: `ping:${t}`, schema: SCHEMA, effort: 'low' },
    )
    results[t] = r === null ? { missing: true } : r
  } catch (e) {
    results[t] = { error: String(e && e.message ? e.message : e) }
  }
}
return results
