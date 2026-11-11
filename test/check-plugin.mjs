/**
 * 用假的 ctx 跑一遍 apply()，确认：
 * 1. 七个工具都注册上了，schema 形状合法；
 * 2. 六个技能都按 SkillRegistration 的形状注册上了；
 * 3. ctx.get('skills') 缺失时安静跳过，不抛；
 * 4. 没网、没 ComfyUI 时工具返回结构化错误而不是崩。
 */
import assert from 'node:assert'

const mod = await import('../index.mjs')

function makeCtx({ withSkills = true } = {}) {
  const tools = new Map()
  const skills = []
  const disposers = []
  const ctx = {
    logger: { info() {}, warn() {} },
    effect(factory, label) {
      const dispose = factory()
      disposers.push({ label, dispose })
      return () => {}
    },
    tools: {
      register(definition) {
        assert.ok(!tools.has(definition.name), `重复注册工具 ${definition.name}`)
        tools.set(definition.name, definition)
        return () => tools.delete(definition.name)
      },
    },
    get(service) {
      if (service === 'skills') {
        if (!withSkills) return undefined
        return {
          register(skill) {
            skills.push(skill)
            return () => {}
          },
        }
      }
      return undefined
    },
  }
  return { ctx, tools, skills, disposers }
}

/* ---------- 1. 完整装配 ---------- */
{
  const { ctx, tools, skills } = makeCtx()
  mod.apply(ctx, {})

  const expectedTools = [
    'gameart_list',
    'gameart_status',
    'gameart_build',
    'gameart_run',
    'gameart_jobs',
    'gameart_slice9',
    'gameart_verify',
  ]
  for (const name of expectedTools) {
    assert.ok(tools.has(name), `缺工具 ${name}`)
  }
  console.log(`tools: ${[...tools.keys()].join(', ')}`)
  assert.strictEqual(tools.size, expectedTools.length, '有未预期的多余工具')

  // 每个工具的形状
  for (const [name, def] of tools) {
    assert.strictEqual(typeof def.description, 'string', `${name} 缺 description`)
    assert.ok(def.description.length > 20, `${name} description 太短`)
    assert.strictEqual(def.parameters.type, 'object', `${name} parameters 不是 object`)
    assert.strictEqual(typeof def.parameters.properties, 'object', `${name} 缺 properties`)
    assert.strictEqual(typeof def.execute, 'function', `${name} 缺 execute`)
    assert.strictEqual(typeof def.output.render, 'function', `${name} 缺 output.render`)
    assert.strictEqual(def.output.schema.type, 'object', `${name} output.schema 不是 object`)
    // 声明成 required 的字段必须在 properties 里
    for (const key of def.parameters.required ?? []) {
      assert.ok(key in def.parameters.properties, `${name}: required 的 ${key} 不在 properties 里`)
    }
  }

  // run 的枚举必须和产线一致
  assert.deepStrictEqual(tools.get('gameart_run').parameters.properties.pipeline_id.enum, [
    '00',
    '01',
    '02',
    '03',
    '04',
    '05',
    '06',
    '07',
    '08',
    '09',
    '10',
    '11',
  ])
  assert.deepStrictEqual(tools.get('gameart_build').parameters.properties.ids.items.enum, [
    '00',
    '01',
    '02',
    '03',
    '04',
    '05',
    '06',
    '07',
    '08',
    '09',
    '10',
    '11',
  ])
  assert.deepStrictEqual(tools.get('gameart_run').parameters.required, ['pipeline_id'])

  // 技能
  assert.strictEqual(skills.length, 6, `技能数应为 6，实际 ${skills.length}`)
  for (const skill of skills) {
    assert.strictEqual(typeof skill.name, 'string', 'skill 缺 name')
    assert.strictEqual(typeof skill.description, 'string', `skill ${skill.name} 缺 description`)
    assert.ok(skill.content.length > 200, `skill ${skill.name} 正文太短`)
    assert.strictEqual(skill.source, 'bundled', `skill ${skill.name} source 不对`)
    assert.strictEqual(skill.provider, 'dsh-gameart', `skill ${skill.name} provider 不对`)
    assert.strictEqual(typeof skill.invocation.modelInvocable, 'boolean', 'invocation 形状不对')
    assert.strictEqual(skill.resourceBase.kind, 'directory', 'resourceBase 形状不对')
  }
  console.log(`skills: ${skills.map((s) => s.name).join(', ')}`)
}

/* ---------- 2. 没有 skills 服务时不炸 ---------- */
{
  const { ctx, tools, skills } = makeCtx({ withSkills: false })
  mod.apply(ctx, {})
  assert.strictEqual(skills.length, 0, '没有 skills 服务时不该注册技能')
  assert.strictEqual(tools.size, 7, '技能挂了不影响工具注册')
  console.log('no-skills-service: ok (工具仍注册，技能跳过)')
}

/* ---------- 3. 关闭开关 ---------- */
{
  const { ctx, tools, skills } = makeCtx()
  mod.apply(ctx, { registerTools: false, registerSkills: false })
  assert.strictEqual(tools.size, 0, 'registerTools:false 应该一个工具都不注册')
  assert.strictEqual(skills.length, 0, 'registerSkills:false 应该一个技能都不注册')
  console.log('switches: ok')
}

/* ---------- 4. skills 分组过滤 ---------- */
{
  const { ctx, skills } = makeCtx()
  mod.apply(ctx, { skills: ['core'] })
  assert.strictEqual(skills.length, 6, 'skills:["core"] 应只装 core 组（就是全部 6 个）')

  const second = makeCtx()
  mod.apply(second.ctx, { skills: ['nonexistent'] })
  assert.strictEqual(second.skills.length, 0, '不存在的分组应该一个都不注册')
  console.log('skill groups: ok')
}

/* ---------- 5. 工具在缺服务时返回结构化错误 ---------- */
{
  const { ctx, tools } = makeCtx()
  mod.apply(ctx, {})

  // subprocess 不可用 → gameart_run 应该返回 ok:false，不是抛
  const run = tools.get('gameart_run')
  const runOut = await run.execute({ pipeline_id: '11', wait: false }, { signal: { aborted: false } })
  assert.strictEqual(typeof runOut, 'object', 'gameart_run 应返回对象')
  // 后台任务模式：立刻返回 job_id
  if (runOut.job_id) {
    assert.match(runOut.job_id, /^job_[0-9a-f]{8}$/, 'job_id 形状不对')
    console.log(`run(后台): job_id=${runOut.job_id} status=${runOut.status}`)

    // 查一次，应该很快变成 failed（因为没有 subprocess）
    await new Promise((r) => setTimeout(r, 300))
    const jobsOut = await tools.get('gameart_jobs').execute({ job_id: runOut.job_id })
    assert.strictEqual(jobsOut.ok, true)
    console.log(`jobs: status=${jobsOut.job.status} message=${jobsOut.job.message}`)
    assert.strictEqual(jobsOut.job.status, 'failed', '没有 subprocess 时应判失败')
  }

  // gameart_list / gameart_build 同样不应抛
  for (const name of ['gameart_list', 'gameart_build', 'gameart_status']) {
    const def = tools.get(name)
    const args = name === 'gameart_build' ? { ids: ['08'] } : {}
    const out = await def.execute(args, { signal: { aborted: false } })
    assert.strictEqual(typeof out, 'object', `${name} 返回的不是对象`)
    assert.strictEqual(out.ok, false, `${name} 在无 subprocess 时应 ok:false`)
    assert.ok(out.error.length > 0, `${name} 应给出 error`)
    console.log(`${name}: ok:false — ${out.error.slice(0, 40)}`)
  }
}

/* ---------- 6. jobs 工具的空态 ---------- */
{
  const { ctx, tools } = makeCtx()
  mod.apply(ctx, {})
  const list = await tools.get('gameart_jobs').execute({})
  assert.strictEqual(list.ok, true)
  assert.ok(Array.isArray(list.jobs))
  const missing = await tools.get('gameart_jobs').execute({ job_id: 'job_deadbeef' })
  assert.strictEqual(missing.ok, false)
  const badCancel = await tools.get('gameart_jobs').execute({ cancel: true })
  assert.strictEqual(badCancel.ok, false)
  console.log('jobs 空态: ok')
}

/* ---------- 7. verify 的参数校验先于桥接 ---------- */
{
  const { ctx, tools } = makeCtx()
  mod.apply(ctx, {})
  const verify = tools.get('gameart_verify')

  const noKind = await verify.execute({ paths: ['a.png'] }, { signal: { aborted: false } })
  assert.strictEqual(noKind.ok, false, '缺 kind 应立刻失败，不去起进程')
  assert.match(noKind.error, /kind/)

  const noPaths = await verify.execute({ kind: 'parts', paths: [] })
  assert.strictEqual(noPaths.ok, false)
  assert.match(noPaths.error, /paths/)

  // 参数齐全但没 subprocess → 走桥接层，返回结构化错误
  const full = await verify.execute({ kind: 'flat', paths: ['a.png'] })
  assert.strictEqual(full.ok, false)
  assert.ok(full.error.length > 0)

  // kind 枚举必须覆盖十二条产线的验收需要
  const kinds = verify.parameters.properties.kind.enum
  assert.deepStrictEqual(
    kinds,
    ['parts', 'mc', 'panel', 'fx', 'flat', 'alpha', 'icon', 'tile', 'upscale', 'turnaround', 'lineart'],
    'verify 的 kind 枚举不对',
  )
  console.log('verify 参数校验: ok（先本地判参，再进桥接；kind 11 种）')
}

console.log('\nALL CHECKS PASSED')
