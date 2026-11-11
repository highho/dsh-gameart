/**
 * 本地产线任务登记簿。
 *
 * 为什么要它：`run()` 少则一分钟、多则五分钟，全都压在单次工具调用里等，
 * 一旦宿主侧先超时，调用方就只剩一个「不知道到底跑没跑」的状态。
 * 这里把长任务挪到后台，工具立刻返回 job id，再用 gameart_jobs 轮询。
 *
 * 刻意不依赖 Host 的 jobs 服务：那种注册簿要求会话上挂着 job controller，
 * 预设编排稍微一变就会 start 失败；自带一个 Map 反而不会因为装配差异而哑掉。
 * 上限只保留最近 maxHistory 条，跑一下午不会把内存吃掉。
 */
import { randomUUID } from 'node:crypto'

export const JOB_STATUS = Object.freeze({
  RUNNING: 'running',
  DONE: 'done',
  FAILED: 'failed',
  CANCELLED: 'cancelled',
})

export function createJobRegistry(maxHistory = 40) {
  /** @type {Map<string, object>} */
  const jobs = new Map()

  function trim() {
    if (jobs.size <= maxHistory) return
    // 只回收已经结束的，运行中的永远留着
    for (const [id, job] of jobs) {
      if (jobs.size <= maxHistory) break
      if (job.status !== JOB_STATUS.RUNNING) jobs.delete(id)
    }
  }

  /** 立刻返回 job（还没跑完），work 在后台继续。 */
  function start(kind, label, work) {
    const job = {
      id: `job_${randomUUID().slice(0, 8)}`,
      kind,
      label,
      status: JOB_STATUS.RUNNING,
      message: '已提交',
      startedAt: Date.now(),
      finishedAt: null,
      result: null,
      error: null,
      controller: new AbortController(),
    }
    jobs.set(job.id, job)

    const onProgress = (message) => {
      if (typeof message === 'string' && message.length > 0) job.message = message
    }

    Promise.resolve()
      .then(() => work(job, onProgress))
      .then((result) => {
        if (job.status === JOB_STATUS.CANCELLED) return
        job.result = result
        if (result && result.ok === false) {
          job.status = JOB_STATUS.FAILED
          job.error = result.error ?? '产线失败'
          job.message = job.error
        } else {
          job.status = JOB_STATUS.DONE
          const count = Array.isArray(result?.images) ? result.images.length : 0
          job.message = count > 0 ? `完成，出图 ${count} 张` : '完成'
        }
      })
      .catch((error) => {
        if (job.status === JOB_STATUS.CANCELLED) return
        job.status = JOB_STATUS.FAILED
        job.error = `${error?.name ?? 'Error'}: ${error?.message ?? error}`
        job.message = job.error
      })
      .finally(() => {
        job.finishedAt = Date.now()
        trim()
      })

    return job
  }

  function cancel(id) {
    const job = jobs.get(id)
    if (!job) return { ok: false, error: `没有这个任务：${id}` }
    if (job.status !== JOB_STATUS.RUNNING) {
      return { ok: false, error: `任务已结束（${job.status}），无需取消`, job: view(job) }
    }
    job.status = JOB_STATUS.CANCELLED
    job.message = '已取消'
    job.finishedAt = Date.now()
    try {
      job.controller.abort()
    } catch {
      /* 已经结束 */
    }
    return { ok: true, job: view(job) }
  }

  function view(job) {
    const images = Array.isArray(job.result?.images) ? job.result.images : null
    return {
      id: job.id,
      kind: job.kind,
      label: job.label,
      status: job.status,
      message: job.message,
      elapsed:
        job.startedAt != null
          ? Math.round((Number(job.finishedAt ?? Date.now()) - job.startedAt) / 1000)
          : null,
      error: job.error,
      pipeline: job.result?.pipeline ?? null,
      applied_overrides: job.result?.applied_overrides ?? null,
      images,
      count: images ? images.length : 0,
    }
  }

  function list(kind) {
    const all = [...jobs.values()]
      .filter((job) => (kind ? job.kind === kind : true))
      .sort((a, b) => b.startedAt - a.startedAt)
    return all.map(view)
  }

  function get(id) {
    const job = jobs.get(id)
    return job ? view(job) : null
  }

  function running() {
    return [...jobs.values()].filter((job) => job.status === JOB_STATUS.RUNNING).map(view)
  }

  return { start, cancel, list, get, running }
}
