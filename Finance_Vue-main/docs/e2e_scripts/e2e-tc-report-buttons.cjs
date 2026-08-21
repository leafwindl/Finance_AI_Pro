/* 端到端验证：tc 面板未完成 Agent3/4 的用例 → 测试用例工作台 →
   新增的「查看预评审报告」「查看六维分析报告」按钮存在并可正确跳转。 */
const { chromium } = require('playwright-core')
const path = require('path')
const fs = require('fs')

const BASE = 'http://127.0.0.1:5173'
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const SHOT_DIR = path.join(__dirname, '..', '..', '.runtime', 'screenshots')
fs.mkdirSync(SHOT_DIR, { recursive: true })
const shot = (page, name) => page.screenshot({ path: path.join(SHOT_DIR, name) })

async function main() {
  const browser = await chromium.launch({ executablePath: EDGE, headless: true, args: ['--no-sandbox', '--disable-gpu'] })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  const consoleErrors = []
  page.on('pageerror', e => consoleErrors.push('PAGEERROR: ' + String(e).slice(0, 300)))

  // 1) 登录
  console.log('STEP1 登录 (1/111111)')
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForSelector('input[placeholder="用户名"]', { timeout: 30000 })
  await page.fill('input[placeholder="用户名"]', '1')
  await page.fill('input[placeholder="密码"]', '111111')
  await page.click('button:has-text("登录")')
  await page.waitForSelector('.dashboard .welcome h2:text("AI 需求助手")', { timeout: 30000 })
  await page.waitForTimeout(2500)
  await shot(page, '04-tc-dashboard.png')

  // 2) 点击 tc 面板"客户密码重置功能"卡片（未注入 tc_card_status → ⏳ → goTc）
  console.log('STEP2 点击测试用例流程面板卡片（未完成状态）')
  const tcPanel = page.locator('div.usecase-panel', { has: page.locator('.panel-title h3:text("测试用例流程")') })
  const card = tcPanel.locator('button.usecase-item', { has: page.locator('.usecase-text:text("客户密码重置功能")') })
  await card.waitFor({ timeout: 15000 })
  const statusIcon = await card.locator('.usecase-status').textContent().catch(() => '(无)')
  console.log('   卡片状态符号:', statusIcon)
  await card.click()
  await page.waitForURL(/\/test-case\/write/, { timeout: 30000 })
  console.log('   工作台 URL:', page.url().slice(0, 120))

  // 3) 验证两个新按钮存在，且在"清空内容"左侧
  console.log('STEP3 验证两个报告按钮')
  const preBtn = page.locator('button:has-text("查看预评审报告")')
  const sixBtn = page.locator('button:has-text("查看六维分析报告")')
  const clearBtn = page.locator('button:has-text("清空内容")')
  await preBtn.waitFor({ timeout: 15000 })
  await sixBtn.waitFor({ timeout: 15000 })
  await clearBtn.waitFor({ timeout: 15000 })
  const preBox = await preBtn.boundingBox()
  const sixBox = await sixBtn.boundingBox()
  const clearBox = await clearBtn.boundingBox()
  const orderOk = preBox.x < sixBox.x && sixBox.x < clearBox.x
  console.log('   按钮顺序 预评审 < 六维 < 清空:', orderOk)
  await shot(page, '05-tc-workbench-buttons.png')

  // 4) 点击"查看六维分析报告"→ 六维报告查看页
  console.log('STEP4 点击查看六维分析报告')
  await sixBtn.click()
  await page.waitForURL(/\/six-dim-report/, { timeout: 30000 })
  await page.waitForSelector('.six-dim-view .analysis-report', { timeout: 30000 })
  await page.waitForTimeout(800)
  const urlSix = page.url()
  const sixBody = await page.locator('body').textContent()
  const sixLen = (await page.locator('.six-dim-view .report-body').textContent().catch(() => '')).length
  console.log('   六维 URL 含 conversationId:', /conversationId=/.test(urlSix))
  console.log('   六维报告正文:', sixLen, '字')
  await shot(page, '06-tc-sixdim-report.png')

  // 5) 返回工作台，点击"查看预评审报告"
  console.log('STEP5 返回并点击查看预评审报告')
  await page.goBack()
  await page.waitForURL(/\/test-case\/write/, { timeout: 30000 })
  await page.locator('button:has-text("查看预评审报告")').waitFor({ timeout: 15000 })
  await page.locator('button:has-text("查看预评审报告")').click()
  await page.waitForURL(/\/chat\/requirement-pre-review/, { timeout: 30000 })
  // 等待预评审报告卡片出现（ReviewReportCard）
  await page.waitForSelector('.report-card', { timeout: 30000 })
  await page.waitForTimeout(800)
  const urlPre = page.url()
  const preLen = (await page.locator('.report-card .report-body').textContent().catch(() => '')).length
  console.log('   预评审 URL 含 conversationId:', /conversationId=/.test(urlPre))
  console.log('   预评审报告正文:', preLen, '字')
  await shot(page, '07-tc-prereview-report.png')

  // 6) 汇总
  console.log('\n===== 汇总 =====')
  console.log('tc 卡片为未完成态（进入工作台而非预评审）:', statusIcon.trim() !== '✅')
  console.log('两个按钮存在且顺序正确:', orderOk)
  console.log('六维报告可查看:', sixLen > 100)
  console.log('预评审报告可查看:', preLen > 100)
  console.log('页面异常:', consoleErrors.length ? consoleErrors : '无')
  console.log('截图目录:', SHOT_DIR)

  await browser.close()
  if (!orderOk || sixLen <= 100 || preLen <= 100) process.exitCode = 1
}

main().catch(e => { console.error('测试脚本异常:', e.message); process.exit(1) })
