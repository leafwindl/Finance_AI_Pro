<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import ForceGraph from 'force-graph'
import { useThemeStore } from '@/stores/theme'

const props = defineProps({
  graphData: { type: Object, required: true },
  selectedKb: { type: String, default: null },
})
const emit = defineEmits(['select-node'])

const themeStore = useThemeStore()
const containerRef = ref(null)
const size = ref({ width: 0, height: 0 })
let graph = null
let resizeObserver = null

const DOC_PALETTE = ['#3d90d6', '#7257d9', '#2f9e8f', '#c8781a', '#d05070', '#38a7c9']
const ENTITY_COLORS = { MODULE:'#3d90d6', REQUIREMENT:'#7257d9', BUSINESSRULE:'#2f9e8f', TESTCASE:'#c8781a', DEFECT:'#d05070', SECURITY:'#a83232', ACCOUNT:'#38a7c9', ERRORCODE:'#b070c0', PERMISSION:'#4a7dcf', OFFICIALRULE:'#5c7a99' }
const ENTITY_COLOR_DEFAULT = '#909399'

function getCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
function primaryColor() {
  return themeStore.isDark ? getCssVar('--el-color-primary-light-5') || '#6ab4e0' : getCssVar('--el-color-primary') || '#0f6cbd'
}
function labelColor() { return themeStore.isDark ? '#f2f6fc' : '#17212b' }
function labelOutline() { return themeStore.isDark ? 'rgba(20,28,40,.75)' : 'rgba(255,255,255,.85)' }
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '"':'&quot;' })[char])
}
function nodeId(value) { return typeof value === 'object' ? value?.id : value }
function findNode(id) { return (props.graphData?.nodes || []).find(node => node.id === id) }
function nodeVisible(node) { return props.selectedKb ? node.kb_code === props.selectedKb : node.type === 'kb' }
function linkVisible(link) {
  if (!props.selectedKb) return false
  const source = typeof link.source === 'object' ? link.source : findNode(link.source)
  const target = typeof link.target === 'object' ? link.target : findNode(link.target)
  return source?.kb_code === props.selectedKb && target?.kb_code === props.selectedKb
}
function linkColor(link) {
  if (link?.type === 'RELATED') return themeStore.isDark ? 'rgba(170,140,230,.5)' : 'rgba(114,87,217,.55)'
  if (link?.type === 'HAS_ENTITY') return themeStore.isDark ? 'rgba(230,170,90,.55)' : 'rgba(200,120,26,.5)'
  if (link?.type === 'PART_OF') return themeStore.isDark ? 'rgba(130,145,168,.4)' : 'rgba(110,132,156,.45)'
  return themeStore.isDark ? 'rgba(130,145,168,.55)' : 'rgba(110,132,156,.55)'
}
function linkDistance(link) {
  if (link.type === 'CONTAINS') return 90
  if (link.type === 'PART_OF') return 50
  if (link.type === 'HAS_ENTITY') return 40
  return 55
}
function nodeColorFor(node) {
  if (node.type === 'kb') return primaryColor()
  if (node.type === 'entity') return ENTITY_COLORS[node.entity_type] || ENTITY_COLOR_DEFAULT
  return DOC_PALETTE[(node.kb_code?.charCodeAt(2) || 0) % DOC_PALETTE.length]
}
function nodeLabel(node) {
  if (node.type === 'kb') return `<b>${escapeHtml(node.kb_code)} · ${escapeHtml(node.label)}</b><br/>${Number(node.count) || 0} 篇文档（点击展开）`
  if (node.type === 'entity') return `<b>${escapeHtml(node.name)}</b><br/><span style="opacity:.75">${escapeHtml(node.entity_type)}${node.description ? ' · ' + escapeHtml(String(node.description).slice(0, 120)) : ''}</span>`
  if (node.type === 'chunk') return `<b>${escapeHtml(node.label)}</b><br/><span style="opacity:.75">${escapeHtml(String(node.text || '').slice(0, 100))}</span>`
  return `<b>${escapeHtml(node.label)}</b><br/><span style="opacity:.75">${escapeHtml(node.kb_code)} · ${escapeHtml(node.source_file)}</span>`
}
function truncate(value, max) {
  const text = String(value || '')
  return text.length > max ? `${text.slice(0, max - 1)}…` : text
}
function paintLabel(ctx, text, x, y, fontSize, globalScale) {
  ctx.font = `600 ${fontSize / globalScale}px -apple-system, 'Segoe UI', sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.lineWidth = 2.5 / globalScale
  ctx.strokeStyle = labelOutline()
  ctx.strokeText(text, x, y)
  ctx.fillStyle = labelColor()
  ctx.fillText(text, x, y)
}
function roundRect(ctx, x, y, width, height, radius) {
  const r = Math.max(0, Math.min(radius, width / 2, height / 2))
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + width, y, x + width, y + height, r)
  ctx.arcTo(x + width, y + height, x, y + height, r)
  ctx.arcTo(x, y + height, x, y, r)
  ctx.arcTo(x, y, x + width, y, r)
  ctx.closePath()
}
function paintNode(node, ctx, globalScale) {
  const color = nodeColorFor(node)
  ctx.save()
  ctx.translate(node.x, node.y)
  if (node.type === 'kb') {
    const width = 116 / globalScale
    const height = 34 / globalScale
    roundRect(ctx, -width / 2, -height / 2, width, height, 9 / globalScale)
    ctx.fillStyle = color
    ctx.fill()
    ctx.strokeStyle = 'rgba(255,255,255,.85)'
    ctx.lineWidth = 1.6 / globalScale
    ctx.stroke()
    ctx.fillStyle = '#fff'
    ctx.font = `700 ${13 / globalScale}px -apple-system, 'Segoe UI', sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(node.kb_code, 0, -4 / globalScale)
    ctx.font = `400 ${10 / globalScale}px -apple-system, 'Segoe UI', sans-serif`
    ctx.fillText(`${Number(node.count) || 0} 篇文档`, 0, 11 / globalScale)
  } else if (node.type === 'entity') {
    const radius = 7 / globalScale
    ctx.beginPath(); ctx.moveTo(0, -radius); ctx.lineTo(radius, 0); ctx.lineTo(0, radius); ctx.lineTo(-radius, 0); ctx.closePath()
    ctx.fillStyle = color; ctx.fill(); ctx.strokeStyle = 'rgba(255,255,255,.9)'; ctx.lineWidth = 1.2 / globalScale; ctx.stroke()
    paintLabel(ctx, truncate(node.name, 12), 0, radius + 8 / globalScale, 10, globalScale)
  } else if (node.type === 'chunk') {
    const side = 11 / globalScale
    roundRect(ctx, -side / 2, -side / 2, side, side, 3 / globalScale)
    ctx.fillStyle = color; ctx.globalAlpha = .75; ctx.fill(); ctx.globalAlpha = 1; ctx.strokeStyle = 'rgba(255,255,255,.9)'; ctx.lineWidth = 1 / globalScale; ctx.stroke()
    paintLabel(ctx, truncate(node.label, 10), 0, side / 2 + 7 / globalScale, 9, globalScale)
  } else {
    const radius = 9 / globalScale
    ctx.beginPath(); ctx.arc(0, 0, radius, 0, Math.PI * 2); ctx.fillStyle = color; ctx.fill(); ctx.strokeStyle = 'rgba(255,255,255,.9)'; ctx.lineWidth = 1.2 / globalScale; ctx.stroke()
    paintLabel(ctx, truncate(node.label, 14), 0, radius + 9 / globalScale, 11, globalScale)
  }
  ctx.restore()
}
function buildGraph() {
  if (!containerRef.value || !size.value.width || !size.value.height) return
  graph?._destructor?.()
  containerRef.value.innerHTML = ''
  graph = ForceGraph()(containerRef.value)
    .graphData(props.graphData)
    .nodeId('id')
    .nodeLabel(nodeLabel)
    .nodeColor(nodeColorFor)
    .nodeCanvasObjectMode(() => 'replace')
    .nodeCanvasObject(paintNode)
    .nodeVisibility(nodeVisible)
    .linkVisibility(linkVisible)
    .linkColor(linkColor)
    .linkWidth(1.2)
    .linkLineDash(link => link?.type === 'RELATED' ? [4, 3] : null)
    .linkDirectionalArrowLength(5)
    .linkDirectionalArrowRelPos(1)
    .backgroundColor('transparent')
    .width(size.value.width)
    .height(size.value.height)
    .enableNodeDrag(true)
    .enableZoomInteraction(true)
    .enablePanInteraction(true)
    .d3VelocityDecay(.25)
    .warmupTicks(150)
    .cooldownTicks(400)
    .cooldownTime(20000)
    .onNodeClick((node, event) => emit('select-node', node, event))
  graph.d3Force('charge').strength(-200)
  graph.d3Force('link').distance(linkDistance)
  fitToView()
}
function refreshGraph() {
  if (!graph) { buildGraph(); return }
  graph.graphData(props.graphData)
  graph.nodeVisibility(nodeVisible)
  graph.linkVisibility(linkVisible)
  graph.refresh?.()
  fitToView()
}
function motionDuration() { return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 0 : 250 }
function fitToView() { graph?.zoomToFit(motionDuration(), 48, nodeVisible) }
function zoomIn() { graph?.zoom(graph.zoom() * 1.2, motionDuration()) }
function zoomOut() { graph?.zoom(graph.zoom() / 1.2, motionDuration()) }
defineExpose({ fitToView, zoomIn, zoomOut })

watch(() => props.graphData, refreshGraph, { deep: false })
watch(() => props.selectedKb, refreshGraph)
watch(() => themeStore.isDark, () => graph?.refresh?.())

onMounted(() => {
  resizeObserver = new ResizeObserver((entries) => {
    const rect = entries[0]?.contentRect
    if (!rect) return
    const changed = rect.width !== size.value.width || rect.height !== size.value.height
    size.value = { width: rect.width, height: rect.height }
    if (!graph && rect.width > 0 && rect.height > 0) buildGraph()
    else if (changed && graph) graph.width(rect.width).height(rect.height)
  })
  if (containerRef.value) resizeObserver.observe(containerRef.value)
})
onBeforeUnmount(() => { resizeObserver?.disconnect(); graph?._destructor?.(); graph = null })
</script>

<template>
  <div ref="containerRef" class="graph-canvas" role="img" aria-label="知识库、文档、分块与实体关系图；可使用右侧文件列表查看文档"></div>
</template>

<style scoped>
.graph-canvas { position:relative; width:100%; height:100%; min-height:0; }
.graph-canvas :deep(canvas) { display:block; }
</style>
