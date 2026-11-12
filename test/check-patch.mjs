/**
 * 校验 cordis.patch.yml 的结构。
 *
 * 单独写成文件而不是 `node -e`：这个包的 package.json 是 `type: module`，
 * `node -e` 里的 `require` 会静默失败（无输出、exit 0），查不出问题。
 */
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)

// yaml 由 DSH 自带的 profile 依赖提供，不同机器路径不同，不能写死。
// 依次尝试：本包 node_modules -> DSH_HOME/profile -> 全局 require。
function loadYaml() {
  const candidates = []
  const dshHome = process.env.DSH_HOME || path.join(os.homedir(), '.dsh')
  const bundles = [
    'yaml/dist/index.js',
    'yaml',
  ]
  for (const name of bundles) {
    candidates.push(name)
    candidates.push(path.join(dshHome, 'profiles', 'desktop', 'node_modules', name))
    candidates.push(path.join(dshHome, 'profiles', 'web', 'node_modules', name))
  }
  for (const candidate of candidates) {
    try {
      return require(candidate)
    } catch {
      // 继续试下一个
    }
  }
  return null
}

const yaml = loadYaml()
if (!yaml) {
  console.log('SKIP: 找不到 yaml 模块，跳过 YAML 结构校验（可 pnpm add -D yaml 后重试）')
  process.exit(0)
}

const text = fs.readFileSync(new URL('../cordis.patch.yml', import.meta.url), 'utf8')
const doc = yaml.parseDocument(text)

if (doc.errors.length) {
  console.log('PARSE ERRORS:')
  for (const error of doc.errors) console.log('  ', error.message)
  process.exit(1)
}

const rows = doc.toJS()
console.log('顶层行数:', rows.length)

let failures = []
const seen = new Set()

for (const row of rows) {
  if (!row.insert) {
    failures.push(`顶层行既不是 insert 也不是覆盖：${JSON.stringify(Object.keys(row))}`)
    continue
  }
  for (const entry of row.insert) {
    if (!entry.id) {
      failures.push('insert 里有行缺 id')
      continue
    }
    if (seen.has(entry.id)) failures.push(`行 id 重复: ${entry.id}`)
    seen.add(entry.id)

    const config = entry.config || {}
    const plugins = Array.isArray(config.plugins) ? config.plugins : []
    console.log(
      `- ${entry.id}  name=${entry.name}  preset=${config.id}  order=${config.order}  行数=${plugins.length}`,
    )

    // preset 必须有 id / plugins
    if (!config.id) failures.push(`${entry.id}: 缺 config.id`)
    if (!/^[a-z0-9-]+$/.test(config.id || '')) {
      failures.push(`${entry.id}: config.id 只能小写字母数字连字符，实为 ${config.id}`)
    }
    if (!plugins.length) failures.push(`${entry.id}: plugins 为空`)
    if (entry.id !== `preset-${config.id}`) {
      failures.push(`${entry.id}: 行 id 应为 preset-${config.id}`)
    }

    // 插件行 id 不能重复
    const innerIds = new Set()
    for (const plugin of plugins) {
      if (!plugin.id) failures.push(`${entry.id}: 有插件行缺 id`)
      if (innerIds.has(plugin.id)) failures.push(`${entry.id}: 插件行 id 重复 ${plugin.id}`)
      innerIds.add(plugin.id)
      if (!plugin.name) failures.push(`${entry.id}/${plugin.id}: 缺 name`)
    }

    // skill-filesystem 必须排在 gameart 之前
    const order = plugins.map((p) => p.id)
    const iSkill = order.indexOf('skill-filesystem')
    const iGameart = order.indexOf('gameart')
    if (iGameart !== -1 && iSkill === -1) {
      failures.push(`${entry.id}: 有 gameart 却没有 skill-filesystem`)
    }
    if (iGameart !== -1 && iSkill !== -1 && iSkill > iGameart) {
      failures.push(`${entry.id}: gameart 必须排在 skill-filesystem 之后`)
    }
    if (iGameart === -1) failures.push(`${entry.id}: 没有挂 gameart 插件行`)

    // 委派工具名不许撞内置工具
    for (const plugin of plugins) {
      if (plugin.name === '@deepseek-ai/dsh-tool-subagent' && plugin.config?.toolName) {
        const banned = ['read', 'write', 'edit', 'glob', 'grep']
        if (banned.includes(plugin.config.toolName)) {
          failures.push(`${entry.id}: 委派工具名 ${plugin.config.toolName} 撞内置工具`)
        }
      }
    }

    // persona 里不准出现没替换的占位
    const persona = plugins.find((p) => p.id === 'persona')
    if (persona?.config?.prefix) {
      if (!persona.config.prefix.includes('{{model}}')) {
        failures.push(`${entry.id}: persona 缺 {{model}}`)
      }
      if (persona.config.prefix.includes('{{') && !persona.config.prefix.includes('{{model}}')) {
        failures.push(`${entry.id}: persona 有未知占位符`)
      }
    } else {
      failures.push(`${entry.id}: 缺 persona 行`)
    }
  }
}

// 三个预设之间的委派引用必须都落地
const presets = new Set(rows.flatMap((r) => (r.insert || []).map((e) => e.config?.id).filter(Boolean)))
for (const row of rows) {
  for (const entry of row.insert || []) {
    for (const plugin of entry.config?.plugins || []) {
      const target = plugin.config?.agentPreset
      if (target && !presets.has(target)) {
        failures.push(`${entry.id}: 委派引用了不存在的预设 ${target}`)
      }
    }
  }
}
console.log('\n预设 id:', [...presets].join(', '))

if (failures.length) {
  console.log('\nFAILURES:')
  for (const failure of failures) console.log('  -', failure)
  process.exit(1)
}
console.log('\nPATCH STRUCTURE OK')
