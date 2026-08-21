import { chromium } from 'playwright-core'

const browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe' })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const requests = []
const data = {
  graph: {
    nodes: [
      { id: 'kb:KB01', type: 'kb', kb_code: 'KB01', label: '业务知识库', count: 1 },
      { id: 'doc:doc1', type: 'doc', doc_id: 'doc1', kb_code: 'KB01', label: '登录需求说明', source_file: 'login.md', chunk_count: 1 }
    ],
    links: [{ source: 'kb:KB01', target: 'doc:doc1', type: 'CONTAINS' }]
  },
  documents: { documents: [{ doc_id: 'doc1', title: '登录需求说明', kb_code: 'KB01', source_file: 'login.md', chunk_count: 1 }] },
  content: { doc_id: 'doc1', title: '登录需求说明', kb_code: 'KB01', source_file: 'login.md', chunk_count: 1, chars: 24, content_markdown: '# 登录需求说明\n\n支持安全登录。' },
  subgraph: { nodes: [{ id: 'chunk:doc1:0', type: 'chunk', doc_id: 'doc1', kb_code: 'KB01', label: '第 1 块', text: '支持安全登录。' }], links: [] }
}
await page.route('**/api/v1/**', async route => {
  const url = new URL(route.request().url())
  requests.push(url.pathname)
  let body = data.graph
  if (url.pathname.endsWith('/kbs/KB01/documents')) body = data.documents
  else if (url.pathname.endsWith('/documents/doc1/content')) body = data.content
  else if (url.pathname.endsWith('/documents/doc1/subgraph')) body = data.subgraph
  await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
})
await page.goto('http://127.0.0.1:5173/knowledge-graph', { waitUntil: 'networkidle' })
await page.screenshot({ path: 'knowledge-graph-mock-initial.png', fullPage: true })
const initial = await page.getByRole('heading', { name: '知识图谱', exact: true }).textContent()
const kbText = await page.locator('.guide-panel').textContent()
await page.getByText('业务知识库', { exact: false }).first().click()
await page.waitForTimeout(300)
const fileText = await page.locator('.file-panel').textContent()
await page.getByRole('button', { name: /登录需求说明/ }).click()
await page.waitForTimeout(300)
const contentText = await page.locator('.doc-content').textContent()
await page.screenshot({ path: 'knowledge-graph-mock-content.png', fullPage: true })
console.log(JSON.stringify({ initial, hasGuide: kbText.includes('探索知识图谱'), hasFile: fileText.includes('登录需求说明'), hasMarkdown: contentText.includes('支持安全登录'), requests }, null, 2))
await browser.close()
