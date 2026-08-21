/**
 * 用户维度的 localStorage key 隔离工具。
 *
 * 背景：需求卡片状态（card_status / tc_card_status / tc_state_{pid}）与助手会话 ID
 * （agent5_conv_id）此前按浏览器全局存储，同一浏览器换账号登录后状态会跨用户残留。
 * 本工具在 key 中附加 user_id 后缀，使每个账号的状态相互隔离。
 *
 * 未登录时（user 为 null）统一落入 'anonymous' 作用域，仅作兜底；
 * 登录页面的守卫会在进入业务页前完成用户初始化，正常流程不会读到该作用域。
 */
import { useUserStore } from '@/stores/user'

function uid() {
  return useUserStore().user?.user_id || 'anonymous'
}

/** 基础 key 按用户隔离：`base__u_<user_id>` */
export function scopedKey(base) {
  return `${base}__u_${uid()}`
}

/** 带 pid 的 key 按用户隔离：`base_<pid>__u_<user_id>` */
export function scopedPidKey(base, pid) {
  return `${base}_${pid}__u_${uid()}`
}

/** 读取按用户隔离的 JSON 对象（形如 { [pid]: status } 的 map） */
export function readScopedMap(base) {
  try {
    return JSON.parse(localStorage.getItem(scopedKey(base)) || '{}')
  } catch {
    return {}
  }
}

/** 写入按用户隔离的 JSON 对象（map） */
export function writeScopedMap(base, map) {
  localStorage.setItem(scopedKey(base), JSON.stringify(map))
}
