/* 端到端验证：tc 面板被驳回步骤生成的用例（❌）→ 测试用例工作台应恢复
   Agent3/Agent4 已生成结果，且生成面板下方显示"步骤已驳回"卡片 + "重新生成"按钮。 */
const { chromium } = require('playwright-core')
const path = require('path')
const fs = require('fs')

const BASE = 'http://127.0.0.1:5173'
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const SHOT_DIR = path.join(__dirname, '..', '..', '.runtime', 'screenshots')
fs.mkdirSync(SHOT_DIR, { recursive: true })
const shot = (page, name) => page.screenshot({ path: path.join(SHOT_DIR, name) })

// 模拟 TestCaseEditor 曾跑完 Agent3(评审)+Agent4(步骤生成) 后点击"驳回"写入的状态
const SAVED_STATE = {
  form: {
    requirementName: '客户密码重置功能', title: '交易密码重置成功流程', module: '权限校验',
    preconditions: '客服人员已通过视频双录完成身份核验', testObjective: '验证客服后台授权人员重置客户交易密码的完整流程',
    testData: '有效客户编号、已核验身份', expected: '密码重置成功，系统记录操作审计日志'
  },
  reviewResult: '# 测试用例评审报告\n\n## 覆盖率\n- 功能覆盖：通过\n- 边界覆盖：通过\n\n## 评审结论\n建议通过',
  generatedResult: '# 交易密码重置成功流程 — 测试步骤\n\n## 1. 前置准备\n- 客服人员已通过视频双录身份核验\n\n## 2. 操作步骤\n1. 登录客服后台\n2. 定位客户交易密码重置入口\n3. 输入客户编号，校验身份\n4. 提交重置请求\n\n## 3. 预期结果\n- 密码重置成功，系统记录操作审计日志',
  stepApproved: false,
  reviewPassed: true,
  mode: 'generate'
}

async function main() {
  const browser = await chromium.launch({ executablePath: EDGE, headless: true, args: ['--no-sandbox', '--disable-gpu'] })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  await page.addInitScript((state) => {
    localStorage.setItem('tc_card_status', JSON.stringify({ r1: 'rejected' }))
    localStorage.setItem('tc_state_r1', JSON.stringify(state))
  }, SAVED_STATE)

  const pageErrors = []
  page.on('pageerror', e => pageErrors.push('PAGEERROR: ' + String(e).slice(0, 300)))

  // 1) 登录
  console.log('STEP1 登录 (1/111111)')
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 30000 })
  await page.waitForSelector('input[placeholder="用户名"]', { timeout: 30000 })
  await page.fill('input[placeholder="用户名"]', '1')
  await page.fill('input[placeholder="密码"]', '111111')
  await page.click('button:has-text("登录")')
  await page.waitForSelector('.dashboard .welcome h2:text("AI 需求助手")', { timeout: 30000 })
  await page.waitForTimeout(2500)
  await shot(page, '08-rejected-dashboard.png')

  // 2) 点击 tc 面板"客户密码重置功能"卡片（应为 ❌ 被驳回）
  console.log('STEP2 点击被驳回的 tc 卡片')
  const tcPanel = page.locator('div.usecase-panel', { has: page.locator('.panel-title h3:text("测试用例流程")') })
  const card = tcPanel.locator('button.usecase-item', { has: page.locator('.usecase-text:text("客户密码重置功能")') })
  await card.waitFor({ timeout: 15000 })
  const statusIcon = await card.locator('.usecase-status').textContent().catch(() => '(无)')
  console.log('   卡片状态符号:', statusIcon)
  await card.click()
  await page.waitForURL(/\/test-case\/write/, { timeout: 30000 })
  console.log('   工作台 URL:', page.url().slice(0, 120))

  // 3) 验证 Agent3 评审结果已恢复
  console.log('STEP3 验证 Agent3 评审结果恢复')
  await page.waitForSelector('.review-stage', { timeout: 15000 })
  const reviewStageText = await page.locator('.review-stage').textContent()
  const hasReview = reviewStageText.includes('测试用例评审报告') || reviewStageText.includes('评审结论')
  const reviewTag = await page.locator('.review-stage .stage-heading el-tag, .review-stage .stage-heading .el-tag').textContent().catch(() => '(无)')
  console.log('   Agent3 评审结果恢复:', hasReview)

  // 4) 验证 Agent4 生成结果 + "步骤已驳回"卡片 + "重新生成"按钮
  console.log('STEP4 验证 Agent4 生成结果与驳回态')
  await page.waitForSelector('.generation-stage', { timeout: 15000 })
  const genStageText = await page.locator('.generation-stage').textContent()
  const hasSteps = genStageText.includes('交易密码重置成功流程') && genStageText.includes('登录客服后台')
  const rejectedCard = page.locator('.decision.rejected')
  await rejectedCard.waitFor({ timeout: 15000 })
  const cardText = await rejectedCard.textContent()
  const hasRejectedText = cardText.includes('步骤已驳回')
  const regenBtn = rejectedCard.locator('button:has-text("重新生成")')
  const hasRegen = await regenBtn.count() > 0
  // "重新生成"按钮在卡片右侧
  const strongBox = await rejectedCard.locator('strong').boundingBox()
  const btnBox = await regenBtn.boundingBox()
  const regenOnRight = strongBox && btnBox && btnBox.x > strongBox.x + strongBox.width
  console.log('   Agent4 生成结果恢复:', hasSteps)
  console.log('   "步骤已驳回"卡片:', hasRejectedText)
  console.log('   "重新生成"按钮在卡片右侧:', regenOnRight)
  await shot(page, '09-rejected-workbench-restored.png')

  // 5) 汇总
  console.log('\n===== 汇总 =====')
  console.log('tc 卡片 ❌ 被驳回:', statusIcon.trim() === '❌')
  console.log('Agent3 评审结果恢复:', hasReview)
  console.log('Agent4 生成结果恢复:', hasSteps)
  console.log('步骤已驳回卡片 + 右侧重新生成按钮:', hasRejectedText && regenOnRight)
  console.log('页面异常:', pageErrors.length ? pageErrors : '无')
  console.log('截图目录:', SHOT_DIR)

  await browser.close()
  if (!hasReview || !hasSteps || !hasRejectedText || !regenOnRight) process.exitCode = 1
}

main().catch(e => { console.error('测试脚本异常:', e.message); process.exit(1) })
