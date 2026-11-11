/**
 * 冒烟测试：确认 index.mjs 能被干净导入，没有 @deepseek-ai 依赖。
 *
 * 必须写成文件跑。这个包是 `type: module`，`node -e` 里做动态 import
 * 会静默无输出（exit 0），查不出问题。
 */
const mod = await import('../index.mjs')

let failures = []

console.log('name:', mod.name)
console.log('inject:', JSON.stringify(mod.inject))
console.log('apply:', typeof mod.apply)

if (typeof mod.name !== 'string' || !mod.name) failures.push('缺导出 name')
if (!Array.isArray(mod.inject)) failures.push('缺导出 inject')
if (typeof mod.apply !== 'function') failures.push('缺导出 apply')
if (mod.inject.includes('subprocess')) {
  // subprocess 是可选服务：通过 ctx.get('subprocess') 取，缺了要能给可读报错。
  // 硬注入会让整个预设在没有 subprocess 的 composition 里挂载失败。
  failures.push('subprocess 不该硬注入，应走 ctx.get')
}

const exported = Object.keys(mod).sort()
console.log('exports:', exported.join(', '))

if (failures.length) {
  console.log('\nFAILURES:')
  for (const failure of failures) console.log('  -', failure)
  process.exit(1)
}
console.log('\nMODULE OK')
