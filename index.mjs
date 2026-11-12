/**
 * dsh-gameart —— 游戏美术产线组（ComfyUI / SD1.5 + SDXL 两代）的 DSH 工具层。
 *
 * 设计约束和 godotmaker / sand3d 一致：**不 import 任何 `@deepseek-ai/*` 包**。
 * 工具与技能注册表都以普通 service 的形式通过 `ctx.tools` / `ctx.skills` 消费，
 * 这样本 bundle 装进任意 profile 都不会因为包版本对不上而挂掉。
 *
 * 工具和技能只在装载它的 preset 里可见（本 bundle 的 patch 只插预设行，
 * 不插 host 行），所以装了本包不会给无关会话加任何工具。
 */
import path from 'node:path'
import fs from 'node:fs'

import {
  SKILLS_ROOT,
  resolveOutputDirs,
  resolvePipelineRoot,
} from './lib/fs-utils.mjs'
import { createJobRegistry } from './lib/jobs.mjs'
import { resolvePython, runBridge } from './lib/python.mjs'

export const name = 'gameart'

/** 只硬依赖工具注册表；subprocess / skills 走可选获取，缺了就给出可读的原因。 */
export const inject = ['tools']

const jsonOutput = {
  schema: { type: 'object', additionalProperties: true },
  render(_args, value) {
    return { type: 'text', text: JSON.stringify(value, null, 2) }
  },
}

/* ------------------------------------------------------------------ 技能 */

/** 拆 SKILL.md 的 `---` frontmatter 与正文。 */
export function parseSkillFile(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text)
  if (!match) return { meta: {}, content: text.trim() }
  const body = text.slice(match[0].length).trim()
  const meta = {}
  const lines = match[1].split(/\r?\n/)
  let key = null
  let buffer = []
  const flush = () => {
    if (key === null) return
    meta[key] = buffer.join('\n').trim()
    key = null
    buffer = []
  }
  for (const line of lines) {
    const field = /^([A-Za-z0-9_-]+):\s*(.*)$/.exec(line)
    if (field && !/^\s/.test(line)) {
      flush()
      const [, name, rest] = field
      if (rest === '|' || rest === '>' || rest === '|-') {
        key = name
        buffer = []
      } else {
        meta[name] = rest.trim()
      }
      continue
    }
    if (key !== null) buffer.push(line.replace(/^\s+/, ''))
  }
  flush()
  return { meta, content: body }
}

function loadSkillDefinitions(groups) {
  const definitions = []
  if (!fs.existsSync(SKILLS_ROOT)) return definitions
  for (const entry of fs.readdirSync(SKILLS_ROOT, { withFileTypes: true })) {
    if (!entry.isDirectory()) continue
    const group = entry.name
    if (Array.isArray(groups) && groups.length > 0 && !groups.includes(group)) continue
    const dir = path.join(SKILLS_ROOT, group)
    const dirs = fs
      .readdirSync(dir, { withFileTypes: true })
      .filter((child) => child.isDirectory())
      .map((child) => path.join(dir, child.name))
    // 也允许 skills/<group>/<name>.md 这种平铺写法
    for (const file of fs.readdirSync(dir, { withFileTypes: true })) {
      if (file.isFile() && file.name.toLowerCase().endsWith('.md') && file.name !== 'README.md') {
        dirs.push(file.name)
      }
    }
    for (const item of dirs) {
      const abs = path.isAbsolute(item) ? item : path.join(dir, item)
      const skillFile = abs.endsWith('.md') ? abs : path.join(abs, 'SKILL.md')
      if (!fs.existsSync(skillFile)) continue
      const raw = fs.readFileSync(skillFile, 'utf8')
      const { meta, content } = parseSkillFile(raw)
      const skillName = (meta.name || '').trim()
      if (!skillName) continue
      // 只有人工显式标注的才从模型菜单里拿掉；默认两边都能用。
      const operatorOnly =
        /^\s*model-invocable:\s*false\s*$/m.test(raw) ||
        /^\s*disable-model-invocation:\s*true\s*$/m.test(raw)
      definitions.push({
        name: skillName,
        description: (meta.description || '').trim() || skillName,
        content,
        ...((meta.whenToUse || meta['when-to-use'] || '').trim()
          ? { whenToUse: (meta.whenToUse || meta['when-to-use']).trim() }
          : {}),
        invocation: { modelInvocable: !operatorOnly, userInvocable: true },
        source: 'bundled',
        provider: 'dsh-gameart',
        path: skillFile,
        group,
      })
    }
  }
  return definitions
}

/* ------------------------------------------------------------------ 工具 */

/** 每个工具的公共前置：解析 pipeline root / python / 输出目录。 */
function makeContext(ctx, config, exec) {
  const subprocess = typeof ctx.get === 'function' ? ctx.get('subprocess') : ctx.subprocess
  return {
    subprocess,
    pipelineRoot: resolvePipelineRoot(ctx, exec, {}, config),
    dirs: resolveOutputDirs(ctx, exec, config),
  }
}

function missingSubprocess() {
  return {
    ok: false,
    error:
      'subprocess 服务在本会话不可用，无法调用 Python 产线。请确认本预设的 composition 里有可用的 subprocess provider。',
  }
}

function missingRoot() {
  return {
    ok: false,
    error:
      '找不到 gameart_pipeline 包。把它装到 workspace（或在插件配置里设 pluginRoot，或调用时给 plugin_root 参数），目录下需要有 gameart_pipeline/runner.py。',
  }
}

/** 通用执行壳：前置检查 → resolvePython → runBridge。 */
async function call(ctx, config, exec, command, args, options = {}) {
  const { subprocess, pipelineRoot, dirs } = makeContext(ctx, config, exec)
  if (!subprocess) return missingSubprocess()
  if (!pipelineRoot) return missingRoot()
  const python = await resolvePython(subprocess, config.pythonPath)
  if (!python.ok) return { ok: false, error: python.error, missing: python.missing }
  return runBridge(subprocess, {
    python: python.python,
    pipelineRoot,
    command,
    args,
    outputEnv: {
      COMFY_WF_DIR: dirs.workflowDir,
      COMFY_API_DIR: dirs.apiDir,
      ...(config.comfyBase ? { COMFY_BASE: config.comfyBase } : {}),
    },
    timeoutMs: options.timeoutMs ?? config.timeoutMs ?? 120000,
    signal: exec?.signal,
  })
}

/** 把产线 run 结果整理成「下一步该干什么」也看得懂的形状。 */
function summarizeRun(pipelineId, overrides, result) {
  if (!result.ok) {
    const stage = result.stage || 'unknown'
    const hints = {
      validate: '图本身没过校验，多半是 object_info 快照跟当前 ComfyUI 版本对不上：先跑 gameart_status 核对在线版本，再 gameart_build 看 node 数。',
      submit: 'ComfyUI 拒收了 prompt。常见原因：模型名不对（ckpt_name）、缺 custom_nodes、显存不足。',
      exec: 'ComfyUI 执行报错。看 error 里的 node_errors，通常是某条 custom_node 没装或输入类型不匹配。',
      timeout: '轮询超时。ComfyUI 可能还在跑：先 gameart_status 看队列，别急着重提。',
      bridge: '桥接层没拿到结果，看 stderr。',
    }
    return {
      ok: false,
      stage,
      error: result.error,
      hint: hints[stage] || '看 error 与 stderr 定位。',
      ...(result.applied_overrides ? { applied_overrides: result.applied_overrides } : {}),
    }
  }
  const images = Array.isArray(result.images) ? result.images : []
  return {
    ok: true,
    pipeline: pipelineId,
    elapsed: result.elapsed,
    applied_overrides: result.applied_overrides ?? [],
    requested_overrides: overrides,
    unapplied_overrides: Object.keys(overrides).filter(
      (key) => !(result.applied_overrides ?? []).includes(key),
    ),
    images: images.map((item) =>
      typeof item === 'string'
        ? item
        : {
            filename: item.filename,
            subfolder: item.subfolder,
            type: item.type,
            // ComfyUI 的 output/ 目录在插件目录之外，这里只给出相对路径，
            // 让调用方自己拼 COMFY_OUTPUT_ROOT（preset 里写进了技能文档）。
            relative: [item.subfolder, item.filename].filter(Boolean).join('/'),
          },
    ),
    count: images.length,
  }
}

export function apply(ctx, config = {}) {
  const registerTools = config.registerTools !== false
  const skillsEnabled = config.registerSkills !== false
  const skillGroups = Array.isArray(config.skills) ? config.skills : null
  // 插件实例级：整个 profile 共用一份任务表，重连/换会话都还能查到
  const jobs = createJobRegistry(40)

  if (registerTools) {
    /* --- 产线清单 --------------------------------------------------- */
    ctx.effect(
      () =>
        ctx.tools.register({
          name: 'gameart_list',
          description:
            '列出可用的美术产线（08 场景背景 / 09 UI 九宫格 / 10 角色部件分层 / 11 光效粒子），含每条产线的用途、输出规格与可覆盖参数。接手美术任务、或不确定该用哪条产线时先调它。不访问 ComfyUI。',
          parameters: { type: 'object', properties: {}, additionalProperties: false },
          output: jsonOutput,
          async execute(args, exec) {
            const result = await call(ctx, config, exec, 'list', [], { timeoutMs: 60000 })
            if (!result.ok) return result
            return { ok: true, pipelines: result.data?.pipelines ?? [] }
          },
        }),
      'gameart: list pipelines',
    )

    /* --- 环境自检 --------------------------------------------------- */
    ctx.effect(
      () =>
        ctx.tools.register({
          name: 'gameart_status',
          description:
            '检查 ComfyUI 是否在线、版本/显卡/显存、节点 schema 数量、两代底模（SD1.5 anything-v5-PrtRE 与 SDXL animagine-xl-3.1）是否就位，并列出 12 条产线。任何产线任务开工前先跑这一条：online=false 说明 ComfyUI 没起来；ckpt_ready=false 说明底模名对不上，跑了也会失败。',
          parameters: {
            type: 'object',
            properties: {
              plugin_root: {
                type: 'string',
                description: '装了 gameart_pipeline 的目录；不写就用插件自带的。',
              },
            },
            additionalProperties: false,
          },
          output: jsonOutput,
          async execute(args, exec) {
            const { subprocess, pipelineRoot, dirs } = makeContext(ctx, config, exec)
            if (!subprocess) return missingSubprocess()
            if (!pipelineRoot) return missingRoot()
            const python = await resolvePython(subprocess, config.pythonPath)
            if (!python.ok) return { ok: false, error: python.error, missing: python.missing }
            const result = await runBridge(subprocess, {
              python: python.python,
              pipelineRoot,
              command: 'info',
              outputEnv: {
                COMFY_WF_DIR: dirs.workflowDir,
                COMFY_API_DIR: dirs.apiDir,
                ...(config.comfyBase ? { COMFY_BASE: config.comfyBase } : {}),
              },
              timeoutMs: 60000,
              signal: exec?.signal,
            })
            if (!result.ok) return result
            const data = result.data ?? {}
            return {
              ...data,
              workflow_dir: dirs.workflowDir,
              api_dir: dirs.apiDir,
              workspace: dirs.workspace,
              pipeline_root: pipelineRoot,
              ready: data.online === true && data.ckpt_ready === true,
              hint:
                data.online !== true
                  ? 'ComfyUI 没在监听。让用户启动 ComfyUI（绘世启动器 / main.py），确认端口 8188 再重试；ComfyUI 不在本机或不在默认端口时，用环境变量 COMFY_BASE 指定，例如 COMFY_BASE=http://192.168.1.10:8188。'
                  : data.ckpt_ready !== true
                    ? (data.ckpt_sdxl_ready === false && data.ckpt_sd15_ready === false
                        ? '两代底模都缺：SDXL animagine-xl-3.1.safetensors（08/09/11）与 SD1.5 anything-v5-PrtRE.safetensors（00~07）。补装模型，不要改代码。'
                        : data.ckpt_sdxl_ready === false
                          ? '缺 SDXL 底模 animagine-xl-3.1.safetensors，08/09/11 跑不了（00~07 不受影响）。补装模型，不要改代码里的 CKPT。'
                          : '缺 SD1.5 底模 anything-v5-PrtRE.safetensors，00~07 跑不了（08/09/11 不受影响）。补装模型，不要改代码里的 CKPT_SD15。')
                    : '环境就绪。',
            }
          },
        }),
      'gameart: comfyui status',
    )

    /* --- 构建工作流 JSON -------------------------------------------- */
    ctx.effect(
      () =>
        ctx.tools.register({
          name: 'gameart_build',
          description:
            '把产线重建为 ComfyUI 工作流 JSON（UI 版 + API 版）并做本地校验，写到工作区的 .gameart/workflows 与 .gameart/api。改了 pipelines.py、或想确认图与当前 ComfyUI 版本是否对得上时用它；返回每条产线的节点数与错误。不提交执行。',
          parameters: {
            type: 'object',
            properties: {
              ids: {
                type: 'array',
                items: { type: 'string', enum: ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11'] },
                description: '只构建这几条；不写就全部 12 条都构。',
              },
            },
            additionalProperties: false,
          },
          output: jsonOutput,
          async execute(args, exec) {
            const ids = Array.isArray(args?.ids) ? args.ids : []
            const result = await call(ctx, config, exec, 'build', ids, { timeoutMs: 120000 })
            if (!result.ok) return result
            const data = result.data ?? {}
            const failed = Object.entries(data).filter(([, value]) => value?.ok === false)
            return {
              ok: failed.length === 0,
              pipelines: data,
              failed: failed.map(([id]) => id),
              hint:
                failed.length === 0
                  ? '全部通过。JSON 可以直接拖进 ComfyUI 界面看结构。'
                  : '有产线没通过校验，errors 里是逐节点原因；多为 object_info 快照与当前 ComfyUI 不一致。',
            }
          },
        }),
      'gameart: build workflows',
    )

    /* --- 跑产线（后台任务） ------------------------------------------ */
    ctx.effect(
      () =>
        ctx.tools.register({
          name: 'gameart_run',
          description:
            '提交一条美术产线到 ComfyUI，立刻返回 job id，出图在后台跑（08 约 1-2 分钟，09/10 最久 3-5 分钟）。之后用 gameart_jobs 查进度和结果。想在同一次调用里等结果就传 wait=true。prompt 写英文 Danbooru 标签；不传就用产线内置默认构图。',
          parameters: {
            type: 'object',
            properties: {
              pipeline_id: {
                type: 'string',
                enum: ['00', '01', '02', '03', '04', '05', '06', '07', '08', '09', '10', '11'],
                description:
                  '00=角色概念 01=立绘透明底 02=表情差分 03=线稿上色 04=三视图 05=道具图标 06=无缝贴图 07=高清放大 08=场景背景 09=UI九宫格 10=角色部件分层 11=光效粒子',
              },
              prompt: {
                type: 'string',
                description:
                  '正向提示词，英文 Danbooru 标签风格，逗号分隔。08 必须无人物（no humans）。',
              },
              negative: {
                type: 'string',
                description:
                  '负向提示词。不写就用产线内置的 NEG（08 还额外排除 humans/person/text/logo/ui/frame/border 等）。',
              },
              seed: { type: 'integer', description: '随机种子；同 seed 同参数可复现。' },
              steps: { type: 'integer', description: '采样步数，默认 28。' },
              cfg: { type: 'number', description: 'CFG，默认 7.0。' },
              width: { type: 'integer', description: '仅 08 有效，默认 1344（再放大到 1920）。' },
              height: { type: 'integer', description: '仅 08 有效，默认 768（再放大到 1080）。' },
              batch_size: { type: 'integer', description: '出图张数；11 默认 12。' },
              sampler_name: { type: 'string', description: '默认 dpmpp_2m。' },
              scheduler: { type: 'string', description: '默认 karras。' },
              timeout: {
                type: 'number',
                description: '轮询超时秒数，默认 560。小于 60 会被忽略。别为了「快点」调小。',
              },
              wait: {
                type: 'boolean',
                description: 'true = 阻塞等到出图再返回（仍然受 timeout 约束）。默认 false。',
              },
              plugin_root: {
                type: 'string',
                description: '装了 gameart_pipeline 的目录；不写就用插件自带的。',
              },
            },
            required: ['pipeline_id'],
            additionalProperties: false,
          },
          output: jsonOutput,
          async execute(args, exec) {
            const { pipeline_id: pipelineId, timeout, wait, plugin_root: pluginRoot, ...rest } =
              args ?? {}
            const overrides = {}
            for (const [key, value] of Object.entries(rest)) {
              if (value !== undefined && value !== null && value !== '') overrides[key] = value
            }
            const seconds = Number.isFinite(timeout) && timeout >= 60 ? timeout : 560
            const settings = { ...config, ...(pluginRoot ? { pluginRoot } : {}) }

            const runner = async (signal) => {
              const { subprocess, pipelineRoot, dirs } = makeContext(ctx, settings, exec)
              if (!subprocess) return missingSubprocess()
              if (!pipelineRoot) return missingRoot()
              const python = await resolvePython(subprocess, config.pythonPath)
              if (!python.ok) return { ok: false, error: python.error, missing: python.missing }
              const result = await runBridge(subprocess, {
                python: python.python,
                pipelineRoot,
                command: 'run',
                args: [pipelineId, JSON.stringify(overrides), String(seconds)],
                outputEnv: {
                  COMFY_WF_DIR: dirs.workflowDir,
                  COMFY_API_DIR: dirs.apiDir,
                  ...(config.comfyBase ? { COMFY_BASE: config.comfyBase } : {}),
                },
                // 子进程要比 Python 侧的轮询窗口更宽，才能拿到它自己的 timeout 结论
                timeoutMs: Math.round((seconds + 60) * 1000),
                signal,
              })
              if (!result.ok) return summarizeRun(pipelineId, overrides, result)
              return summarizeRun(pipelineId, overrides, { ok: true, ...result.data })
            }

            const label = `产线 ${pipelineId}${overrides.seed != null ? ` · seed ${overrides.seed}` : ''}`
            const job = jobs.start('run', label, (_job, onProgress) => {
              onProgress(`ComfyUI 执行中（${label}）`)
              return runner(_job.controller.signal)
            })

            if (wait !== true) {
              return {
                ok: true,
                job_id: job.id,
                status: job.status,
                label,
                pipeline: pipelineId,
                requested_overrides: overrides,
                hint: '任务已在后台跑。用 gameart_jobs {job_id} 查进度；同一时间不要重复提交同一条产线。',
              }
            }

            // wait=true：阻塞到这条 job 结束（有上限，避免调用方被永久挂住）
            const deadline = Date.now() + Math.round((seconds + 90) * 1000)
            while (Date.now() < deadline) {
              const current = jobs.get(job.id)
              if (current && current.status !== 'running') return current
              await new Promise((resolve) => setTimeout(resolve, 1000))
            }
            return {
              ok: false,
              job_id: job.id,
              error: '等待超时，任务可能还在跑。用 gameart_jobs 再查。',
            }
          },
        }),
      'gameart: run pipeline',
    )

    /* --- 任务查询 / 取消 --------------------------------------------- */
    ctx.effect(
      () =>
        ctx.tools.register({
          name: 'gameart_jobs',
          description:
            '查 gameart_run 提交的后台任务：不传 job_id 列出全部，传 job_id 看单条（含出图路径）。cancel=true 取消还在跑的任务。',
          parameters: {
            type: 'object',
            properties: {
              job_id: { type: 'string', description: '任务 id（gameart_run 返回的 job_id）。' },
              cancel: { type: 'boolean', description: 'true = 取消这个任务。' },
            },
            additionalProperties: false,
          },
          output: jsonOutput,
          async execute(args) {
            const jobId = typeof args?.job_id === 'string' ? args.job_id.trim() : ''
            if (args?.cancel === true) {
              if (!jobId) return { ok: false, error: 'cancel 需要同时给 job_id' }
              return jobs.cancel(jobId)
            }
            if (jobId) {
              const job = jobs.get(jobId)
              if (!job) return { ok: false, error: `没有这个任务：${jobId}` }
              return { ok: true, job, running: jobs.running() }
            }
            return { ok: true, jobs: jobs.list(), running: jobs.running() }
          },
        }),
      'gameart: job status',
    )

    /* --- 九宫格切图 -------------------------------------------------- */
    ctx.effect(
      () =>
        ctx.tools.register({
          name: 'gameart_slice9',
          description:
            '把 09 产线出的 UI 面板切成九宫格（tl/tc/tr/ml/mc/mr/bl/bc/br 九张），中间块用面板中心实测的单一纯色重建，避免把四角圆角拉伸糊掉。输入是 RGBA 面板 PNG；先按 alpha 包围盒裁边再切。',
          parameters: {
            type: 'object',
            properties: {
              src: { type: 'string', description: '面板 PNG 的绝对路径。' },
              out_dir: {
                type: 'string',
                description: '切块输出目录；不写就在源文件同级建 nineslice/。',
              },
              corner: {
                type: 'integer',
                description: '九宫格角块边长（像素），默认 160。会被夹到 [16, min(w,h)/4]。',
              },
            },
            required: ['src'],
            additionalProperties: false,
          },
          output: jsonOutput,
          async execute(args, exec) {
            const src = typeof args?.src === 'string' ? args.src : ''
            if (!src) return { ok: false, error: '需要 src（面板 PNG 的绝对路径）' }
            const outDir = typeof args?.out_dir === 'string' && args.out_dir ? args.out_dir : '-'
            const corner = Number.isFinite(args?.corner) ? String(Math.round(args.corner)) : '160'
            const result = await call(ctx, config, exec, 'slice', [src, outDir, corner], {
              timeoutMs: 60000,
            })
            if (!result.ok) return result
            const data = result.data ?? {}
            return {
              ...data,
              hint: 'center_rgb 是重建中间块用的纯色；面板有渐变/纹理时要把它改成贴图的平铺方案，别直接拉伸。',
            }
          },
        }),
      'gameart: slice nine-patch',
    )

    /* --- 出图验收 ---------------------------------------------------- */
    ctx.effect(
      () =>
        ctx.tools.register({
          name: 'gameart_verify',
          description:
            '用 numpy 量一张产线出图的结构性指标并给出判定，别靠肉眼看。kind 十一种：parts（10 的头/身两层，必须像素级零重叠、透明区 RGB 全 0）、mc（09 切好的中间块，必须单色不透明）、panel（09 原始面板，四角四边有内容、中间不透明）、fx（11 光效，区分 sprite 与满屏闪光，并检查透明区够暗以免加色叠加烧白）、flat（08 背景，尺寸与是否带 alpha）、alpha（通用 RGBA 体检）、icon（05 道具图标，正方形、背景全透、主体居中且线性占比 45%~98%、透明区 RGB 全 0）、tile（06 无缝贴图，环绕处跳变不得超过图内任意相邻跳变，比值 ≤1.2）、upscale（07 放大图，尺寸够大且拉普拉斯方差证明有真实细节，不是放大了但糊）、turnaround（04 三视图，横版且左中右三段都有主体）、lineart（03 线稿上色，近白纸占比 ≤35% 且彩度 p90 ≥0.12，证明真上了色而不是出了张灰度图）。返回的 checks 里逐条写明哪一项没过。出图后、交付前必须跑一次。',
          parameters: {
            type: 'object',
            properties: {
              kind: {
                type: 'string',
                enum: [
                  'parts',
                  'mc',
                  'panel',
                  'fx',
                  'flat',
                  'alpha',
                  'icon',
                  'tile',
                  'upscale',
                  'turnaround',
                  'lineart',
                ],
                description:
                  '验收类型，和产线对应：10→parts，09→panel+mc，11→fx，08→flat，05→icon，06→tile，07→upscale，04→turnaround，03→lineart。',
              },
              paths: {
                type: 'array',
                items: { type: 'string' },
                description:
                  '图片绝对路径。parts 必须按 [head, body] 顺序给两张；其余给一张。',
              },
              corner: {
                type: 'integer',
                description: 'panel 的角块边长，和切图时用的一致，默认 160。',
              },
            },
            required: ['kind', 'paths'],
            additionalProperties: false,
          },
          output: jsonOutput,
          async execute(args, exec) {
            const kind = typeof args?.kind === 'string' ? args.kind : ''
            if (!kind) return { ok: false, error: '需要 kind' }
            const paths = Array.isArray(args?.paths)
              ? args.paths.filter((item) => typeof item === 'string' && item)
              : []
            if (!paths.length) return { ok: false, error: '需要 paths（图片绝对路径）' }
            const argv = [kind, ...paths]
            if (Number.isFinite(args?.corner)) argv.push(String(Math.round(args.corner)))
            const result = await call(ctx, config, exec, 'verify', argv, { timeoutMs: 120000 })
            if (!result.ok) return result
            const data = result.data ?? {}
            return {
              ...data,
              hint:
                data.ok === true
                  ? '结构性验收通过。接着用 read_image 看一眼构图和风格（这一步只判结构，不判好不好看）。'
                  : '有 checks 没过：按返回里标 false 的那一项去改，不要直接交付。',
            }
          },
        }),
      'gameart: verify output',
    )
  }

  /* --- 技能注册 ----------------------------------------------------- */
  if (!skillsEnabled) return

  const skills = typeof ctx.get === 'function' ? ctx.get('skills') : ctx.skills
  if (!skills || typeof skills.register !== 'function') {
    ctx.logger?.warn?.(
      'skills 服务不可用，跳过技能注册。让本插件排在 skill-filesystem 之后（预设里已有该行）。',
    )
    return
  }

  let definitions = []
  try {
    definitions = loadSkillDefinitions(skillGroups)
  } catch (error) {
    ctx.logger?.warn?.(`读取技能目录失败：${error.message}`)
    return
  }

  for (const definition of definitions) {
    ctx.effect(
      () =>
        skills.register({
          name: definition.name,
          description: definition.description,
          content: definition.content,
          whenToUse: definition.whenToUse,
          invocation: definition.invocation,
          source: definition.source,
          provider: definition.provider,
          resourceBase: { kind: 'directory', path: path.dirname(definition.path) },
        }),
      `gameart: skill ${definition.name}`,
    )
  }
}
