/**
 * 端到端：用真的 subprocess 服务跑一次 gameart_verify。
 *
 * 前面的套件都是拿假 subprocess 测「参数校验」，从没验证过
 * bridge → python → imageqa 这条链在工具层真的通。这里补上。
 */
import { spawn } from 'node:child_process'
import path from 'node:path'

const ROOT = path.dirname(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')))
const PY = 'python'

// 最小 subprocess 服务实现：够 runBridge 用就行
const subprocess = {
  async resolveExecutable(command) {
    // 只要能找到 python 就行，这里已经假定在 PATH 上
    if (command === 'python' || command === 'python3' || command === 'py') {
      return { command, path: command }
    }
    throw new Error(`not found: ${command}`)
  },
  // 合同：spawn 必须同步返回 handle（不是 Promise）。写成 async 会让
  // runBridge 拿到 Promise，readCollected 读不到东西，最后误报「桥接没输出」。
  spawn(spec) {
    const child = spawn(spec.argv[0], spec.argv.slice(1), {
      cwd: spec.cwd,
      env: { ...process.env, ...(spec.env ?? {}) },
      windowsHide: true,
    })
    const stdout = []
    const stderr = []
    child.stdout.on('data', (chunk) => stdout.push(chunk))
    child.stderr.on('data', (chunk) => stderr.push(chunk))
    const done = new Promise((resolve, reject) => {
      child.on('error', reject)
      child.on('close', (code) => resolve({ exitCode: code }))
    })
    return {
      done,
      collected: {
        stdout: { readFrom: () => ({ text: Buffer.concat(stdout).toString('utf8') }) },
        stderr: { readFrom: () => ({ text: Buffer.concat(stderr).toString('utf8') }) },
      },
      terminate() {
        child.kill()
      },
    }
  },
}

const tools = new Map()
const ctx = {
  logger: { warn() {}, info() {} },
  effect(factory) {
    return factory()
  },
  get(name) {
    if (name === 'subprocess') return subprocess
    if (name === 'skills') return null
    return undefined
  },
  tools: {
    register(def) {
      tools.set(def.name, def)
      return () => tools.delete(def.name)
    },
  },
}

const mod = await import('../index.mjs')
await mod.apply(ctx, { registerSkills: false, pythonPath: PY })

const verify = tools.get('gameart_verify')
if (!verify) {
  console.log('FAIL: 没注册 gameart_verify')
  process.exit(1)
}

let failures = []
const exec = { signal: new AbortController().signal }

async function call(label, args, expect) {
  const value = await verify.execute(args, exec)
  const ok = expect(value)
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${label}`)
  if (!ok) {
    failures.push(label)
    console.log('      ', JSON.stringify(value).slice(0, 300))
  }
  return value
}

// 真实样本：这四组是已知的确定性结果
const S = path.join(ROOT, 'samples')

await call('panel 真实面板', { kind: 'panel', paths: [path.join(S, '09/ui_panel_9slice_00006_.png')] }, (v) => v.ok === true && v.kind === 'panel' && v.checks.corners_filled === true)

await call('mc 单色中间块', { kind: 'mc', paths: [path.join(S, '09/9slice_mc_704x704_00007_.png')] }, (v) => v.ok === true && v.unique_rgb === 1)

await call('parts 头部+身体', { kind: 'parts', paths: [path.join(S, '10/part_head_00010_.png'), path.join(S, '10/part_body_00011_.png')] }, (v) => v.ok === true && v.overlap_px === 0 && v.transparent_rgb_max === 0)

await call('flat 背景', { kind: 'flat', paths: [path.join(S, '08/bg_scene_00001_.png')] }, (v) => v.kind === 'flat' && v.checks.is_1080p === true && v.has_alpha === false)

await call('fx 光效贴图', { kind: 'fx', paths: [path.join(S, '11/fx_energy_00004_.png')] }, (v) => v.ok === true && v.style === 'sprite')

await call('fx 满屏闪光应拒绝', { kind: 'fx', paths: [path.join(S, '11/fx_energy_00001_.png')] }, (v) => v.ok === false && v.style === 'full_frame' && typeof v.hint === 'string')

// 新增产线的验收器：经真实的桥接层再走一遍，确认参数编排没接错
await call('icon 未抠图应拒绝', { kind: 'icon', paths: [path.join(S, '09/ui_panel_9slice_00006_.png')] }, (v) => v.ok === false && v.checks.bg_transparent === false && typeof v.hint === 'string')

await call('tile 场景图应判有接缝', { kind: 'tile', paths: [path.join(S, '08/bg_scene_00001_.png')] }, (v) => v.kind === 'tile' && v.checks.square === false && v.checks.seam_h_ok === false)

await call('upscale 背景图合格', { kind: 'upscale', paths: [path.join(S, '08/bg_scene_00001_.png')] }, (v) => v.ok === true && v.checks.big_side === true && v.sharpness > 20)

await call('turnaround 背景图应拒绝', { kind: 'turnaround', paths: [path.join(S, '08/bg_scene_00001_.png')] }, (v) => v.kind === 'turnaround' && typeof v.checks.three_panels === 'boolean')

// 桥接层错误也要能回来，不能抛
await call('不存在的文件', { kind: 'alpha', paths: [path.join(S, 'nope.png')] }, (v) => v.ok === false && typeof v.error === 'string')

await call('lineart 背景图应判为未上色', { kind: 'lineart', paths: [path.join(S, '08/bg_scene_00001_.png')] }, (v) => v.kind === 'lineart' && typeof v.checks.paper_low === 'boolean' && typeof v.sat_p90 === 'number')
await call('lineart 透明立绘应拒绝', { kind: 'lineart', paths: [path.join(S, '10/part_head_00010_.png')] }, (v) => v.ok === false && typeof v.hint === 'string')
await call('未知 kind 要列全 11 种', { kind: 'nonsense', paths: [path.join(S, '08/bg_scene_00001_.png')] }, (v) => v.ok === false && /turnaround/.test(v.error) && /upscale/.test(v.error) && /icon/.test(v.error) && /tile/.test(v.error))

if (failures.length) {
  console.log('\nFAILURES:', failures.join(', '))
  process.exit(1)
}
console.log('\nE2E VERIFY OK')
