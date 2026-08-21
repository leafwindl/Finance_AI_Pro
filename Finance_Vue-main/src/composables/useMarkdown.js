import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'

// ---- marked 配置 ----
marked.use({
  // GFM 扩展：break、表格、任务列表等
  extensions: [],
  gfm: true,
  breaks: true,
})

// 自定义渲染器：代码高亮 + 链接新窗口
marked.use({
  renderer: {
    // 代码块高亮 + 语言标签
    code({ text, lang: language }) {
      const langLabel = language ? `<span class="code-lang">${language}</span>` : ''
      if (language && hljs.getLanguage(language)) {
        try {
          const highlighted = hljs.highlight(text, { language }).value
          return `<pre>${langLabel}<code class="hljs language-${language}">${highlighted}</code></pre>\n`
        } catch {}
      }
      return `<pre>${langLabel}<code>${text}</code></pre>\n`
    },
    // 链接新窗口打开
    link({ href, title, text }) {
      return `<a href="${href}" target="_blank" rel="noopener noreferrer"${title ? ` title="${title}"` : ''}>${text}</a>`
    }
  }
})

/**
 * 将 Markdown 渲染为安全的 HTML
 * @param {string} content
 * @returns {string}
 */
export function renderMarkdown(content) {
  if (!content) return ''
  try {
    const rawHtml = marked.parse(content)
    return DOMPurify.sanitize(rawHtml, {
      ADD_ATTR: ['class', 'target', 'rel'],
      ALLOW_DATA_ATTR: false,
    })
  } catch {
    return escapeHtml(content)
  }
}

function escapeHtml(text) {
  const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }
  return String(text).replace(/[&<>"']/g, m => map[m])
}
