/* 端到端验证：浏览器存在"坏缓存"（stepApproved=false 但 generatedResult 为空）时，
   应自动清除缓存并走后端恢复 Agent3 + Agent4，而非只显示 Agent3。 */
const { chromium } = require('playwright-core')
const path = require('path')
const fs = require('fs')

const BASE = 'http://127.0.0.1:5173'
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const SHOT_DIR = path.join(__dirname, '..', '..', '.runtime', 'screenshots')
fs.mkdirSync(SHOT_DIR, { recursive: true })
const shot = (page, name) => page.screenshot({ path: path.join(SHOT_DIR, name) })

// 模拟旧版兜底逻辑写入的坏缓存：只有 Agent3 评审、无 Agent4 生成、stepApproved=false
const BAD_STATE = {
  form: { requirementName: '客户密码重置功能', title: '交易密码重置流程', module: '', preconditions: '', testObjective: '', testData: '', expected: '' },
  reviewResult: '# 测试用例评审报告\n\n## 评审结论\n建议通过',
  generatedResult: '',
  stepApproved: false,
  reviewPassed: true,
  mode: 'review'
}

async function main() {
  const browser = await chromium.launch({ executablePath: EDGE, headless: true, args: ['--no-sandbox', '--disable-gpu'] })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()

  await page.addInitScript((state) => {
    localStorage.setItem('tc_card_status', JSON.stringify({ r1: 'rejected' }))
    localStorage.setItem('tc_state_r1', JSON.stringify(state))
  }, BAD_STATE)

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

  console.log('STEP2 点击被驳回卡片')
  const tcPanel = page.locator('div.usecase-panel', { has: page.locator('.panel-title h3:text("测试用例流程")') })
  const card = tcPanel.locator('button.usecase-item', { has: page.locator('.usecase-text:text("客户密码重置功能")') })
  await card.waitFor({ timeout: 15000 })
  await card.click()
  await page.waitForURL(/\/test-case\/write/, { timeout: 30000 })

  console.log('STEP3 等待后端恢复（坏缓存应被清除）')
  await page.waitForSelector('.generation-stage', { timeout: 30000 })
  await page.waitForSelector('.decision.rejected', { timeout: 30000 })
  await page.waitForTimeout(800)

  const genLen = (await page.locator('.generation-stage').textContent()).length
  const hasSteps = genLen > 200
  const hasRejected = (await page.locator('.decision.rejected').textContent()).includes('步骤已驳回')
  const hasRegen = await page.locator('.decision.rejected button:has-text("重新生成")').count() > 0
  // 确认坏缓存已被清除（localStorage 不再有旧 stepApproved=false + 空 generatedResult）
  const stateNow = await page.evaluate(() => localStorage.getItem('tc_state_r1'))
  const cleared = !stateNow || JSON.parse(stateNow).generatedResult !== ''

  console.log('   Agent4 生成步骤恢复:', hasSteps, `(${genLen}字)`)
  console.log('   "步骤已驳回"卡片:', hasRejected)
  console.log('   "重新生成"按钮:', hasRegen)
  console.log('   坏缓存已清除:', cleared)
  await shot(page, '12-stale-cache-recovered.png')

  console.log('\n===== 汇总 =====')
  console.log('坏缓存场景 → Agent4 恢复:', hasSteps)
  console.log('坏缓存自动清除:', cleared)
  console.log('步骤已驳回 + 重新生成:', hasRejected && hasRegen)
  console.log('页面异常:', pageErrors.length ? pageErrors : '无')

  await browser.close()
  if (!hasSteps || !cleared || !hasRejected || !hasRegen) process.exitCode = 1
}

main().catch(e => { console.error('测试脚本异常:', e.message); process.exit(1) })
