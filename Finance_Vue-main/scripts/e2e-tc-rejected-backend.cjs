/* 端到端验证：被驳回用例（本地无保存状态）→ 从后端 Agent3/Agent4 会话兜底恢复。
   模拟"saveTcState 上线前就已驳回"的既有用例：仅 tc_card_status.rejected，无 tc_state_*。 */
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

  // 只标记 r1 被驳回，不注入 tc_state_r1 → 触发后端兜底恢复
  await page.addInitScript(() => {
    localStorage.setItem('tc_card_status', JSON.stringify({ r1: 'rejected' }))
  })

  const pageErrors = []
  page.on('pageerror', e => pageErrors.push('PAGEERROR: ' + String(e).slice(0, 300)))

  console.log('STEP1 登录 (1/111111)')
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForSelector('input[placeholder="用户名"]', { timeout: 30000 })
  await page.fill('input[placeholder="用户名"]', '1')
  await page.fill('input[placeholder="密码"]', '111111')
  await page.click('button:has-text("登录")')
  await page.waitForSelector('.dashboard .welcome h2:text("AI 需求助手")', { timeout: 30000 })
  await page.waitForTimeout(2500)
  await shot(page, '10-backend-rejected-dashboard.png')

  console.log('STEP2 点击被驳回的 tc 卡片（客户密码重置功能）')
  const tcPanel = page.locator('div.usecase-panel', { has: page.locator('.panel-title h3:text("测试用例流程")') })
  const card = tcPanel.locator('button.usecase-item', { has: page.locator('.usecase-text:text("客户密码重置功能")') })
  await card.waitFor({ timeout: 15000 })
  const statusIcon = await card.locator('.usecase-status').textContent().catch(() => '(无)')
  console.log('   卡片状态符号:', statusIcon)
  await card.click()
  await page.waitForURL(/\/test-case\/write/, { timeout: 30000 })

  // 等待后端异步恢复完成（同步会话 + 加载消息）
  console.log('STEP3 等待后端恢复 Agent3/Agent4 结果')
  await page.waitForSelector('.review-stage', { timeout: 30000 })
  await page.waitForSelector('.generation-stage', { timeout: 30000 })
  await page.waitForSelector('.decision.rejected', { timeout: 30000 })
  await page.waitForTimeout(1000)

  const reviewLen = (await page.locator('.review-stage').textContent()).length
  const genLen = (await page.locator('.generation-stage').textContent()).length
  const reviewHasReport = reviewLen > 200
  const genHasSteps = genLen > 200

  const rejectedCard = page.locator('.decision.rejected')
  const cardText = await rejectedCard.textContent()
  const hasRejectedText = cardText.includes('步骤已驳回')
  const regenBtn = rejectedCard.locator('button:has-text("重新生成")')
  const hasRegen = await regenBtn.count() > 0
  const strongBox = await rejectedCard.locator('strong').boundingBox()
  const btnBox = await regenBtn.boundingBox()
  const regenOnRight = strongBox && btnBox && btnBox.x > strongBox.x + strongBox.width

  console.log('   Agent3 评审报告恢复:', reviewHasReport, `(${reviewLen}字)`)
  console.log('   Agent4 生成步骤恢复:', genHasSteps, `(${genLen}字)`)
  console.log('   "步骤已驳回"卡片:', hasRejectedText)
  console.log('   "重新生成"按钮在右侧:', regenOnRight)
  await shot(page, '11-backend-rejected-restored.png')

  console.log('\n===== 汇总 =====')
  console.log('tc 卡片 ❌:', statusIcon.trim() === '❌')
  console.log('后端恢复 Agent3 结果:', reviewHasReport)
  console.log('后端恢复 Agent4 结果:', genHasSteps)
  console.log('步骤已驳回卡片 + 右侧重新生成按钮:', hasRejectedText && regenOnRight)
  console.log('页面异常:', pageErrors.length ? pageErrors : '无')
  console.log('截图目录:', SHOT_DIR)

  await browser.close()
  if (!reviewHasReport || !genHasSteps || !hasRejectedText || !regenOnRight) process.exitCode = 1
}

main().catch(e => { console.error('测试脚本异常:', e.message); process.exit(1) })
