export const meta = {
  name: 'math-tcs-run',
  description: 'math-tcs: translate → scaffold → verify → prove one mathematics source into Lean (stage control, retries and result collection in code; agents do the LLM work; scripts do Lean and files)',
  phases: [
    { title: 'Translate', detail: 'extract items → translator agent → validate (≤2 fix rounds) → register' },
    { title: 'Scaffold', detail: 'context packages → scaffolder agent → apply + elaborate (≤2 repair rounds)' },
    { title: 'Verify', detail: 'per declaration: snapshot → semantic ‖ reuse reviewers → combine' },
    { title: 'Prove', detail: 'per eligible declaration (batches of K): lock → prover (budgeted) → promote → unlock' },
    { title: 'Collect', detail: 'run record with an explicit status for every declaration × stage' },
  ],
}

// ---------------------------------------------------------------- configuration
const A = args || {}
const PREFIX = A.agentPrefix === undefined ? 'math-tcs:' : A.agentPrefix
const T = n => `${PREFIX}${n}`
const MT0 = `python3 "${A.pluginRoot}/scripts/mathtcs.py"`
const MT = MT0  // every command below appends --root via mtc()
const NOW = A.startedAt || 'unknown-start'
const STAGES = A.stages || ['translate', 'scaffold', 'verify', 'prove']
const PARALLEL = Math.max(1, Number(A.parallel) || 1)
const MAX_TRANSLATE_FIX = 2
const MAX_SCAFFOLD_REPAIR = 2
const MAX_REVIEW_RETRY = 1
const MAX_PROVER_RESPAWN = 1
const OBJECT_KINDS = new Set(['definition', 'construction', 'notation'])
const q = s => `"${String(s).replace(/(["\\$`])/g, '\\$1')}"`
const safe = s => String(s).replace(/[^0-9A-Za-z_.-]/g, '-')
const R = A.projectRoot
const mtc = sub => `${MT0} ${sub} --root ${q(R)}`
const ART = `${R}/math-tcs`

// ---------------------------------------------------------------- run record
const rec = { started_at: NOW, args: A, stages_planned: STAGES, stages_run: [], declarations: {}, agents: [], notes: [], ids: [] }
const mark = (id, stage, status, extra) => { (rec.declarations[id] = rec.declarations[id] || {})[stage] = Object.assign({ status }, extra || {}) }
const note = m => { rec.notes.push(m); log(m) }
const outOfBudget = () => Boolean(budget && budget.total && budget.remaining() < 30000)

// ---------------------------------------------------------------- schemas
const NSTR = { anyOf: [{ type: 'string' }, { type: 'null' }] }
const RUNNER_SCHEMA = {
  type: 'object',
  properties: { exit: { type: 'integer' }, stdout_json: { anyOf: [{ type: 'object' }, { type: 'null' }] }, stdout: { type: 'string' }, stderr: { type: 'string' } },
  required: ['exit', 'stdout_json'],
}
const TRANSLATE_SCHEMA = {
  type: 'object',
  properties: { path: { type: 'string' }, ids: { type: 'array', items: { type: 'string' } }, tbd: { type: 'integer' }, questions: { type: 'integer' } },
  required: ['path', 'ids'],
}
const PROPOSALS_SCHEMA = {
  type: 'object',
  properties: {
    module: NSTR, title: NSTR, source: NSTR,
    proposals: { type: 'array', items: { type: 'object', properties: {
      id: { type: 'string' }, kind: NSTR, representation: { type: 'string' }, lean_name: NSTR,
      imports: { type: 'array', items: { type: 'string' } }, opens: { type: 'array', items: { type: 'string' } },
      statement: NSTR, difficulty: { type: 'object' }, deviations: { type: 'array', items: { type: 'string' } },
      blockers: { type: 'array' }, names_checked: { type: 'array' }, existing_name: NSTR, owner: NSTR, doc_extra: NSTR,
    }, required: ['id', 'representation'] } },
  },
  required: ['proposals'],
}
const FINDING = { type: 'object' }
const SEMANTIC_SCHEMA = {
  type: 'object',
  properties: { kind: { type: 'string' }, agent: { type: 'string' }, id: { type: 'string' }, statement_sha256: NSTR, verdict: { type: 'string' },
    fidelity_findings: { type: 'array', items: FINDING }, degenerate_case_findings: { type: 'array', items: FINDING }, notes: NSTR },
  required: ['statement_sha256', 'verdict', 'fidelity_findings', 'degenerate_case_findings'],
}
const REUSE_SCHEMA = {
  type: 'object',
  properties: { kind: { type: 'string' }, agent: { type: 'string' }, id: { type: 'string' }, statement_sha256: NSTR, verdict: { type: 'string' },
    searched: { type: 'array', items: { type: 'string' } }, candidates: { type: 'array', items: FINDING }, findings: { type: 'array', items: FINDING }, notes: NSTR },
  required: ['statement_sha256', 'verdict', 'searched', 'candidates'],
}
const PROVE_SCHEMA = {
  type: 'object',
  properties: { id: { type: 'string' }, result: { type: 'string' }, statement_sha256: NSTR, work: NSTR, proof: NSTR,
    helpers: { type: 'array', items: FINDING }, attempts: { type: 'array', items: FINDING }, checks_used: { type: 'integer' }, budget: { type: 'integer' },
    trust: NSTR, axioms: { anyOf: [{ type: 'array', items: { type: 'string' } }, { type: 'null' }] }, statement_change: { anyOf: [{ type: 'object' }, { type: 'null' }] } },
  required: ['result', 'attempts'],
}

// ---------------------------------------------------------------- deterministic steps through the tool-runner agent
async function run(cmd, opts) {
  opts = opts || {}
  const files = opts.files || []
  const fileText = files.length
    ? 'Before running the command, write these files exactly as given (Write tool, overwrite if present):\n' +
      files.map(f => `=== file: ${f.path}\n${f.content}\n=== end file`).join('\n') + '\n\n'
    : ''
  const prompt = `${fileText}Working directory: ${R} (the command already carries --root; do not cd).\nCommand: ${cmd}\n\nRun exactly this one command with the Bash tool and return its result. Do not run any other command, do not retry, do not interpret the output.`
  const r = await agent(prompt, { agentType: T('tool-runner'), schema: RUNNER_SCHEMA, effort: 'low', label: opts.label || cmd.slice(0, 48), phase: opts.phase })
  rec.agents.push({ label: opts.label || cmd.slice(0, 48), phase: opts.phase, kind: 'runner', null_result: r === null })
  if (r === null) return { exit: -1, stdout_json: null, stdout: '', stderr: 'tool-runner returned null (skipped or terminal error)', missing: true }
  return r
}
const J = r => (r && r.stdout_json) || null
const why = r => (r && (r.stderr || r.stdout || (r.missing ? 'runner missing' : 'no output'))) || 'no output'

async function llm(kind, prompt, schema, label, phase) {
  const r = await agent(prompt, { agentType: T(kind), schema, label, phase })
  rec.agents.push({ label, phase, kind, null_result: r === null })
  return r
}

// ---------------------------------------------------------------- collect (always runs, even on early exit)
async function collect(summary) {
  phase('Collect')
  rec.summary = summary
  const payloadPath = `${ART}/runs/${safe(NOW)}.payload.json`
  const r = await run(`${mtc(`runs record --payload ${q(payloadPath)} --started-at ${q(NOW)}`)}`,
    { label: 'record', phase: 'Collect', files: [{ path: payloadPath, content: JSON.stringify(rec, null, 1) }] })
  const j = J(r)
  return {
    started_at: NOW, stages_planned: STAGES, stages_run: rec.stages_run,
    counts: j ? j.counts : null, record: j ? j.path : null, record_error: j ? null : why(r),
    declarations: rec.declarations, notes: rec.notes, agents: rec.agents.length, summary,
  }
}

// ================================================================ Translate
phase('Translate')
let slug = A.slug, chapter = A.chapter, title = null, ids = [], kinds = {}
const ex = await run(`${mtc(`source extract ${q(A.source)}${A.slug ? ' --slug ' + q(A.slug) : ''}${A.chapter ? ' --chapter ' + q(A.chapter) : ''}`)}`, { label: 'extract', phase: 'Translate' })
const exj = J(ex)
if (!exj || ex.exit !== 0) {
  note(`translate: source extract failed: ${why(ex)}`)
  return await collect({ ok: false, failed_at: 'translate', reason: why(ex) })
}
slug = exj.slug; chapter = exj.chapter; title = exj.title
const itemsPath = `${ART}/annotated/${slug}-ch${chapter}.items.json`
const annotatedPath = `${ART}/annotated/${slug}-ch${chapter}.md`
const extractedIds = (exj.items || []).map(i => i.id)
extractedIds.forEach(id => { kinds[id] = (exj.items.find(i => i.id === id) || {}).kind })

const translatorPrompt = errors => `You are invoked by the math-tcs run workflow. Follow your agent instructions (annotated/v1 format) exactly.
source: ${A.source}
items: ${itemsPath}
output: ${annotatedPath}
slug: ${slug}
chapter: ${chapter}
title: ${title}
source_sha256: ${exj.sha256}
Read the source in full and the items file. Write the annotated file with the Write tool, then return {path, ids, tbd, questions}.` +
  (errors ? `\n\nThe previous attempt was rejected by the validator. Fix every error below (edit the existing file):\n- ${errors.join('\n- ')}` : '')

let validated = null, errors = null
if (!outOfBudget()) {
  const wrote = await run(`${mtc(`source extract ${q(A.source)}${A.slug ? ' --slug ' + q(A.slug) : ''}${A.chapter ? ' --chapter ' + q(A.chapter) : ''}`)} > ${q(itemsPath)} && echo '{"saved": true}'`, { label: 'save items', phase: 'Translate' })
  if (wrote.exit !== 0) note(`translate: could not save items JSON: ${why(wrote)}`)
  for (let round = 0; round <= MAX_TRANSLATE_FIX; round++) {
    const t = await llm('formal-translator', translatorPrompt(errors), TRANSLATE_SCHEMA, `translate:${slug}${round ? ':fix' + round : ''}`, 'Translate')
    if (t === null) { note(`translate: translator returned null (round ${round})`); break }
    const v = await run(`${mtc(`annotated validate ${q(annotatedPath)} --source ${q(A.source)} --assign-ids --write`)}`, { label: `validate${round ? ':' + round : ''}`, phase: 'Translate' })
    const vj = J(v)
    if (vj && vj.ok) { validated = vj; break }
    errors = (vj && vj.errors && vj.errors.length) ? vj.errors : [`validator produced no usable output: ${why(v)}`]
    note(`translate: validation round ${round} failed (${errors.length} errors)`)
  }
}
if (!validated) {
  extractedIds.forEach(id => mark(id, 'translate', 'failed', { reason: errors ? errors.slice(0, 5).join(' | ') : 'translator missing', annotated: annotatedPath }))
  rec.stages_run.push('translate')
  return await collect({ ok: false, failed_at: 'translate', errors: errors || ['translator missing'] })
}
const reg = await run(`${mtc(`annotated register ${q(annotatedPath)} --source ${q(A.source)} --at ${q(NOW)}`)}`, { label: 'register', phase: 'Translate' })
const regj = J(reg)
if (!regj || reg.exit !== 0) {
  extractedIds.forEach(id => mark(id, 'translate', 'failed', { reason: `register failed: ${why(reg)}` }))
  rec.stages_run.push('translate')
  return await collect({ ok: false, failed_at: 'translate:register', reason: why(reg) })
}
ids = regj.registered.map(r => r.id)
regj.registered.forEach(r => { kinds[r.id] = r.kind; mark(r.id, 'translate', 'ok', { annotated: annotatedPath, kind: r.kind }) })
rec.ids = ids
rec.stages_run.push('translate')
note(`translate: ${ids.length} declarations registered (${validated.assignments ? validated.assignments.length : 0} ids assigned)`)
if (!STAGES.includes('scaffold')) return await collect({ ok: true, stopped_after: 'translate' })

// ================================================================ Scaffold
phase('Scaffold')
const staleR = await run(`${mtc(`manifest stale ${ids.map(q).join(' ')}`)}`, { label: 'stale', phase: 'Scaffold' })
const staleJ = J(staleR) || { results: [] }
const protectedIds = new Set(staleJ.results.filter(r => !A.force && (r.status === 'proved' || r.human_edited)).map(r => r.id))
const todo = ids.filter(id => !protectedIds.has(id))
protectedIds.forEach(id => mark(id, 'scaffold', 'skipped', { reason: 'proved or human-edited block is protected (use --force)' }))
let modShort = A.module || null
if (!modShort) {
  const mn = await run(`${mtc(`scaffold module-name --title ${q(title)}`)}`, { label: 'module-name', phase: 'Scaffold' })
  modShort = (J(mn) && J(mn).module_short) || 'MathTcsModule'
}
const modInfoR = await run(`${mtc(`scaffold module-path ${q(modShort)}`)}`, { label: 'module-path', phase: 'Scaffold' })
const modInfo = J(modInfoR) || {}
const modulePath = modInfo.path ? `${R}/${modInfo.path}` : null
let applied = null
if (todo.length && !outOfBudget()) {
  const ctxR = await run(`${mtc(`context scaffold ${todo.map(q).join(' ')} --annotated ${q(annotatedPath)}`)}`, { label: 'context:scaffold', phase: 'Scaffold' })
  const packages = ((J(ctxR) || {}).packages || []).map(p => `${R}/${p.path}`)
  const proposalsPath = `${ART}/context/scaffold/${slug}-ch${chapter}-proposals.json`
  const scaffolderPrompt = (diagnostics, previous) => `You are invoked by the math-tcs run workflow. Follow your agent instructions exactly (statements only; theorem bodies exactly "by\\n  sorry"; definitions need real bodies; missing terms are blockers).
context packages (one per declaration, read all): ${packages.join(', ')}
declaration ids in source order: ${todo.join(', ')}
project: root ${R}; module ${modInfo.module || modShort}; file ${modulePath || '(new)'}; namespace ${modInfo.namespace || 'MathTcs'}; Mathlib sources ${R}/.lake/packages/mathlib/Mathlib
probe: ${mtc('probe check <Name> [<Name> ...] --imports <Module,Module>')}   (run from ${R}; batch names; ~20-60 s per call)
Return the proposals JSON with "module": "${modShort}".` +
    (diagnostics ? `\n\nThe previous proposals were applied and Lean reported problems. Repair exactly these and return the full proposals again:\n${JSON.stringify(diagnostics, null, 1)}\n\nPrevious proposals:\n${JSON.stringify(previous, null, 1)}` : '')
  let diagnostics = null, previous = null
  for (let round = 0; round <= MAX_SCAFFOLD_REPAIR; round++) {
    const s = await llm('lean-scaffolder', scaffolderPrompt(diagnostics, previous), PROPOSALS_SCHEMA, `scaffold:${modShort}${round ? ':repair' + round : ''}`, 'Scaffold')
    if (s === null) { note(`scaffold: scaffolder returned null (round ${round})`); break }
    s.module = modShort
    const ap = await run(`${mtc(`scaffold apply ${q(proposalsPath)} --module ${q(modShort)} --at ${q(NOW)}${A.force ? ' --force' : ''}`)}`,
      { label: `apply${round ? ':' + round : ''}`, phase: 'Scaffold', files: [{ path: proposalsPath, content: JSON.stringify(s, null, 1) }] })
    applied = J(ap)
    if (!applied) { note(`scaffold: apply produced no JSON: ${why(ap)}`); break }
    const elabBlocked = (applied.blocked || []).filter(b => b.from === 'elaboration')
    const elabOk = applied.elaboration ? applied.elaboration.ok : true
    if (elabOk && elabBlocked.length === 0) break
    diagnostics = { module_errors: applied.elaboration ? applied.elaboration.unattributed_errors : [], blocked: elabBlocked, failed: applied.failed }
    previous = s
    note(`scaffold: elaboration problems after round ${round} (${elabBlocked.length} blocked, module ok=${elabOk})`)
  }
}
const scaffoldedIds = []
if (applied) {
  ;(applied.written || []).forEach(w => { scaffoldedIds.push(w.id); mark(w.id, 'scaffold', 'ok', { rev: w.rev, lean_name: w.lean_name, module: applied.module, path: applied.path }) })
  ;(applied.blocked || []).forEach(b => mark(b.id, 'scaffold', 'failed', { reason: 'blocked: ' + (b.blockers || []).join(' | ') }))
  ;(applied.skipped || []).forEach(s => mark(s.id, 'scaffold', s.reason === 'existing representation' ? 'ok' : 'skipped', { reason: s.reason, existing_name: s.existing_name }))
  ;(applied.failed || []).forEach(f => mark(f.id, 'scaffold', 'failed', { reason: f.reason }))
}
todo.forEach(id => { if (!rec.declarations[id] || !rec.declarations[id].scaffold) mark(id, 'scaffold', 'missing', { reason: 'no scaffold result recorded (agent or apply missing)' }) })
rec.stages_run.push('scaffold')
note(`scaffold: ${scaffoldedIds.length} blocks written to ${applied ? applied.path : '(none)'}`)
if (!STAGES.includes('verify')) return await collect({ ok: true, stopped_after: 'scaffold', module: applied ? applied.path : null })

// ================================================================ Verify
phase('Verify')
ids.forEach(id => { if (!scaffoldedIds.includes(id)) { const s = rec.declarations[id] && rec.declarations[id].scaffold; mark(id, 'verify', 'skipped', { reason: s && s.existing_name ? 'existing representation' : 'not scaffolded' }) } })
const reviewerPrompt = (kind, ctxPath, id) => `You are invoked by the math-tcs run workflow as the ${kind}. Follow your agent instructions exactly.
context: ${ctxPath}
declaration: ${id}
Review exactly the revision frozen in that context.json and echo its statement_sha256.` +
  (kind === 'reuse-reviewer' ? `\nprobe: ${mtc('probe check <Name> [...] --imports <M,N>')}   and   ${mtc(`probe tactic --file ${q(modulePath)} --id ${q(id)} --tactic "exact?"`)}   (run from ${R}; each call runs Lean once)` : '')
async function review(kind, ctxPath, id, schema) {
  for (let attempt = 0; attempt <= MAX_REVIEW_RETRY; attempt++) {
    const r = await llm(kind, reviewerPrompt(kind, ctxPath, id), schema, `${kind.replace('-reviewer', '')}:${id}${attempt ? ':retry' : ''}`, 'Verify')
    if (r !== null) return r
  }
  return null
}
const verifyResults = await pipeline(scaffoldedIds,
  async id => {
    const s = await run(`${mtc(`snapshot ${q(id)} --at ${q(NOW)}`)}`, { label: `snapshot:${id}`, phase: 'Verify' })
    const sj = J(s)
    if (!sj || s.exit !== 0) { mark(id, 'verify', 'failed', { reason: `snapshot failed: ${why(s)}` }); return null }
    if (sj.skipped) { mark(id, 'verify', 'skipped', { reason: sj.reason }); return null }
    return sj
  },
  async (snap, id) => {
    if (!snap) return null
    const ctxPath = `${R}/${snap.context}`
    const [sem, reuse] = await parallel([
      () => review('semantic-reviewer', ctxPath, id, SEMANTIC_SCHEMA),
      () => review('reuse-reviewer', ctxPath, id, REUSE_SCHEMA),
    ])
    return { snap, sem, reuse }
  },
  async (both, id) => {
    if (!both) return null
    const dir = `${R}/${both.snap.dir}`
    const files = []
    if (both.sem) files.push({ path: `${dir}/semantic.json`, content: JSON.stringify(Object.assign({ kind: 'model_review', agent: 'semantic-reviewer', id }, both.sem), null, 1) })
    if (both.reuse) files.push({ path: `${dir}/reuse.json`, content: JSON.stringify(Object.assign({ kind: 'model_review', agent: 'reuse-reviewer', id }, both.reuse), null, 1) })
    const c = await run(`${mtc(`report combine ${q(id)} --rev ${both.snap.rev} --at ${q(NOW)}`)}`, { label: `combine:${id}`, phase: 'Verify', files })
    const cj = J(c)
    if (!cj || c.exit !== 0) { mark(id, 'verify', 'failed', { reason: `combine failed: ${why(c)}`, semantic: both.sem ? 'ok' : 'missing', reuse: both.reuse ? 'ok' : 'missing' }); return null }
    mark(id, 'verify', 'ok', { action: cj.action, reason: cj.reason, elaboration_ok: cj.elaboration_ok, trust: cj.trust, semantic: cj.semantic, reuse: cj.reuse, report: cj.report, md: cj.md, status: cj.status, rev: cj.rev })
    return cj
  },
)
scaffoldedIds.forEach(id => { if (!rec.declarations[id] || !rec.declarations[id].verify) mark(id, 'verify', 'missing', { reason: 'verify pipeline produced no result' }) })
rec.stages_run.push('verify')
const actions = {}
verifyResults.filter(Boolean).forEach(r => { actions[r.action] = (actions[r.action] || 0) + 1 })
note(`verify: ${verifyResults.filter(Boolean).length}/${scaffoldedIds.length} combined — actions ${JSON.stringify(actions)}`)
if (!STAGES.includes('prove')) return await collect({ ok: true, stopped_after: 'verify', actions })

// ================================================================ Prove
phase('Prove')
const eligible = []
scaffoldedIds.forEach(id => {
  const v = rec.declarations[id] && rec.declarations[id].verify
  if (!v || v.status !== 'ok') { mark(id, 'prove', 'skipped', { reason: 'not verified' }); return }
  if (OBJECT_KINDS.has(kinds[id])) { mark(id, 'prove', 'skipped', { reason: 'definition (object kind): nothing to prove' }); return }
  if (!(v.action === 'prove' || v.action === 'reuse') && !A.force) { mark(id, 'prove', 'skipped', { reason: `verify action is ${v.action}` }); return }
  if (!v.elaboration_ok) { mark(id, 'prove', 'skipped', { reason: 'statement does not elaborate' }); return }
  eligible.push(id)
})
let chain = Promise.resolve()
const serial = fn => { const p = chain.then(fn, fn); chain = p.catch(() => {}); return p }
const budgetN = Number(A.budget) || 4
async function proveOne(id) {
  if (outOfBudget()) { mark(id, 'prove', 'skipped', { reason: 'token budget exhausted' }); return }
  const lock = await run(`${mtc(`manifest lock ${q(id)} --stage prove --at ${q(NOW)} --owner ${q('workflow:' + NOW)}`)}`, { label: `lock:${id}`, phase: 'Prove' })
  if (lock.exit !== 0) { mark(id, 'prove', 'skipped', { reason: `locked: ${why(lock)}` }); return }
  try {
    const prep = await run(`${mtc(`scratch prepare ${q(id)}`)}`, { label: `scratch:${id}`, phase: 'Prove' })
    const work = J(prep) && J(prep).work
    const ctx = await run(`${mtc(`context prove ${q(id)}`)}`, { label: `context:${id}`, phase: 'Prove' })
    const ctxPath = J(ctx) && J(ctx).packages && J(ctx).packages[0] ? `${R}/${J(ctx).packages[0].path}` : null
    if (!work || !ctxPath) { mark(id, 'prove', 'failed', { reason: `preparation failed: ${!work ? why(prep) : why(ctx)}` }); return }
    const prompt = `You are invoked by the math-tcs run workflow as the proof-worker. Follow your agent instructions exactly; never change the statement; edit only the block for ${id} in the work file.
context: ${ctxPath}
work: ${work}
check: ${mtc(`check --file ${q(work)} --tag ${q('prove/' + id)} --brief`)}   (run from ${R}; one Lean run each)
budget: ${budgetN} check runs
Return the result JSON.`
    let result = null
    for (let attempt = 0; attempt <= MAX_PROVER_RESPAWN; attempt++) {
      result = await llm('proof-worker', prompt, PROVE_SCHEMA, `prove:${id}${attempt ? ':respawn' : ''}`, 'Prove')
      if (result !== null) break
    }
    if (result === null) { mark(id, 'prove', 'missing', { reason: 'proof-worker returned null twice' }); return }
    const resultPath = `${ART}/reports/${id}/prove-result.json`
    const rep = await run(`${mtc(`report prove ${q(id)} --result ${q(resultPath)} --at ${q(NOW)}`)}`,
      { label: `report:${id}`, phase: 'Prove', files: [{ path: resultPath, content: JSON.stringify(Object.assign({ id, budget: budgetN }, result), null, 1) }] })
    const repj = J(rep) || {}
    let promoted = null
    if (result.result === 'proved') {
      promoted = await serial(() => run(`${mtc(`promote ${q(id)} --attempt ${q(work)} --at ${q(NOW)}`)}`, { label: `promote:${id}`, phase: 'Prove' }))
    }
    const pj = J(promoted)
    const status = result.result === 'proved' ? (pj && pj.promoted ? 'ok' : 'failed') : (result.result === 'unfinished' || result.result === 'statement_change_required' ? 'ok' : 'failed')
    mark(id, 'prove', status, {
      result: result.result, promoted: Boolean(pj && pj.promoted), trust: pj ? pj.trust : result.trust, axioms: pj ? pj.axioms : result.axioms,
      reason: pj && !pj.promoted ? pj.reason : (result.result === 'proved' ? 'promoted' : result.result),
      attempts: (result.attempts || []).length, helpers: (result.helpers || []).length, report: repj.report || null, statement_change: result.statement_change || null,
    })
  } finally {
    await run(`${mtc(`manifest unlock ${q(id)}`)}`, { label: `unlock:${id}`, phase: 'Prove' })
  }
}
for (let i = 0; i < eligible.length; i += PARALLEL) {
  const batch = eligible.slice(i, i + PARALLEL)
  await parallel(batch.map(id => () => proveOne(id)))
}
eligible.forEach(id => { if (!rec.declarations[id] || !rec.declarations[id].prove) mark(id, 'prove', 'missing', { reason: 'prove produced no result' }) })
rec.stages_run.push('prove')
const proved = eligible.filter(id => rec.declarations[id].prove.promoted).length
note(`prove: ${proved}/${eligible.length} promoted`)
return await collect({ ok: true, stopped_after: 'prove', proved, eligible: eligible.length })
