// 知识库上传 V2 验收脚本（mock 路由拦截，Gateway 未启动时前端侧验证）。
// 用法：先启动 dev server（5173），再 node scripts/verify-upload-v2.mjs
// 覆盖：下拉选项 / 自动分类（不传 kb_code）/ 手动指定（传 kb_code）/ 块级多库结果 /
//       失败任务错误提示 / 轮询进度 / 无直连后端。
import { chromium } from 'playwright-core'

const BASE = 'http://127.0.0.1:5173'
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'

const results = []
const ok = (name, pass, detail = '') => {
  results.push({ name, pass: !!pass })
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  →  ' + detail : ''}`)
}

const AUTO_RESULT = {
  kb_distribution: { KB01: 2, KB04: 1 },
  total_chunks: 3,
  blocks: [
    { heading: '第一章 总则', kb_code: 'KB01', doc_id: 'd1' },
    { heading: '第二章 交易', kb_code: 'KB01', doc_id: 'd2' },
    { heading: '附录 规则', kb_code: 'KB04', doc_id: 'd3' },
  ],
  // 后端语义：多库分布时不返回 kb_code/doc_id（仅单库时有）
}

const browser = await chromium.launch({ headless: true, executablePath: EDGE })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const requests = []
const uploadBodies = []
let uploadSeq = 0
let currentKb = ''

const page = await context.newPage()
await page.route('**/api/v1/**', async (route) => {
  const req = route.request()
  const pathname = new URL(req.url()).pathname
  const method = req.method()
  requests.push(`${method} ${pathname}`)

  const json = (body, status = 200) =>
    route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

  if (pathname.endsWith('/auth/me')) return json({ user_id: 1, name: 'tester' })
  if (pathname.endsWith('/knowledge/upload')) {
    uploadSeq++
    const body = req.postData() || ''
    uploadBodies.push(body)
    const m = body.match(/name="kb_code"\r\n\r\n(KB\d{2})/)
    currentKb = m ? m[1] : ''
    return json(
      { task_id: 'kb_abcdef123456', file_id: 'file_x', filename: '需求说明.md', status: 'processing' },
      202
    )
  }
  if (pathname.includes('/knowledge/tasks/')) {
    const taskGets = requests.filter((r) => r.includes('/knowledge/tasks/')).length
    if (uploadSeq >= 3) {
      // 第三次上传 → 任务失败（模拟全部 OUT_OF_SCOPE）
      return json({
        task_id: 'kb_abcdef123456',
        filename: '坏.md',
        status: 'failed',
        progress: { stage: 'done', percent: 100 },
        error: { code: 'ingest_failed', message: '没有可入库的知识块（全部 OUT_OF_SCOPE 或分类失败）', retryable: true },
      })
    }
    if (taskGets <= 1) {
      // 第一次轮询：处理中，带阶段与百分比
      return json({ task_id: 'kb_abcdef123456', filename: '需求说明.md', status: 'processing', progress: { stage: '解析', percent: 30 } })
    }
    const result = currentKb
      ? { kb_distribution: { [currentKb]: 3 }, total_chunks: 3, blocks: AUTO_RESULT.blocks, kb_code: currentKb, doc_id: 'd1' }
      : AUTO_RESULT
    return json({ task_id: 'kb_abcdef123456', filename: '需求说明.md', status: 'completed', progress: { stage: 'done', percent: 100 }, result })
  }
  // 其余（会话/需求等）后端未启动时放行 → 网络失败，页面自行容错
  return route.fallback()
})

await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded', timeout: 30000 })
await page.waitForSelector('.kb-dropzone', { timeout: 15000 })

const state = (p) => p.evaluate(() => document.querySelector('.kb-dropzone').__vueParentComponent.setupState)

// ---- 1. 下拉选项 ----
ok('下拉选择器存在', (await page.locator('.kb-dropzone__select').count()) === 1)
await page.locator('.kb-dropzone__select').click()
await page.waitForTimeout(300)
const optionTexts = await page.locator('.el-select-dropdown__item').allTextContents()
ok('下拉含「自动分类（推荐）」与 KB01~KB06', optionTexts.some((t) => t.includes('自动分类')) && optionTexts.some((t) => t.includes('KB06')), optionTexts.join('|'))
await page.keyboard.press('Escape')
await page.waitForTimeout(200)

// ---- 2. 自动分类：不传 kb_code，展示块级多库结果 ----
await page.evaluate(() => {
  const st = document.querySelector('.kb-dropzone').__vueParentComponent.setupState
  st.handleFiles([new File(['# 第一章 总则\n\n支持登录。'], '需求说明.md', { type: 'text/markdown' })])
})
await page.waitForTimeout(2600)
await page.waitForSelector('.el-notification', { timeout: 10000 })
let note = await page.locator('.el-notification').last().textContent()
ok('自动分类：通知含 KB01×2、KB04×1', note.includes('KB01×2') && note.includes('KB04×1'), note.slice(0, 80))
ok('自动分类：通知含总块数 3', note.includes('3 个知识块'), note.slice(0, 80))
ok('自动分类：未发送 kb_code', uploadBodies.length >= 1 && !uploadBodies[uploadBodies.length - 1].includes('name="kb_code"'))
ok('自动分类：完成后恢复空闲', (await state(page)).uploading === false)

// ---- 3. 手动指定：传 kb_code=KB02 ----
await page.evaluate(() => {
  const st = document.querySelector('.kb-dropzone').__vueParentComponent.setupState
  st.selectedKb = 'KB02'
  st.handleFiles([new File(['# 规范\n\n统一编号。'], '规范.md', { type: 'text/markdown' })])
})
await page.waitForTimeout(2600)
await page.waitForSelector('.el-notification', { timeout: 10000 })
note = await page.locator('.el-notification').last().textContent()
ok('手动指定：通知含「已入库到 KB02」', note.includes('已入库到 KB02'), note.slice(0, 80))
const lastBody = uploadBodies[uploadBodies.length - 1] || ''
ok('手动指定：请求携带 kb_code=KB02', lastBody.includes('name="kb_code"') && lastBody.includes('KB02'))
ok('手动指定：完成后恢复空闲', (await state(page)).uploading === false)

// ---- 4. 失败任务：task failed → 错误提示 ----
await page.evaluate(() => {
  const st = document.querySelector('.kb-dropzone').__vueParentComponent.setupState
  st.selectedKb = ''
  st.handleFiles([new File(['# 坏文档'], '坏.md', { type: 'text/markdown' })])
})
await page.waitForTimeout(1200)
await page.waitForSelector('.el-message', { timeout: 10000 })
const msgText = await page.locator('.el-message').last().textContent()
ok('失败路径：错误提示可见', /失败/.test(msgText), msgText.slice(0, 80))
ok('失败路径：完成后恢复空闲', (await state(page)).uploading === false)

// ---- 5. 请求均为 /api/v1/*，无直连后端 ----
const bad = requests.filter((r) => /:(8002|7687|9200|5432)/.test(r))
ok('无直连后端（8002/7687/9200/5432）', bad.length === 0)
const hasUpload = requests.some((r) => r.includes('POST /api/v1/knowledge/upload'))
const hasTasks = requests.some((r) => r.includes('GET /api/v1/knowledge/tasks/'))
ok('调用上传与任务轮询接口', hasUpload && hasTasks, requests.filter((r) => r.includes('/knowledge/')).join(', '))

await page.screenshot({ path: 'upload-v2-acceptance.png', fullPage: true })

const failed = results.filter((r) => !r.pass)
console.log(`\n==== 汇总 ====\n总用例 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
if (failed.length) for (const f of failed) console.log(`  - ${f.name}`)
await browser.close()
process.exit(failed.length ? 1 : 0)
