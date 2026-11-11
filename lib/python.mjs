/**
 * Python 桥接：解析解释器 → spawn bridge.py → 读回最后一行 `__GAMEART_JSON__{…}`。
 *
 * 为什么走独立进程而不是 shell 拼串：
 *   run() 最慢要几分钟且会一直轮询 ComfyUI，放进子进程里既能被 timeout 掐掉，
 *   又不会把 host 事件循环卡住；argv 直传也省掉引号 / 中文 / JSON 的转义问题。
 */
import { BRIDGE_SCRIPT } from './fs-utils.mjs'

const MARKER = '__GAMEART_JSON__'
const COLLECT_BYTES = 4 * 1024 * 1024

/** 候选解释器：显式环境变量优先，其次平台惯例。 */
export function pythonCandidates() {
  const fromEnv = [process.env.GAMEART_PYTHON, process.env.PYTHON, process.env.PYTHON3]
    .filter((item) => typeof item === 'string' && item.trim().length > 0)
  const platform = process.platform === 'win32' ? ['python', 'py', 'python3'] : ['python3', 'python']
  return [...new Set([...fromEnv, ...platform])]
}

export async function resolvePython(subprocess, configured) {
  const explicit = typeof configured === 'string' && configured.trim().length > 0 ? configured.trim() : null
  const candidates = explicit ? [explicit] : pythonCandidates()
  const missing = []
  for (const candidate of candidates) {
    try {
      if (typeof subprocess.resolveExecutable === 'function') {
        const resolved = await subprocess.resolveExecutable(candidate)
        if (typeof resolved === 'string' && resolved.length > 0) return { ok: true, python: resolved }
      }
      return { ok: true, python: candidate }
    } catch {
      missing.push(candidate)
    }
  }
  return {
    ok: false,
    missing,
    error: `找不到可用的 Python 解释器（试过 ${missing.join(', ')}）。用 GAMEART_PYTHON 环境变量，或在本插件配置里设 pythonPath。`,
  }
}

function readCollected(stream) {
  try {
    const chunk = stream?.readFrom?.(0)
    return typeof chunk?.text === 'string' ? chunk.text : ''
  } catch {
    return ''
  }
}

/** 从 stdout 里取最后一条带 marker 的 JSON。 */
export function parseBridgeOutput(stdout) {
  const lines = stdout.split(/\r?\n/)
  for (let index = lines.length - 1; index >= 0; index -= 1) {
    const line = lines[index]
    const at = line.indexOf(MARKER)
    if (at === -1) continue
    const body = line.slice(at + MARKER.length).trim()
    if (body.length === 0) continue
    try {
      return { ok: true, value: JSON.parse(body) }
    } catch (error) {
      return { ok: false, error: `桥接输出不是合法 JSON：${error.message}`, raw: body.slice(0, 2000) }
    }
  }
  return null
}

/**
 * 跑一次桥接。永不抛：任何失败都折成 { ok: false, ... } 让工具层决定怎么呈现。
 *
 * @param {object} subprocess ctx.subprocess
 * @param {object} options { python, pipelineRoot, command, args, outputEnv, timeoutMs, signal }
 */
export async function runBridge(subprocess, options) {
  const { python, pipelineRoot, command, args = [], outputEnv = {}, timeoutMs = 120000, signal } = options

  const env = {
    ...process.env,
    PYTHONUTF8: '1',
    PYTHONIOENCODING: 'utf-8',
    PYTHONPATH: pipelineRoot,
    ...outputEnv,
  }

  let handle
  try {
    handle = subprocess.spawn({
      argv: [python, '-X', 'utf8', '-W', 'ignore::RuntimeWarning', BRIDGE_SCRIPT, command, ...args],
      cwd: pipelineRoot,
      stdio: {
        stdin: 'ignore',
        stdout: { collect: { maxBytes: COLLECT_BYTES } },
        stderr: { collect: { maxBytes: COLLECT_BYTES } },
      },
      env,
      graceMs: 3000,
      signal,
    })
  } catch (error) {
    return { ok: false, error: `spawn 失败：${error.message}` }
  }

  // 合同要求 spawn 同步返回 handle。provider 若给回 Promise，后面读 collected
  // 只会拿到 undefined，最后表现为「桥接没有输出结果」这种查不出来的错。
  if (!handle || typeof handle.then === 'function' || !handle.done) {
    return {
      ok: false,
      stage: 'bridge',
      error: 'subprocess.spawn 没有同步返回 handle（拿到的是 Promise 或空值）。这是 provider 违反约定，不是 Python 侧的问题。',
    }
  }

  let timedOut = false
  const timer = setTimeout(() => {
    timedOut = true
    try {
      handle.terminate()
    } catch {
      /* 已经退出 */
    }
  }, Math.max(5000, timeoutMs))

  let outcome
  try {
    outcome = await handle.done
  } catch (error) {
    clearTimeout(timer)
    return { ok: false, error: `子进程异常：${error.message}` }
  }
  clearTimeout(timer)

  const stdout = readCollected(handle.collected?.stdout)
  const stderr = readCollected(handle.collected?.stderr)
  const parsed = parseBridgeOutput(stdout)

  if (timedOut) {
    return {
      ok: false,
      stage: 'timeout',
      error: `超过 ${Math.round(timeoutMs / 1000)} 秒仍未返回，已终止。产线可能还在 ComfyUI 队列里跑，先用 gameart_status 看队列。`,
      stdout: stdout.slice(-2000),
      stderr: stderr.slice(-2000),
    }
  }

  if (parsed === null) {
    return {
      ok: false,
      stage: 'bridge',
      error: '桥接脚本没有输出结果。多半是 Python 侧 import 失败（缺 numpy/Pillow，或 pipeline_root 指错）。',
      exitCode: outcome?.exitCode ?? null,
      stdout: stdout.slice(-3000),
      stderr: stderr.slice(-3000),
    }
  }

  if (parsed.ok === false) {
    return { ok: false, stage: 'bridge', ...parsed, stderr: stderr.slice(-2000) }
  }

  const value = parsed.value
  if (value && value.ok === false) {
    return { ...value, stderr: stderr.trim() ? stderr.slice(-2000) : undefined }
  }
  if (value && value.ok === true && 'data' in value) {
    return { ok: true, data: value.data, stderr: stderr.trim() ? stderr.slice(-2000) : undefined }
  }
  return { ok: true, data: value }
}
