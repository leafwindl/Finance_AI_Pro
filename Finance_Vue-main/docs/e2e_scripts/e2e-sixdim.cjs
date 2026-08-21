/* 端到端验证：测试用例流程面板 ✅ 用例 → 预评审工作台 → 查看六维分析 → 六维报告查看页
   复现用户 bug 场景：预评审已通过 → 点击"查看六维分析"应带 conversationId 打开报告，而非"缺少会话 ID"。 */
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

  // 模拟用户浏览器已有的 localStorage 状态：r1（客户密码重置功能）已通过预评审 + 用例流程
  await page.addInitScript(() => {
    localStorage.setItem('card_status', JSON.stringify({ r1: 'approved' }))
    localStorage.setItem('tc_card_status', JSON.stringify({ r1: 'approved' }))
  })

  const consoleErrors = []
  page.on('console', m => { if (m.type() === 'error') consoleErrors.push(m.text().slice(0, 300)) })
  page.on('pageerror', e => consoleErrors.push('PAGEERROR: ' + String(e).slice(0, 300)))
  page.on('requestfailed', r => consoleErrors.push('REQFAIL: ' + r.url().slice(0, 150) + ' ' + (r.failure()?.errorText || '')))

  // 1) 登录
  console.log('STEP1 打开首页 → 登录 (1/111111)')
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForSelector('input[placeholder="用户名"]', { timeout: 30000 })
  await page.fill('input[placeholder="用户名"]', '1')
  await page.fill('input[placeholder="密码"]', '111111')
  await page.click('button:has-text("登录")')

  // 2) 仪表盘
  console.log('STEP2 等待仪表盘')
  await page.waitForSelector('.dashboard .welcome h2:text("AI 需求助手")', { timeout: 30000 })
  await page.waitForTimeout(2500) // 等待会话同步 + 卡片状态计算
  await shot(page, '01-dashboard.png')

  // 3) 点击测试用例流程面板中"客户密码重置功能"（应为 ✅）
  console.log('STEP3 点击测试用例流程面板卡片: 客户密码重置功能')
  const tcPanel = page.locator('div.usecase-panel', { has: page.locator('.panel-title h3:text("测试用例流程")') })
  const card = tcPanel.locator('button.usecase-item', { has: page.locator('.usecase-text:text("客户密码重置功能")') })
  await card.waitFor({ timeout: 15000 })
  // 记录卡片状态符号
  const cardStatusText = await card.locator('.usecase-status').textContent().catch(() => '(无)')
  console.log('   卡片状态符号:', cardStatusText)
  await card.click()
  await page.waitForURL(/\/chat\/requirement-pre-review/, { timeout: 30000 })
  const urlPre = page.url()
  console.log('   预评审 URL:', urlPre.slice(0, 140))

  // 4) 预评审报告（已通过 + 查看六维分析按钮）
  console.log('STEP4 等待预评审报告 + 查看六维分析按钮')
  await page.waitForSelector('button:has-text("查看六维分析")', { timeout: 60000 })
  await page.waitForTimeout(500)
  await shot(page, '02-pre-review-report.png')

  // 5) 点击查看六维分析
  console.log('STEP5 点击查看六维分析')
  await page.click('button:has-text("查看六维分析")')

  // 6) 六维报告查看页
  console.log('STEP6 等待六维报告查看页')
  await page.waitForURL(/\/six-dim-report/, { timeout: 30000 })
  const url6 = page.url()
  console.log('   六维报告 URL:', url6.slice(0, 200))
  await page.waitForSelector('.six-dim-view .analysis-report', { timeout: 30000 })
  await page.waitForTimeout(800)
  await shot(page, '03-six-dim-report.png')

  // 7) 断言
  const bodyText = await page.locator('body').textContent()
  const hasMissingSessionError = bodyText.includes('缺少会话 ID')
  const h1Text = await page.locator('.six-dim-view h1').textContent().catch(() => '(无)')
  const reportLen = (await page.locator('.six-dim-view .report-body').textContent().catch(() => '')).length

  console.log('\n===== 汇总 =====')
  console.log('tc 面板卡片 ✅:', cardStatusText.trim() === '✅')
  console.log('查看六维分析按钮出现:', (await page.locator('button:has-text("查看六维分析")').count()) > 0)
  console.log('最终 URL 含 conversationId:', /conversationId=/.test(url6))
  console.log('h1 标题:', h1Text)
  console.log('报告正文长度:', reportLen, '字')
  console.log('仍显示"缺少会话 ID":', hasMissingSessionError)
  console.log('控制台错误:', consoleErrors.length ? consoleErrors : '无')
  console.log('截图目录:', SHOT_DIR)

  await browser.close()
  if (hasMissingSessionError || reportLen <= 100) process.exitCode = 1
}

main().catch(e => { console.error('测试脚本异常:', e.message); process.exit(1) })
