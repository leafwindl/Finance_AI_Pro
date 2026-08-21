import { ref, onUnmounted } from 'vue'

/**
 * 打字机效果：将 source 中的文本逐字搬运到 display，产生逐字输出效果。
 *
 * 自适应速度：落后超过 30 字时自动加速，落后较少时正常速度。
 * 流结束时无需手动 flush——source 停止增长后打字机会自动追完。
 *
 * @param {number} speed  正常速度（ms/字），默认 30
 * @returns {{ source, display, isActive, start, reset }}
 */
export function useTypewriter(speed = 30) {
  const source = ref('')    // 原始完整文本（SSE 累积写入）
  const display = ref('')   // 已打出的文本（绑定到 UI）
  const isActive = ref(false)

  let timer = null
  let pos = 0

  function tick() {
    if (pos >= source.value.length) {
      // source 停止增长了（流已结束），打字机也刚好跑完
      isActive.value = false
      timer = null
      return
    }

    // 自适应速度：落后超过 30 字则加速
    const behind = source.value.length - pos
    const currentSpeed = behind > 30 ? Math.max(8, Math.floor(speed / 3)) : speed

    pos++
    display.value = source.value.slice(0, pos)
    timer = setTimeout(tick, currentSpeed)
  }

  /** 开始 / 恢复打字 */
  function start() {
    if (timer) return          // 已在运行
    if (pos >= source.value.length) return // 已打完
    isActive.value = true
    tick()
  }

  /** 重置所有状态 */
  function reset() {
    clearTimeout(timer)
    timer = null
    pos = 0
    source.value = ''
    display.value = ''
    isActive.value = false
  }

  onUnmounted(() => clearTimeout(timer))

  return { source, display, isActive, start, reset }
}
