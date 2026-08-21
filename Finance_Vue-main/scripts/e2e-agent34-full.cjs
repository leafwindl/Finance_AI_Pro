/* 端到端验证：Agent3 → Agent4 完整流程 */
const { chromium } = require('playwright-core')
const path = require('path'), fs = require('fs')
const BASE = 'http://127.0.0.1:5173'
const EDGE = 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe'
const SHOT_DIR = path.join(__dirname, '..', '..', '.runtime', 'screenshots')
fs.mkdirSync(SHOT_DIR, { recursive: true })
const shot = (page, name) => page.screenshot({ path: path.join(SHOT_DIR, name), fullPage: true })
const PID = 'e2e_test_' + Date.now()

async function main() {
  const browser = await chromium.launch({ executablePath: EDGE, headless: true, args: ['--no-sandbox', '--disable-gpu'] })
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await ctx.newPage()
  await page.addInitScript(() => { localStorage.clear() })
  const pageErrors = []; page.on('pageerror', e => pageErrors.push(String(e).slice(0, 500)))

  // 登录
  console.log('STEP1 登录')
  await page.goto(BASE, { waitUntil: 'domcontentloaded' })
  await page.waitForSelector('input[placeholder="用户名"]'); await page.fill('input[placeholder="用户名"]', '1'); await page.fill('input[placeholder="密码"]', '111111')
  await page.click('button:has-text("登录")'); await page.waitForSelector('.dashboard', { timeout: 20000 }); await page.waitForTimeout(2500)

  // 打开工作台
  const REQ = '客服后台支持授权客服人员直接重置客户交易密码。仅适用于已通过视频双录完成身份核验的场景。需关注合规风险与操作审计。'
  const url = `/test-case/write?title=客户密码重置功能&requirement=${encodeURIComponent(REQ)}&pid=${PID}`
  console.log('STEP2 工作台 pid:', PID); await page.goto(BASE + url, { waitUntil: 'domcontentloaded' }); await page.waitForSelector('.case-workbench'); await page.waitForTimeout(800)

  // 填表
  console.log('STEP3 填写'); const n = page.locator('input[placeholder*="例如"]').first()
  if (!(await n.inputValue())) await n.fill('交易密码重置成功流程')
  const mod = page.locator('.form-grid label').filter({ hasText: '所属模块' }).locator('.el-select'); await mod.click(); await page.waitForTimeout(300)
  const opt = page.locator('.el-select-dropdown__item').filter({ hasText: '权限校验' }).first()
  if (await opt.isVisible().catch(() => false)) await opt.click(); else await page.keyboard.press('Escape'); await page.waitForTimeout(200)
  const tObj = page.locator('.form-grid label').filter({ hasText: '测试场景' }).locator('textarea')
  if (!(await tObj.inputValue().catch(() => ''))) await tObj.fill('验证客服后台授权人员重置客户交易密码的完整流程')
  await page.waitForTimeout(300); await shot(page, '13-form.png')

  // Agent3
  console.log('STEP4 提交 → Agent3'); await page.click('button:has-text("提交智能评审")'); await page.waitForSelector('.review-stage', { timeout: 15000 })
  try { await page.waitForSelector('.review-stage .live-status', { timeout: 15000 }) } catch {}
  const rStart = Date.now()
  // 等报告出现
  await page.waitForSelector('.review-stage .markdown-body', { timeout: 300000 })
  console.log(`   报告出现（${((Date.now()-rStart)/1000).toFixed(0)}s），等待结论…`)
  // 等标签变化 或 人工通过按钮出现
  let passed = false
  try {
    await page.waitForFunction(() => {
      const t = document.querySelector('.review-stage .el-tag')
      return t && t.textContent.trim() !== '评审中'
    }, { timeout: 180000 })
    const tag = await page.locator('.review-stage .el-tag').first().textContent()
    passed = tag.trim() === '评审通过'
    console.log(`   结论: ${tag.trim()}`)
  } catch {
    passed = false; console.log('   标签未变化，设不通过')
  }
  // 兜底：看人工通过按钮
  const manualBtn = page.locator('button:has-text("人工通过并继续")')
  if (!passed && await manualBtn.isVisible().catch(() => false)) { passed = false; console.log('   人工通过按钮可见') }
  const rLen = (await page.locator('.review-stage .markdown-body').textContent().catch(() => '')).length
  console.log(`   Agent3 报告: ${rLen} 字`)
  await shot(page, '14-review.png')

  // 人工通过
  if (!passed) {
    console.log('STEP5 点击人工通过'); await manualBtn.waitFor({ timeout: 15000 }); await manualBtn.click(); console.log('   已点击')
  } else { console.log('STEP5 评审通过，Agent4 自动开始') }

  // Agent4
  console.log('STEP6 等待 Agent4…'); await page.waitForSelector('.generation-stage', { timeout: 30000 })
  console.log('   生成阶段出现，等待完成…'); const gStart = Date.now()
  // 等 report 出现 或 决策框出现
  try {
    await page.waitForFunction(() => {
      const art = document.querySelector('.generation-stage .generated-report')
      if (art && art.textContent.length > 100) return true
      return document.querySelector('.decision') !== null
    }, { timeout: 300000 })
  } catch { /* 超时也继续 */ }
  const gElapsed = ((Date.now() - gStart) / 1000).toFixed(0)
  const gLen = (await page.locator('.generation-stage .generated-report').textContent().catch(() => '')).length
  const dec = await page.locator('.decision').isVisible().catch(() => false)
  console.log(`   Agent4 (${gElapsed}s): ${gLen} 字, 决策卡: ${dec}`)
  await shot(page, '15-gen.png')

  console.log('\n===== 汇总 =====')
  console.log('Agent3 报告:', rLen, '字')
  console.log('Agent4 步骤:', gLen, '字')
  console.log('决策卡片:', dec)
  console.log('页面异常:', pageErrors.length ? pageErrors : '无')
  console.log('截图:', SHOT_DIR)
  await browser.close()
  if (rLen <= 50 || gLen <= 50 || !dec) process.exitCode = 1
}
main().catch(e => { console.error('异常:', e.message); process.exit(1) })
