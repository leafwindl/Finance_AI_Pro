/** 知识库 API：文档入库、图谱、文件列表、正文及文档子图。 */
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

const getErrorMessage = async (response) => {
  try {
    const data = await response.json()
    if (typeof data?.detail === 'string') return data.detail
    if (typeof data?.detail?.message === 'string') return data.detail.message
    if (typeof data?.error?.message === 'string') return data.error.message
  } catch { /* response body is not JSON */ }
  return `HTTP ${response.status}`
}

async function requestJson(path, { signal } = {}) {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    credentials: 'include',
    signal
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  try {
    return await response.json()
  } catch {
    throw new Error('接口响应不是合法 JSON')
  }
}

/**
 * 上传文档到知识库（V2：异步任务）。
 * POST /api/v1/knowledge/upload → 202 + { task_id, file_id, filename, status }。
 * kbCode 可选：空/不传 → 后台按块全自动分类（默认）；传 KB01~KB06 → 整篇归入指定库。
 * 提交后需轮询 getKnowledgeTask() 直到终态；单次上传请用 uploadDocumentAndWait()。
 */
export async function uploadToKnowledgeBase(file, { kbCode = '', signal } = {}) {
  const formData = new FormData()
  formData.append('file', file)
  const code = String(kbCode || '').trim().toUpperCase()
  if (code) formData.append('kb_code', code)

  const response = await fetch(`${apiBaseUrl}/knowledge/upload`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
    signal
  })

  if (!response.ok) {
    throw new Error(await getErrorMessage(response))
  }

  try {
    return await response.json()
  } catch {
    throw new Error('接口响应不是合法 JSON')
  }
}

/** 查询入库任务状态。GET /api/v1/knowledge/tasks/{taskId} */
export function getKnowledgeTask(taskId, { signal } = {}) {
  return requestJson(`/knowledge/tasks/${encodeURIComponent(taskId)}`, { signal })
}

/**
 * 上传并轮询到终态（completed / failed）。
 * V2 结果结构：{ kb_distribution, total_chunks, blocks, kb_code?, doc_id? }。
 * 取消：传入 AbortController 的 signal；进度：onProgress(task)。
 */
export async function uploadDocumentAndWait(
  file,
  { kbCode = '', signal, onProgress, pollIntervalMs = 1500, maxAttempts = 120 } = {}
) {
  const created = await uploadToKnowledgeBase(file, { kbCode, signal })
  if (!created?.task_id) {
    throw new Error('上传响应缺少任务 ID')
  }

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (signal?.aborted) throw new DOMException('上传已取消', 'AbortError')
    const task = await getKnowledgeTask(created.task_id, { signal })
    onProgress?.(task)
    if (task?.status === 'completed') return task
    if (task?.status === 'failed') {
      const err = task.error
      throw new Error((err && (err.message || err.code)) || '入库任务失败')
    }
    await new Promise((resolve) => {
      let onAbort
      const timer = setTimeout(() => {
        if (onAbort) signal?.removeEventListener('abort', onAbort)
        resolve()
      }, pollIntervalMs)
      onAbort = () => { clearTimeout(timer); resolve() }
      signal?.addEventListener('abort', onAbort, { once: true })
    })
  }
  throw new Error('入库超时，请稍后重试或稍后到知识库查看')
}

/** 获取知识库与文档的两级图谱。GET /api/v1/knowledge/graph */
export function fetchKnowledgeGraph({ signal } = {}) {
  return requestJson('/knowledge/graph', { signal })
}

/** 获取指定知识库下的文档列表。GET /api/v1/knowledge/kbs/{kbCode}/documents */
export function listKbDocuments(kbCode, { signal } = {}) {
  return requestJson(`/knowledge/kbs/${encodeURIComponent(kbCode)}/documents`, { signal })
}

/** 获取知识库文档的 Markdown 正文。GET /api/v1/knowledge/documents/{docId}/content */
export function fetchDocumentContent(docId, { signal } = {}) {
  return requestJson(`/knowledge/documents/${encodeURIComponent(docId)}/content`, { signal })
}

/** 获取文档的分块与实体子图。GET /api/v1/knowledge/documents/{docId}/subgraph */
export function fetchDocumentSubgraph(docId, { signal } = {}) {
  return requestJson(`/knowledge/documents/${encodeURIComponent(docId)}/subgraph`, { signal })
}
