/**
 * 路径解析：工作区、插件根、输出根。
 *
 * 这里刻意不 import 任何 `@deepseek-ai/*` 包：工具与技能注册表都以普通
 * service 的形式通过 `ctx.tools` / `ctx.skills` 消费，本 bundle 才能装进任意 profile。
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

/** 包根目录（package.json 所在处）。 */
export const BUNDLE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

/** Python 侧 `gameart_pipeline` 包根：与 lib/ 同级，'import gameart_pipeline' 的 sys.path 起点。 */
export const PY_PACKAGE_ROOT = BUNDLE_ROOT

/** 桥接脚本。 */
export const BRIDGE_SCRIPT = path.join(BUNDLE_ROOT, 'lib', 'bridge.py')

/** 内置技能目录。 */
export const SKILLS_ROOT = path.join(BUNDLE_ROOT, 'skills')

export function expandHome(input) {
  if (typeof input !== 'string' || input.length === 0) return input
  if (input === '~') return os.homedir()
  if (input.startsWith('~/') || input.startsWith('~\\')) return path.join(os.homedir(), input.slice(2))
  return input
}

function isFile(candidate) {
  try {
    return fs.statSync(candidate).isFile()
  } catch {
    return false
  }
}

/** 某个目录里是否装着 gameart_pipeline 包。 */
export function hasPipelinePackage(dir) {
  if (typeof dir !== 'string' || dir.length === 0) return false
  return isFile(path.join(dir, 'gameart_pipeline', 'runner.py'))
}

/**
 * 会话工作区：优先问 sandboxPolicy，问不到就退回进程 cwd。
 * 与 godotmaker 的 sessionWorkspace 同一思路 —— 任何一步失败都不抛，只降级。
 */
export function sessionWorkspace(ctx, exec) {
  try {
    const policy = ctx.sandboxPolicy
    if (policy && typeof policy.resolve === 'function') {
      const session = exec?.agent?.session
      const resolved = policy.resolve(session ? { session } : {})
      const root = resolved?.workspaceRoot
      if (typeof root === 'string' && root.length > 0) return root
    }
  } catch {
    /* 沙箱策略不可用时继续往下退 */
  }
  try {
    const wd = ctx.workingDirectory
    const cwd = typeof wd?.get === 'function' ? wd.get() : wd?.current
    if (typeof cwd === 'string' && cwd.length > 0) return cwd
  } catch {
    /* ignore */
  }
  return process.cwd()
}

/**
 * 解析「跑哪份产线包」。优先级：
 *   1. 调用参数里的 plugin_root / project_path（用户显式指定装了 gameart_pipeline 的目录）
 *   2. config.pluginRoot（profile 里配死的安装路径）
 *   3. 本 bundle 自带的 gameart_pipeline
 * 三条都会校验目录里确实有 gameart_pipeline/runner.py 才认。
 */
export function resolvePipelineRoot(ctx, exec, args, config = {}) {
  const explicit = expandHome(args?.plugin_root ?? args?.project_path)
  if (hasPipelinePackage(explicit)) return path.resolve(explicit)
  const configured = expandHome(config.pluginRoot)
  if (hasPipelinePackage(configured)) return path.resolve(configured)
  if (hasPipelinePackage(PY_PACKAGE_ROOT)) return PY_PACKAGE_ROOT
  return null
}

/**
 * build() 会往 COMFY_WF_DIR / COMFY_API_DIR 里写文件，而这两者的默认值在**包内**。
 * 装成 node_modules 下的 bundle 之后那里往往只读或会被覆盖，所以统一改投到工作区
 * 的 .gameart/ 下；用户在 config 里显式给了就用用户的。
 */
export function resolveOutputDirs(ctx, exec, config = {}) {
  const workspace = sessionWorkspace(ctx, exec)
  const stamp = (value, fallback) => {
    const picked = expandHome(value)
    return typeof picked === 'string' && picked.trim().length > 0 ? path.resolve(picked) : fallback
  }
  const fallbackWf = path.join(workspace, '.gameart', 'workflows')
  const fallbackApi = path.join(workspace, '.gameart', 'api')
  return {
    workspace,
    workflowDir: stamp(config.workflowDir, fallbackWf),
    apiDir: stamp(config.apiDir, fallbackApi),
    outputDir: stamp(config.outputDir, path.join(workspace, '.gameart', 'output')),
  }
}
