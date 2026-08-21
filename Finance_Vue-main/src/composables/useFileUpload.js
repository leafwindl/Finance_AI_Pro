import { ref, computed, reactive } from 'vue'
import { uploadFile } from '@/services/api'

const ALLOWED_EXTENSIONS = [
  '.pdf', '.docx', '.xlsx', '.md', '.txt', '.csv', '.json',
  '.png', '.jpg', '.jpeg', '.webp', '.bmp'
]
const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB
const MAX_FILE_COUNT = 5
const UPLOAD_TIMEOUT = 15000 // 15 秒

let _idCounter = 0

export function useFileUpload(agentId = '') {
  const files = ref([])

  /* ---- derived state ---- */
  const doneFiles = computed(() => files.value.filter(f => f.status === 'done'))
  const hasUploading = computed(() => files.value.some(f => f.status === 'uploading'))

  /* ---- helpers ---- */
  const formatSize = (bytes) => {
    if (bytes < 1024) return bytes + ' B'
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  }

  const _extension = (file) => {
    const idx = file.name.lastIndexOf('.')
    if (idx === -1) return ''
    return file.name.slice(idx).toLowerCase()
  }

  const _validate = (file) => {
    const ext = _extension(file)
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      const allowed = ALLOWED_EXTENSIONS.join(' / ')
      return { valid: false, error: `不支持的文件格式（${ext}），仅允许 ${allowed}` }
    }
    if (file.size > MAX_FILE_SIZE) {
      return { valid: false, error: `文件大小 ${formatSize(file.size)} 超过 10 MB 限制` }
    }
    return { valid: true }
  }

  /* ---- 单文件上传（含超时） ---- */
  const _doUpload = async (entry, file) => {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), UPLOAD_TIMEOUT)
    entry._controller = controller

    try {
      const result = await uploadFile(file, agentId, controller.signal)
      clearTimeout(timer)
      entry.status = 'done'
      entry.result = result
      entry.progress = 100
      entry._controller = null
      return { success: true, entry }
    } catch (err) {
      clearTimeout(timer)
      entry._controller = null
      entry.status = 'error'
      if (err.name === 'AbortError') {
        entry.error = '上传超时'
      } else {
        entry.error = err.message || '上传失败'
      }
      return { success: false, entry, error: entry.error }
    }
  }

  /* ---- actions ---- */
  const addFile = async (file) => {
    if (files.value.length >= MAX_FILE_COUNT) {
      return { success: false, error: `最多同时上传 ${MAX_FILE_COUNT} 个文件` }
    }

    const validation = _validate(file)
    if (!validation.valid) {
      return { success: false, error: validation.error }
    }

    const duplicate = files.value.find(f => f.name === file.name && f.size === file.size)
    if (duplicate) {
      return { success: false, error: '该文件已添加' }
    }

    const entry = reactive({
      id: `fu_${++_idCounter}`,
      name: file.name,
      size: file.size,
      ext: _extension(file),
      status: 'pending',
      progress: 0,
      result: null,
      error: null,
      _controller: null,
      _file: file
    })

    files.value.push(entry)
    entry.status = 'uploading'
    return _doUpload(entry, file)
  }

  const retryFile = async (id) => {
    const entry = files.value.find(f => f.id === id)
    if (!entry || !entry._file) return { success: false, error: '无法重试' }

    entry.status = 'uploading'
    entry.error = null
    entry.result = null
    return _doUpload(entry, entry._file)
  }

  const cancelUpload = (id) => {
    const entry = files.value.find(f => f.id === id)
    if (entry?._controller) {
      entry._controller.abort()
    }
  }

  const addFiles = async (fileList) => {
    const results = []
    for (const file of fileList) {
      const result = await addFile(file)
      results.push(result)
    }
    return results
  }

  const removeFile = (id) => {
    cancelUpload(id)
    const idx = files.value.findIndex(f => f.id === id)
    if (idx !== -1) files.value.splice(idx, 1)
  }

  const clearFiles = () => {
    files.value.forEach(f => cancelUpload(f.id))
    files.value = []
  }

  return {
    files, doneFiles, hasUploading,
    addFile, addFiles, removeFile, clearFiles, retryFile, cancelUpload,
    formatSize,
    MAX_FILE_COUNT, ALLOWED_EXTENSIONS, MAX_FILE_SIZE
  }
}
