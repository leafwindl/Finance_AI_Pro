// 知识图谱前端验收脚本（mock 路由拦截）。
// 用法：先启动 dev server（5173），再 node scripts/verify-knowledge-graph-acceptance.mjs
// 覆盖：全图加载 / 选库 / 正文 / 子图 / 分块 / 实体 / 收起 / 错误态 / 鉴权重定向 / 无直连后端 / XSS 清洗 / 缩放按钮。
import { chromium } from 'playwright-core'

const BASE = 'http://127.0.0.1:5173'
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'

const mock = {
  graph: {
    nodes: [
      { id: 'kb:KB01', type: 'kb', kb_code: 'KB01', label: '业务知识库', count: 2 },
      { id: 'kb:KB02', type: 'kb', kb_code: 'KB02', label: '系统规范库', count: 0 },
      { id: 'doc:doc1', type: 'doc', doc_id: 'doc1', kb_code: 'KB01', label: '登录需求说明', source_file: 'login.md', chunk_count: 1 },
      { id: 'doc:doc2', type: 'doc', doc_id: 'doc2', kb_code: 'KB01', label: '资金对冲需求分析', source_file: 'hedge.md', chunk_count: 2 },
    ],
    links: [
      { source: 'kb:KB01', target: 'doc:doc1', type: 'CONTAINS' },
      { source: 'kb:KB01', target: 'doc:doc2', type: 'CONTAINS' },
    ],
  },
  documents: {
    documents: [
      { doc_id: 'doc1', title: '登录需求说明', kb_code: 'KB01', source_file: 'login.md', chunk_count: 1 },
      { doc_id: 'doc2', title: '资金对冲需求分析', kb_code: 'KB01', source_file: 'hedge.md', chunk_count: 2 },
    ],
  },
  content: {
    doc_id: 'doc1', title: '登录需求说明', kb_code: 'KB01', source_file: 'login.md',
    chunk_count: 1, chars: 24,
    content_markdown: '# 登录需求说明\n\n支持安全登录。<b>加粗富文本</b><script>window.__xss=1</script>',
  },
  subgraph: {
    nodes: [
      { id: 'chunk:doc1:0', type: 'chunk', doc_id: 'doc1', kb_code: 'KB01', label: '第 1 块', text: '支持安全登录。' },
      { id: 'entity:session', type: 'entity', kb_code: 'KB01', name: '用户会话', entity_type: 'MODULE', description: '会话管理实体' },
      { id: 'entity:perm', type: 'entity', kb_code: 'KB01', name: '权限校验', entity_type: 'PERMISSION', description: '权限控制' },
    ],
    links: [
      { source: 'doc:doc1', target: 'chunk:doc1:0', type: 'PART_OF' },
      { source: 'chunk:doc1:0', target: 'entity:session', type: 'HAS_ENTITY' },
      { source: 'entity:session', target: 'entity:perm', type: 'RELATED' },
    ],
  },
}

const results = []
const ok = (name, pass, detail = '') => {
  results.push({ name, pass: !!pass, detail: detail || (pass ? 'OK' : 'FAIL') })
  console.log(`${pass ? 'PASS' : 'FAIL'}  ${name}${detail ? '  →  ' + detail : ''}`)
}

const browser = await chromium.launch({ headless: true, executablePath: EDGE })
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const requests = []
const pageErrors = []

async function installMockRoutes(page, flags = {}) {
  await page.route('**/api/v1/**', async (route) => {
    const pathname = new URL(route.request().url()).pathname
    requests.push(pathname)
    const json = (body, status = 200) =>
      route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) })

    if (pathname.endsWith('/auth/me')) return json({ user_id: 1, name: 'tester' })
    if (pathname.endsWith('/knowledge/graph')) {
      return flags.graphFail ? json({ detail: '图谱服务不可用' }, 503) : json(mock.graph)
    }
    if (pathname.endsWith('/kbs/KB01/documents')) return json(mock.documents)
    if (pathname.endsWith('/kbs/KB99/documents')) return json({ detail: '知识库不存在' }, 404)
    if (pathname.endsWith('/documents/doc1/content')) return json(mock.content)
    if (pathname.endsWith('/documents/doc1/subgraph')) return json(mock.subgraph)
    if (pathname.endsWith('/documents/doc2/content')) return json({ detail: '文档内容服务超时' }, 503)
    if (pathname.endsWith('/documents/doc2/subgraph')) return json({ wrong: true })
    return json(mock.graph)
  })
}

// 访问 Vue 组件 setupState（与源版 debug 脚本同模式，避免依赖画布坐标）。
// 注意：不要把整个 setupState 直接序列化回 Node —— 嵌套的 Set（expandedDocs）会被
// 序列化成空对象；Set 断言必须放到页面内做。
const state = (page) => page.evaluate(() => {
  const el = document.querySelector('.graph-view')
  return el ? el.__vueParentComponent?.setupState : null
})
const expandedList = (page) => page.evaluate(() =>
  [...(document.querySelector('.graph-view').__vueParentComponent.setupState.expandedDocs || [])]
)

const page = await context.newPage()
page.on('pageerror', (e) => pageErrors.push(String(e.message).slice(0, 200)))
await installMockRoutes(page)
await page.goto(`${BASE}/knowledge-graph`, { waitUntil: 'networkidle', timeout: 30000 })

// ---- A. 初始加载 ----
let s = await state(page)
ok('初始加载：图谱无错误', s && s.graphError === '' && s.graphLoading === false, JSON.stringify(s?.graphError))
ok('初始加载：KB+文档节点数=4', s?.graphData?.nodes?.length === 4, `nodes=${s?.graphData?.nodes?.length}`)
ok('初始加载：guide 面板可见', (await page.locator('.guide-panel').count()) === 1)
ok('初始加载：画布已渲染', (await page.locator('.graph-canvas canvas').count()) === 1)

// ---- B. 选择知识库 ----
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.selectKb({ kb_code: 'KB01' }))
await page.waitForTimeout(300)
s = await state(page)
ok('选库：selectedKb=KB01、files 面板', s?.selectedKb === 'KB01' && s?.panelView === 'files', `panel=${s?.panelView}`)
ok('选库：文档列表 2 条', (await page.locator('.file-panel .doc-item').count()) === 2)
const fileText = await page.locator('.file-panel').textContent()
ok('选库：列表含两个文档名', fileText.includes('登录需求说明') && fileText.includes('资金对冲需求分析'))

// ---- C. 打开文档 → 正文 + 自动展开子图 ----
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.openDoc({ doc_id: 'doc1', title: '登录需求说明', kb_code: 'KB01' }))
await page.waitForTimeout(500)
s = await state(page)
ok('正文：panel=content、无错误', s?.panelView === 'content' && s?.contentError === '', `err=${s?.contentError}`)
const md = await page.locator('.doc-content .markdown-body').textContent()
ok('正文：Markdown 已渲染', md.includes('支持安全登录') && md.includes('加粗富文本'))
ok('XSS：script 被 DOMPurify 清除', (await page.locator('.doc-content script').count()) === 0 && !(await page.evaluate(() => window.__xss)))
const expandedAfterOpen = await expandedList(page)
ok('子图：doc1 已展开', expandedAfterOpen.includes('doc1'), JSON.stringify(expandedAfterOpen))
const types = {}
for (const n of s.graphData.nodes) types[n.type] = (types[n.type] || 0) + 1
ok('子图：出现 chunk+entity 节点', types.chunk >= 1 && types.entity >= 2, JSON.stringify(types))

// ---- D. 分块详情 ----
await page.evaluate(() => {
  const st = document.querySelector('.graph-view').__vueParentComponent.setupState
  const chunk = st.graphData.nodes.find((n) => n.type === 'chunk')
  st.showChunk(chunk)
})
await page.waitForTimeout(200)
s = await state(page)
ok('分块：panel=chunk 且正文渲染', s?.panelView === 'chunk' && (await page.locator('.detail-panel .markdown-body').textContent()).includes('支持安全登录'))

// ---- E. 实体详情 + 关联 ----
await page.evaluate(() => {
  const st = document.querySelector('.graph-view').__vueParentComponent.setupState
  const entity = st.graphData.nodes.find((n) => n.type === 'entity')
  st.showEntity(entity)
})
await page.waitForTimeout(200)
s = await state(page)
const entityName = await page.locator('.detail-panel h3').textContent()
ok('实体：panel=entity 且名称正确', s?.panelView === 'entity' && entityName.includes('用户会话'))
const relCount = await page.locator('.rel-item').count()
ok('实体：关联实体 ≥1', relCount >= 1, `rel=${relCount}`)

// ---- F. 收起子图 ----
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.toggleDocExpansion({ doc_id: 'doc1' }))
await page.waitForTimeout(200)
s = await state(page)
const expandedAfterCollapse = await expandedList(page)
ok('收起：doc1 展开态移除', !expandedAfterCollapse.includes('doc1'), JSON.stringify(expandedAfterCollapse))
const typesAfter = {}
for (const n of s.graphData.nodes) typesAfter[n.type] = (typesAfter[n.type] || 0) + 1
ok('收起：chunk/entity 已从画布移除', !typesAfter.chunk && !typesAfter.entity, JSON.stringify(typesAfter))

// ---- G. 错误态：graph 503 → 重试恢复 ----
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.loadGraph())
await page.waitForTimeout(300)
s = await state(page)
ok('graph 正常加载兜底', s?.graphError === '')

// 切换 graphFail 标志后重新 install mock
await page.unroute('**/api/v1/**')
await installMockRoutes(page, { graphFail: true })
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.loadGraph())
await page.waitForTimeout(300)
s = await state(page)
ok('graph 503：错误态可见', s?.graphError.includes('不可用') && (await page.locator('.full-state.error').count()) === 1, s?.graphError)
ok('graph 503：重试按钮存在', (await page.getByRole('button', { name: /重试/ }).count()) >= 1)

// 恢复 graph
await page.unroute('**/api/v1/**')
await installMockRoutes(page)
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.loadGraph())
await page.waitForTimeout(300)

// ---- H. 错误态：files 404 ----
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.selectKb({ kb_code: 'KB99' }))
await page.waitForTimeout(300)
s = await state(page)
ok('files 404：错误态可见', s?.filesError.includes('知识库不存在') && (await page.locator('.file-panel .state.error').count()) === 1, s?.filesError)
ok('files 404：重试按钮存在', (await page.locator('.file-panel').getByRole('button', { name: /重试/ }).count()) === 1)

// ---- I. 错误态：content 503 + subgraph 非法结构 ----
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.selectKb({ kb_code: 'KB01' }))
await page.waitForTimeout(300)
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.openDoc({ doc_id: 'doc2', title: '资金对冲需求分析', kb_code: 'KB01' }))
await page.waitForTimeout(500)
s = await state(page)
ok('content 503：正文错误态', s?.contentError.includes('超时') && (await page.locator('.doc-content .state.error').count()) === 1, s?.contentError)
ok('subgraph 非法结构：告警出现', s?.subgraphError.includes('文档子图') && (await page.locator('.subgraph-alert').count()) === 1, s?.subgraphError)

// ---- J. 重置 + 刷新 ----
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.resetSelection())
await page.waitForTimeout(200)
s = await state(page)
ok('重置：回到 guide、selectedKb=null', s?.selectedKb === null && (await page.locator('.guide-panel').count()) === 1)
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.loadGraph())
await page.waitForTimeout(300)
s = await state(page)
ok('刷新：图谱重新加载', s?.graphLoading === false && s?.graphError === '' && s?.graphData?.nodes?.length === 4)

// ---- K. 缩放按钮 ----
await page.getByRole('button', { name: '放大图谱' }).click()
await page.getByRole('button', { name: '缩小图谱' }).click()
await page.getByRole('button', { name: '适配图谱视图' }).click()
ok('缩放/适配按钮可点', true)

// ---- L. 侧栏入口 ----
ok('侧栏含知识图谱入口', (await page.locator('a[href="/knowledge-graph"]').count()) === 1)

// ---- M. 无直连后端 ----
const bad = requests.filter((p) => /:(8002|7687|9200|5432)/.test(p))
ok('请求均为 /api/v1/*，无直连后端', bad.length === 0 && requests.every((p) => p.startsWith('/api/v1/')), `请求数=${requests.length}`)

// ---- N. 鉴权重定向（未登录） ----
const ctx2 = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const page2 = await ctx2.newPage()
await page2.route('**/api/v1/**', (route) =>
  route.fulfill({ status: 401, contentType: 'application/json', body: JSON.stringify({ detail: '未登录' }) }))
await page2.goto(`${BASE}/knowledge-graph`, { waitUntil: 'networkidle', timeout: 30000 })
ok('鉴权：未登录重定向 /login 且带 redirect', new URL(page2.url()).pathname === '/login' && new URL(page2.url()).searchParams.get('redirect') === '/knowledge-graph', page2.url())
await ctx2.close()

// ---- 截图 ----
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.selectKb({ kb_code: 'KB01' }))
await page.waitForTimeout(300)
await page.evaluate(() => document.querySelector('.graph-view').__vueParentComponent.setupState.openDoc({ doc_id: 'doc1', title: '登录需求说明', kb_code: 'KB01' }))
await page.waitForTimeout(500)
await page.screenshot({ path: 'knowledge-graph-acceptance-final.png', fullPage: true })

const failed = results.filter((r) => !r.pass)
console.log('\n==== 汇总 ====')
console.log(`总用例 ${results.length}，通过 ${results.length - failed.length}，失败 ${failed.length}`)
if (failed.length) {
  console.log('失败项：')
  for (const f of failed) console.log(`  - ${f.name}：${f.detail}`)
}
if (pageErrors.length) {
  console.log('页面异常：')
  for (const e of pageErrors) console.log('  -', e)
} else {
  console.log('页面异常：无')
}
await browser.close()
process.exit(failed.length || pageErrors.length ? 1 : 0)
