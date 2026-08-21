/** 测试用例工作流专用 API，不再复用聊天模块。 */
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

const clientId = () => `case_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`

function postWorkflow(path, query, onEvent, { timeoutMs = 240000 } = {}) {
  let buffer = ''
  let consumed = 0
  let streamError = null

  const parseAvailable = () => {
    let boundary
    while ((boundary = buffer.search(/\r?\n\r?\n/)) >= 0) {
      const block = buffer.slice(0, boundary)
      const separator = buffer.slice(boundary).match(/^\r?\n\r?\n/)?.[0] || '\n\n'
      buffer = buffer.slice(boundary + separator.length)
      let event = 'message'
      const dataLines = []
      for (const line of block.split(/\r?\n/)) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) dataLines.push(line.slice(5).trimStart())
      }
      if (dataLines.length) {
        try { onEvent({ event, data:JSON.parse(dataLines.join('\n')) }) } catch (error) { streamError = error }
      }
    }
  }

  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${apiBaseUrl}${path}`, true)
    xhr.withCredentials = true
    xhr.timeout = timeoutMs
    xhr.setRequestHeader('Content-Type', 'application/json')
    xhr.setRequestHeader('Accept', 'text/event-stream')
    xhr.onprogress = () => {
      buffer += xhr.responseText.slice(consumed)
      consumed = xhr.responseText.length
      parseAvailable()
    }
    xhr.onload = () => {
      buffer += xhr.responseText.slice(consumed)
      consumed = xhr.responseText.length
      parseAvailable()
      if (streamError) { reject(streamError); return }
      if (xhr.status >= 200 && xhr.status < 300) { resolve(); return }
      try {
        const body = JSON.parse(xhr.responseText)
        reject(new Error(body?.detail?.message || body?.detail || `HTTP ${xhr.status}`))
      } catch { reject(new Error(`HTTP ${xhr.status}`)) }
    }
    xhr.onerror = () => reject(new Error('无法连接 Gateway'))
    xhr.ontimeout = () => reject(new Error('工作流请求超时'))
    xhr.onabort = () => reject(new Error('工作流请求已取消'))
    xhr.send(JSON.stringify({ query, client_message_id:clientId() }))
  })
}

export function submitForReview(tc, onEvent) {
  const parts = ['请评审以下结构化测试用例：','']
  if (tc.requirementName) parts.push(`对应需求：${tc.requirementName}`)
  if (tc.title) parts.push(`用例名称：${tc.title}`)
  if (tc.module) parts.push(`所属模块：${tc.module}`)
  if (tc.preconditions) parts.push(`前置条件：${tc.preconditions}`)
  if (tc.testObjective) parts.push(`测试场景/测试点：${tc.testObjective}`)
  if (tc.testData) parts.push(`测试数据与输入条件：${tc.testData}`)
  if (tc.expected) parts.push(`预期结果：${tc.expected}`)
  return postWorkflow('/test-cases/review', parts.join('\n'), onEvent)
}

export function generateSteps(req, onEvent) {
  const parts = ['请根据以下已评审用例生成可执行测试步骤：','']
  if (req.title) parts.push(`用例名称：${req.title}`)
  if (req.module) parts.push(`所属模块：${req.module}`)
  if (req.requirementName) parts.push(`关联需求：${req.requirementName}`)
  if (req.preconditions) parts.push(`前置条件：${req.preconditions}`)
  if (req.testObjective) parts.push(`测试场景/测试点：${req.testObjective}`)
  if (req.testData) parts.push(`测试数据与输入条件：${req.testData}`)
  if (req.expected) parts.push(`预期结果：${req.expected}`)
  if (req.reviewReport) parts.push(`Agent 3 评审报告：${req.reviewReport}`)
  return postWorkflow('/test-cases/generate-steps', parts.join('\n'), onEvent)
}
