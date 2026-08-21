<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import {
  fetchKnowledgeGraph,
  listKbDocuments,
  fetchDocumentContent,
  fetchDocumentSubgraph,
} from '@/services/api/knowledge'
import KnowledgeGraphCanvas from '@/components/knowledge/KnowledgeGraphCanvas.vue'
import KnowledgeFilePanel from '@/components/knowledge/KnowledgeFilePanel.vue'
import KnowledgeDocContent from '@/components/knowledge/KnowledgeDocContent.vue'
import KbUploadDropzone from '@/components/KbUploadDropzone.vue'
import { renderMarkdown } from '@/composables/useMarkdown'

const baseGraph = ref({ nodes: [], links: [] }) // 原始两级图（KB + 文件）
const graphData = ref({ nodes: [], links: [] }) // 画布当前数据（含展开的子图）
const graphLoading = ref(true)
const graphError = ref('')

const selectedKb = ref(null)
const panelView = ref('files') // files | content | chunk | entity
const documents = ref([])
const filesLoading = ref(false)
const filesError = ref('')
const currentDoc = ref(null)
const contentLoading = ref(false)
const contentError = ref('')
const currentChunk = ref(null)
const currentEntity = ref(null)
const subgraphError = ref('')
const subgraphLoading = ref(new Set())
const graphCanvas = ref(null)

let graphController = null
let filesController = null
let contentController = null
const subgraphControllers = new Map()
let graphRequestId = 0
let filesRequestId = 0
let contentRequestId = 0

// 展开状态：docId -> 子图数据；每次变化后从 baseGraph 重建画布数据
const subgraphs = new Map()
const expandedDocs = ref(new Set())

// force-graph 会就地变异 graphData（links 的 source/target 替换为节点对象、
// 节点附加 x/y 等内部属性），缓存层必须始终保存干净克隆，重建时复制新对象。
function cloneGraph(g) {
  return {
    nodes: (g?.nodes || []).map((n) => ({ ...n })),
    links: (g?.links || []).map((l) => ({ ...l })),
  }
}

// 初始布局：KB 节点固定在圆周上彼此分开；文档均匀散布在所属 KB 周围的
// 同心环带上（点选 KB 后才显示，不会与其他库的文档交叉重叠）。
function initLayout(g) {
  const kbNodes = g.nodes.filter((n) => n.type === 'kb')
  // 半径随 KB 数量增长，避免库多了圆环上挤不下
  const kbRadius = 160 + Math.max(0, kbNodes.length - 6) * 12
  kbNodes.forEach((n, i) => {
    const angle = (i / Math.max(kbNodes.length, 1)) * Math.PI * 2 - Math.PI / 2
    n.fx = Math.cos(angle) * kbRadius
    n.fy = Math.sin(angle) * kbRadius
    n.x = n.fx
    n.y = n.fy
  })
  const docsByKb = {}
  for (const n of g.nodes) {
    if (n.type !== 'doc') continue
    ;(docsByKb[n.kb_code] ||= []).push(n)
  }
  const perRing = 16
  for (const [kbCode, docs] of Object.entries(docsByKb)) {
    const kb = kbNodes.find((k) => k.kb_code === kbCode)
    if (!kb) continue
    docs.forEach((n, idx) => {
      const ring = Math.floor(idx / perRing)
      const posInRing = idx % perRing
      const count = Math.min(perRing, docs.length - ring * perRing)
      const angle = (posInRing / Math.max(count, 1)) * Math.PI * 2
      const radius = 110 + ring * 50
      n.x = kb.x + Math.cos(angle) * radius
      n.y = kb.y + Math.sin(angle) * radius
    })
  }
}

function nodeId(value) {
  return typeof value === 'object' ? value?.id : value
}

function validateGraph(value, label = '知识图谱') {
  if (!value || !Array.isArray(value.nodes) || !Array.isArray(value.links)) {
    throw new Error(`${label}接口响应格式不正确`)
  }
  const ids = new Set()
  for (const node of value.nodes) {
    if (!node || typeof node.id !== 'string' || !node.id || typeof node.type !== 'string') {
      throw new Error(`${label}包含无效节点`)
    }
    if (ids.has(node.id)) throw new Error(`${label}包含重复节点：${node.id}`)
    ids.add(node.id)
  }
  for (const link of value.links) {
    if (!link || typeof nodeId(link.source) !== 'string' || typeof nodeId(link.target) !== 'string') {
      throw new Error(`${label}包含无效关系`)
    }
  }
  return value
}

function stableRatio(value) {
  let hash = 0
  for (const char of String(value || '')) hash = (hash * 31 + char.charCodeAt(0)) >>> 0
  return (hash % 10000) / 10000
}

// 子图节点（分块/实体）按稳定 ID 散布在所属文档周围，刷新时布局可复现。
function initSubgraphLayout(sub, docNode) {
  for (const n of sub.nodes) {
    const ratio = stableRatio(n.id)
    const angle = ratio * Math.PI * 2
    const dist = 50 + stableRatio(`${n.id}:distance`) * 130
    n.x = (docNode ? docNode.x : 0) + Math.cos(angle) * dist
    n.y = (docNode ? docNode.y : 0) + Math.sin(angle) * dist
  }
}

const kbNode = computed(() =>
  graphData.value.nodes.find((n) => n.type === 'kb' && n.kb_code === selectedKb.value) || null
)
const hasSelection = computed(() => !!selectedKb.value)

// 当前实体的相邻实体（按 RELATED 边在画布数据中查找）
const relatedEntities = computed(() => {
  const entity = currentEntity.value
  if (!entity) return []
  const nodeMap = new Map(graphData.value.nodes.map((n) => [n.id, n]))
  const neighbors = []
  for (const link of graphData.value.links) {
    if (link.type !== 'RELATED') continue
    // force-graph 可能已把 source/target 替换为节点对象引用
    const src = typeof link.source === 'object' ? link.source?.id : link.source
    const tgt = typeof link.target === 'object' ? link.target?.id : link.target
    const other = src === entity.id ? tgt : tgt === entity.id ? src : null
    if (other && !neighbors.some((n) => n.id === other)) {
      const node = nodeMap.get(other)
      if (node) neighbors.push(node)
    }
  }
  return neighbors
})

async function loadGraph() {
  const requestId = ++graphRequestId
  graphController?.abort()
  graphController = new AbortController()
  graphLoading.value = true
  graphError.value = ''
  try {
    const data = validateGraph(await fetchKnowledgeGraph({ signal: graphController.signal }))
    if (requestId !== graphRequestId) return
    baseGraph.value = cloneGraph(data)
    initLayout(baseGraph.value)
    subgraphs.clear()
    expandedDocs.value = new Set()
    rebuildGraph()
    resetSelection()
  } catch (e) {
    if (e.name !== 'AbortError' && requestId === graphRequestId) graphError.value = e.message || '加载图谱失败'
  } finally {
    if (requestId === graphRequestId) graphLoading.value = false
  }
}

function rebuildGraph() {
  const nodes = baseGraph.value.nodes.map((n) => ({ ...n }))
  const links = baseGraph.value.links.map((l) => ({ ...l }))
  const seen = new Set(nodes.map((n) => n.id))
  const linkKeys = new Set(links.map((l) => `${nodeId(l.source)}|${l.type || ''}|${nodeId(l.target)}`))
  for (const docId of expandedDocs.value) {
    const sub = subgraphs.get(docId)
    if (!sub) continue
    for (const n of sub.nodes) {
      if (!seen.has(n.id)) { nodes.push({ ...n }); seen.add(n.id) }
    }
    for (const l of sub.links) {
      const key = `${nodeId(l.source)}|${l.type || ''}|${nodeId(l.target)}`
      if (!linkKeys.has(key)) { links.push({ ...l }); linkKeys.add(key) }
    }
  }
  graphData.value = { nodes, links }
}

async function toggleDocExpansion(node) {
  const docId = node.doc_id
  if (!docId) return
  if (expandedDocs.value.has(docId)) {
    expandedDocs.value.delete(docId)
    subgraphs.delete(docId)
    subgraphControllers.get(docId)?.abort()
    subgraphControllers.delete(docId)
    subgraphLoading.value = new Set(subgraphLoading.value)
    subgraphLoading.value.delete(docId)
    rebuildGraph()
    return
  }
  if (subgraphLoading.value.has(docId)) return
  const controller = new AbortController()
  subgraphControllers.set(docId, controller)
  const nextLoading = new Set(subgraphLoading.value)
  nextLoading.add(docId)
  subgraphLoading.value = nextLoading
  subgraphError.value = ''
  try {
    const sub = validateGraph(await fetchDocumentSubgraph(docId, { signal: controller.signal }), '文档子图')
    if (subgraphControllers.get(docId) !== controller || !subgraphLoading.value.has(docId)) return
    const clean = cloneGraph(sub)
    const docNode = baseGraph.value.nodes.find((n) => n.doc_id === docId)
    initSubgraphLayout(clean, docNode)
    subgraphs.set(docId, clean)
    expandedDocs.value.add(docId)
    rebuildGraph()
  } catch (e) {
    if (e.name !== 'AbortError') subgraphError.value = e.message || '加载文档子图失败'
  } finally {
    if (subgraphControllers.get(docId) === controller) {
      subgraphControllers.delete(docId)
      const done = new Set(subgraphLoading.value)
      done.delete(docId)
      subgraphLoading.value = done
    }
  }
}

async function selectKb(node) {
  const requestId = ++filesRequestId
  filesController?.abort()
  filesController = new AbortController()
  contentController?.abort()
  selectedKb.value = node.kb_code
  panelView.value = 'files'
  currentDoc.value = null
  currentChunk.value = null
  currentEntity.value = null
  contentError.value = ''
  documents.value = []
  filesError.value = ''
  filesLoading.value = true
  try {
    const res = await listKbDocuments(node.kb_code, { signal: filesController.signal })
    if (requestId !== filesRequestId) return
    if (!Array.isArray(res?.documents)) throw new Error('文件列表接口响应格式不正确')
    documents.value = res.documents
  } catch (e) {
    if (e.name !== 'AbortError' && requestId === filesRequestId) filesError.value = e.message || '加载文件列表失败'
  } finally {
    if (requestId === filesRequestId) filesLoading.value = false
  }
}

async function openDoc(doc) {
  const requestId = ++contentRequestId
  contentController?.abort()
  contentController = new AbortController()
  panelView.value = 'content'
  currentDoc.value = { doc_id: doc.doc_id, title: doc.title, kb_code: doc.kb_code, source_file: doc.source_file, chunk_count: doc.chunk_count }
  contentError.value = ''
  contentLoading.value = true
  toggleDocExpansion({ ...doc, doc_id: doc.doc_id })
  try {
    if (!doc?.doc_id) throw new Error('文档 ID 无效')
    const result = await fetchDocumentContent(doc.doc_id, { signal: contentController.signal })
    if (typeof result?.content_markdown !== 'string') throw new Error('文档内容接口响应格式不正确')
    if (requestId === contentRequestId) currentDoc.value = result
  } catch (e) {
    if (e.name !== 'AbortError' && requestId === contentRequestId) contentError.value = e.message || '加载文件内容失败'
  } finally {
    if (requestId === contentRequestId) contentLoading.value = false
  }
}

function showChunk(node) {
  panelView.value = 'chunk'
  currentChunk.value = node
}

function showEntity(node) {
  panelView.value = 'entity'
  currentEntity.value = node
}

function resetSelection() {
  selectedKb.value = null
  panelView.value = 'files'
  documents.value = []
  filesError.value = ''
  currentDoc.value = null
  currentChunk.value = null
  currentEntity.value = null
  contentError.value = ''
  contentController?.abort()
  filesController?.abort()
  for (const controller of subgraphControllers.values()) controller.abort()
  subgraphControllers.clear()
  subgraphLoading.value = new Set()
  subgraphError.value = ''
}

function onSelectNode(node) {
  if (node.type === 'kb') {
    selectKb(node)
  } else if (node.type === 'doc') {
    openDoc(node)
  } else if (node.type === 'chunk') {
    showChunk(node)
  } else if (node.type === 'entity') {
    showEntity(node)
  }
}

function retryCurrentDoc() {
  if (currentDoc.value?.doc_id) openDoc(currentDoc.value)
}

onMounted(loadGraph)
onBeforeUnmount(() => {
  graphController?.abort()
  filesController?.abort()
  contentController?.abort()
  for (const controller of subgraphControllers.values()) controller.abort()
  subgraphControllers.clear()
})
</script>

<template>
  <div class="graph-view">
    <!-- 页面标题 + 工具栏 -->
    <header class="graph-head">
      <div class="head-left">
        <span class="eyebrow">KNOWLEDGE GRAPH</span>
        <h1>知识图谱</h1>
      </div>
      <div class="head-right">
        <el-tag v-if="kbNode" type="primary" effect="dark" class="sel-tag">
          已聚焦：{{ selectedKb }} · {{ kbNode.label }}
        </el-tag>
        <el-tag v-if="hasSelection" class="hint-tag">画布已仅显示当前知识库</el-tag>
        <el-button
          v-if="hasSelection"
          size="small"
          @click="resetSelection"
        >
          <el-icon><RefreshLeft /></el-icon> 重置视图
        </el-button>
        <el-button-group>
          <el-button size="small" aria-label="缩小图谱" @click="graphCanvas?.zoomOut()"><el-icon><Minus /></el-icon></el-button>
          <el-button size="small" aria-label="适配图谱视图" @click="graphCanvas?.fitToView()"><el-icon><FullScreen /></el-icon></el-button>
          <el-button size="small" aria-label="放大图谱" @click="graphCanvas?.zoomIn()"><el-icon><Plus /></el-icon></el-button>
        </el-button-group>
        <el-button size="small" text @click="loadGraph">
          <el-icon><Refresh /></el-icon> 刷新数据
        </el-button>
      </div>
    </header>

    <!-- 加载中 / 错误 -->
    <div v-if="graphLoading" class="full-state">
      <el-icon :size="30" class="is-loading"><Loading /></el-icon>
      <span>正在加载知识图谱…</span>
    </div>
    <div v-else-if="graphError" class="full-state error">
      <el-icon :size="34"><WarningFilled /></el-icon>
      <strong>图谱加载失败</strong>
      <span class="err-detail">{{ graphError }}</span>
      <span class="err-hint">知识图谱服务暂不可用，请稍后重试；若持续失败，请联系服务端维护人员。</span>
      <el-button type="primary" @click="loadGraph">重试</el-button>
    </div>

    <!-- 图谱 + 右侧面板 -->
    <div v-else class="graph-main">
      <div class="canvas-card">
        <KnowledgeGraphCanvas
          ref="graphCanvas"
          :graph-data="graphData"
          :selected-kb="selectedKb"
          @select-node="onSelectNode"
        />
        <div v-if="!graphData.nodes.length" class="canvas-empty">
          <el-empty description="图谱暂无数据" :image-size="90" />
        </div>
        <!-- 图例 -->
        <div class="legend">
          <span class="lg-item"><i class="dot kb-dot"></i>知识库</span>
          <span class="lg-item"><i class="dot doc-dot"></i>文件</span>
          <span class="lg-item"><i class="dot chunk-dot"></i>分块</span>
          <span class="lg-item"><i class="dot entity-dot"></i>实体</span>
        </div>
      </div>

      <aside class="side-panel">
        <el-alert
          v-if="subgraphError"
          class="subgraph-alert"
          type="warning"
          :title="`文档关系图加载失败：${subgraphError}`"
          show-icon
          closable
          @close="subgraphError = ''"
        />
        <!-- 文件列表（选中知识库后） -->
        <KnowledgeFilePanel
          v-if="panelView === 'files' && hasSelection"
          :kb-code="selectedKb"
          :kb-name="kbNode?.label"
          :doc-count="documents.length"
          :documents="documents"
          :loading="filesLoading"
          :error="filesError"
          @select-doc="openDoc"
          @back="resetSelection"
          @retry="selectKb({ kb_code: selectedKb })"
        />

        <KnowledgeDocContent
          v-else-if="panelView === 'content'"
          :doc="currentDoc"
          :loading="contentLoading"
          :error="contentError"
          @show-files="panelView = 'files'"
          @back="resetSelection"
          @retry="retryCurrentDoc"
        />

        <!-- 分块详情 -->
        <section v-else-if="panelView === 'chunk' && currentChunk" class="detail-panel">
          <header class="detail-head">
            <div class="detail-icon chunk-bg"><el-icon><Memo /></el-icon></div>
            <div class="head-text">
              <span class="eyebrow">KNOWLEDGE CHUNK</span>
              <h3>{{ currentChunk.label }}</h3>
            </div>
            <el-button size="small" text @click="panelView = currentDoc ? 'content' : 'files'">
              <el-icon><Back /></el-icon> 返回
            </el-button>
          </header>
          <div class="detail-body">
            <article
              class="markdown-body"
              v-html="renderMarkdown(currentChunk.text || '')"
            />
          </div>
        </section>

        <!-- 实体详情 -->
        <section v-else-if="panelView === 'entity' && currentEntity" class="detail-panel">
          <header class="detail-head">
            <div class="detail-icon entity-bg"><el-icon><Connection /></el-icon></div>
            <div class="head-text">
              <span class="eyebrow">KNOWLEDGE ENTITY</span>
              <h3>{{ currentEntity.name }}</h3>
              <div class="meta">
                <el-tag size="small" effect="plain">{{ currentEntity.entity_type }}</el-tag>
              </div>
            </div>
            <el-button size="small" text @click="panelView = currentDoc ? 'content' : 'files'">
              <el-icon><Back /></el-icon> 返回
            </el-button>
          </header>
          <div class="detail-body">
            <p class="entity-desc">{{ currentEntity.description || '（无描述）' }}</p>
            <template v-if="relatedEntities.length">
              <div class="rel-title">关联实体</div>
              <ul class="rel-list">
                <li
                  v-for="rel in relatedEntities"
                  :key="rel.id"
                  class="rel-item"
                  role="button"
                  tabindex="0"
                  @click="showEntity(rel)"
                  @keydown.enter="showEntity(rel)"
                >
                  <i class="dot entity-dot"></i>{{ rel.name }}
                  <span class="rel-type">{{ rel.entity_type }}</span>
                </li>
              </ul>
            </template>
          </div>
        </section>

        <!-- 未选中知识库：指引（兜底） -->
        <section v-else class="guide-panel">
          <div class="guide-icon">
            <el-icon :size="30"><Share /></el-icon>
          </div>
          <h3>探索知识图谱</h3>
          <p>点击图中<b>蓝色知识库节点</b>，展开该库的文件图谱；在右侧列表点文件可阅读全文。</p>
          <p>图上点文件节点会继续展开其<b>分块与实体</b>；点分块看片段，点实体看描述与关联。</p>
          <p class="guide-tip">支持鼠标拖拽移动节点、滚轮缩放画布。</p>
        </section>
      </aside>
    </div>

    <!-- 知识库文档上传（页面下方） -->
    <div class="graph-upload">
      <KbUploadDropzone />
    </div>
  </div>
</template>

<style scoped>
.graph-view {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 26px 28px 24px;
  background:
    radial-gradient(circle at 12% 0, rgba(15, 108, 189, 0.09), transparent 34%),
    radial-gradient(circle at 92% 10%, rgba(61, 144, 214, 0.06), transparent 28%),
    var(--el-bg-color-page);
}

.graph-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 20px;
  flex-shrink: 0;
  padding: 2px 2px 14px;
}
.head-left .eyebrow {
  color: var(--el-color-primary);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.15em;
}
.head-left h1 {
  margin: 5px 0 0;
  color: var(--el-text-color-primary);
  font-size: 26px;
  line-height: 1.25;
}
.head-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.sel-tag { margin-right: 2px; }
.hint-tag { opacity: 0.85; }

/* 全屏状态 */
.full-state {
  display: flex;
  flex: 1;
  min-height: 0;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 12px;
  color: var(--el-text-color-placeholder);
}
.full-state.error {
  color: var(--el-color-danger);
}
.full-state.error strong {
  color: var(--el-text-color-secondary);
  font-size: 16px;
}
.full-state.error .err-detail {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.full-state.error .err-hint {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
}

/* 主区 */
.graph-main {
  flex: 1;
  min-height: 0;
  display: flex;
  gap: 16px;
}
.graph-upload {
  flex-shrink: 0;
  margin-top: 16px;
}
.graph-upload:deep(.kb-dropzone) {
  padding: 18px 24px;
}
.canvas-card {
  position: relative;
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  background: var(--el-bg-color);
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.07);
}
.canvas-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.legend {
  position: absolute;
  left: 14px;
  bottom: 12px;
  display: flex;
  gap: 16px;
  padding: 7px 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 999px;
  background: color-mix(in srgb, var(--el-bg-color) 88%, transparent);
  backdrop-filter: blur(8px);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.lg-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  display: inline-block;
}
.kb-dot {
  background: var(--el-color-primary);
  border-radius: 3px;
}
.doc-dot { background: #7257d9; }
.chunk-dot {
  width: 8px;
  height: 8px;
  background: #3d90d6;
  border-radius: 2px;
  opacity: 0.85;
}
.entity-dot {
  background: #2f9e8f;
  border-radius: 1px;
  transform: rotate(45deg);
}

/* 右侧面板 */
.side-panel {
  position: relative;
  width: 384px;
  flex-shrink: 0;
  min-height: 0;
}
.subgraph-alert {
  position: absolute;
  z-index: 2;
  top: 8px;
  right: 8px;
  left: 8px;
}
.guide-panel {
  display: flex;
  height: 100%;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 10px;
  padding: 28px;
  text-align: center;
  border: 1px dashed var(--el-border-color);
  border-radius: 16px;
  background: var(--el-bg-color);
  color: var(--el-text-color-secondary);
  font-size: 13px;
  line-height: 1.7;
}
.guide-icon {
  display: grid;
  width: 64px;
  height: 64px;
  color: #fff;
  border-radius: 18px;
  background: linear-gradient(135deg, #0f6cbd, #3d90d6);
  box-shadow: 0 10px 24px rgba(15, 108, 189, 0.3);
  place-items: center;
}
.guide-panel h3 {
  margin: 6px 0 0;
  color: var(--el-text-color-primary);
  font-size: 18px;
}
.guide-tip {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

/* 分块 / 实体详情面板 */
.detail-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  background: var(--el-bg-color);
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.07);
}
.detail-head {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--el-border-color-extra-light);
  flex-shrink: 0;
}
.detail-head .eyebrow {
  display: block;
  margin-bottom: 3px;
  color: var(--el-color-primary);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.15em;
}
.detail-head h3 {
  margin: 0;
  color: var(--el-text-color-primary);
  font-size: 16px;
  line-height: 1.3;
  word-break: break-all;
}
.detail-icon {
  display: grid;
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  color: #fff;
  border-radius: 12px;
  place-items: center;
}
.chunk-bg {
  background: linear-gradient(135deg, #3d90d6, #2f9e8f);
  box-shadow: 0 6px 16px rgba(61, 144, 214, 0.28);
}
.entity-bg {
  background: linear-gradient(135deg, #2f9e8f, #3d90d6);
  box-shadow: 0 6px 16px rgba(47, 158, 143, 0.28);
}
.head-text {
  flex: 1;
  min-width: 0;
}
.head-text .meta {
  margin-top: 8px;
}
.detail-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px 16px 18px;
}
.detail-body .markdown-body {
  color: var(--el-text-color-regular);
  font-size: 13.5px;
  line-height: 1.7;
  word-break: break-word;
}
.entity-desc {
  margin: 0;
  color: var(--el-text-color-regular);
  font-size: 13.5px;
  line-height: 1.7;
}
.rel-title {
  margin: 18px 0 8px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.06em;
}
.rel-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rel-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 12px;
  border-radius: 9px;
  cursor: pointer;
  color: var(--el-text-color-primary);
  font-size: 13px;
  transition: background 0.15s;
}
.rel-item:hover {
  background: var(--el-fill-color-light);
}
.rel-item .rel-type {
  margin-left: auto;
  color: var(--el-text-color-placeholder);
  font-size: 11px;
}

@media (max-width: 1200px) {
  .graph-head { align-items: flex-start; flex-direction: column; }
  .head-right { flex-wrap: wrap; }
  .graph-main { flex-direction: column; overflow-y: auto; }
  .canvas-card { flex: 0 0 420px; min-height: 360px; }
  .side-panel { width: 100%; min-height: 360px; }
}
@media (max-width: 560px) {
  .graph-view { padding: 16px 12px; }
  .head-right { width: 100%; }
  .canvas-card { flex-basis: 360px; }
  .legend { right: 10px; flex-wrap: wrap; border-radius: 12px; }
}
</style>