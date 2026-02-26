<template>
  <div v-if="show" class="modal-overlay" :style="{ display: show ? 'flex' : 'none' }" @click="closeModal">
    <div class="modal-container platform-manager" @click.stop>
      <div class="modal-header">
        <h3 class="manager-title">平台管理</h3>
        <button type="button" class="close-btn" @click="closeModal">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>

      <div class="modal-body">
        <div v-if="loading" class="loading-state">
          <div class="spinner-border text-primary" role="status">
            <span class="visually-hidden">加载中...</span>
          </div>
        </div>

        <div v-else-if="platforms.length === 0" class="empty-state">
          <div class="empty-icon">📱</div>
          <p>暂无平台</p>
        </div>

        <div v-else class="platform-list">
          <div 
            v-for="platform in platforms" 
            :key="platform.id" 
            class="platform-item"
            draggable="true"
            @dragstart="handleDragStart($event, platform)"
            @dragover.prevent
            @drop="handleDrop($event, platform)"
            :class="{ 'dragging': draggingPlatform?.id === platform.id, 'drag-over': dragOverPlatform?.id === platform.id }"
          >
            <div class="drag-handle">
              <i class="bi bi-grip-vertical"></i>
            </div>
            <div class="platform-info">
              <div class="platform-name">{{ platform.name }}</div>
            </div>
            <div class="platform-actions">
              <button class="action-btn edit-btn" @click="editPlatform(platform)" title="编辑">
                <i class="bi bi-pencil"></i>
              </button>
              <button class="action-btn delete-btn" @click="confirmDelete(platform)" title="删除">
                <i class="bi bi-trash"></i>
              </button>
            </div>
          </div>
        </div>

        <div class="manager-footer">
          <button class="add-btn" @click="showAddModal = true">
            <i class="bi bi-plus-circle me-2"></i>添加平台
          </button>
        </div>
      </div>

      <!-- 添加/编辑平台弹窗 -->
      <div class="modal-overlay" :class="{ show: showAddModal || showEditModal }" :style="{ display: (showAddModal || showEditModal) ? 'flex' : 'none' }" @click.self="closeModal">
        <div class="modal-container">
          <div class="modal-header">
            <h3 class="modal-title">{{ isEditing ? '编辑平台' : '添加平台' }}</h3>
            <button type="button" class="close-btn" @click="closeModal">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>
          <div class="modal-body">
            <div class="form-group">
              <label class="form-label">平台名称</label>
              <input
                type="text"
                class="form-input"
                :class="{ 'is-invalid': validationErrors.name }"
                v-model="platformName"
                placeholder="请输入平台名称（如：支付宝、理财通）"
              >
              <div v-if="validationErrors.name" class="invalid-feedback">
                {{ validationErrors.name }}
              </div>
            </div>
            <div v-if="validationErrors.general" class="alert alert-danger mt-3">
              {{ validationErrors.general }}
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="closeModal">取消</button>
            <button type="button" class="btn btn-primary" @click="savePlatform" :disabled="saving">
              {{ saving ? '保存中...' : '确认' }}
            </button>
          </div>
        </div>
      </div>

      <!-- 删除确认弹窗 -->
      <div class="modal-overlay" :class="{ show: showDeleteModal }" :style="{ display: showDeleteModal ? 'flex' : 'none' }" @click.self="showDeleteModal = false">
        <div class="modal-container">
          <div class="modal-header">
            <h3 class="modal-title">确认删除</h3>
            <button type="button" class="close-btn" @click="showDeleteModal = false; emit('update:show', false)">
              <i class="bi bi-x-lg"></i>
            </button>
          </div>
          <div class="modal-body">
            <div class="delete-confirm-section">
              <div class="delete-warning">
                <i class="bi bi-exclamation-triangle"></i>
                <span>确定要删除平台"{{ deletingPlatform?.name }}"吗？此操作不可恢复。</span>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="showDeleteModal = false; emit('update:show', false)">取消</button>
            <button type="button" class="btn btn-danger" @click="deletePlatform" :disabled="deleting">
              {{ deleting ? '删除中...' : '删除' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import { platformApi } from '../services/api'

const props = defineProps({
  show: Boolean
})

const emit = defineEmits(['update:show', 'update'])

const platforms = ref([])
const loading = ref(false)
const showAddModal = ref(false)
const showEditModal = ref(false)
const showDeleteModal = ref(false)
const platformName = ref('')
const currentPlatform = ref(null)
const deletingPlatform = ref(null)
const isEditing = ref(false)
const saving = ref(false)
const deleting = ref(false)
const validationErrors = ref({})
const draggingPlatform = ref(null)
const dragOverPlatform = ref(null)

async function loadPlatforms() {
  loading.value = true
  try {
    const response = await platformApi.get()
    platforms.value = response.data
  } catch (error) {
    console.error('加载平台列表失败:', error)
  } finally {
    loading.value = false
  }
}

function editPlatform(platform) {
  currentPlatform.value = platform
  platformName.value = platform.name
  isEditing.value = true
  showEditModal.value = true
  validationErrors.value = {}
}

function confirmDelete(platform) {
  deletingPlatform.value = platform
  showDeleteModal.value = true
}

function closeModal() {
  showAddModal.value = false
  showEditModal.value = false
  platformName.value = ''
  currentPlatform.value = null
  isEditing.value = false
  validationErrors.value = {}
  emit('update:show', false)
}

async function savePlatform() {
  validationErrors.value = {}
  
  if (!platformName.value.trim()) {
    validationErrors.value.name = '平台名称不能为空'
    return
  }

  saving.value = true
  try {
    if (isEditing.value) {
      await platformApi.update(currentPlatform.value.id, platformName.value.trim())
    } else {
      await platformApi.add(platformName.value.trim())
    }
    await loadPlatforms()
    emit('update')
    closeModal()
  } catch (error) {
    console.error('保存平台失败:', error)
    if (error.response && error.response.data && error.response.data.error) {
      validationErrors.value.general = error.response.data.error
    } else {
      validationErrors.value.general = '保存失败，请重试'
    }
  } finally {
    saving.value = false
  }
}

async function deletePlatform() {
  deleting.value = true
  try {
    await platformApi.delete(deletingPlatform.value.id)
    await loadPlatforms()
    emit('update')
    showDeleteModal.value = false
    deletingPlatform.value = null
  } catch (error) {
    console.error('删除平台失败:', error)
    if (error.response && error.response.data && error.response.data.error) {
      alert(error.response.data.error)
    } else {
      alert('删除失败，请重试')
    }
  } finally {
    deleting.value = false
  }
}

function formatDate(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

// 拖曳开始
function handleDragStart(event, platform) {
  draggingPlatform.value = platform
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', platform.id)
}

// 拖曳结束
function handleDragEnd() {
  draggingPlatform.value = null
  dragOverPlatform.value = null
}

// 拖曳经过
function handleDragOver(event, platform) {
  event.preventDefault()
  event.dataTransfer.dropEffect = 'move'
  dragOverPlatform.value = platform
}

// 拖曳放下
function handleDrop(event, targetPlatform) {
  event.preventDefault()
  
  if (draggingPlatform.value && draggingPlatform.value.id !== targetPlatform.id) {
    const dragIndex = platforms.value.findIndex(p => p.id === draggingPlatform.value.id)
    const targetIndex = platforms.value.findIndex(p => p.id === targetPlatform.id)
    
    // 重新排序平台数组
    const updatedPlatforms = [...platforms.value]
    updatedPlatforms.splice(dragIndex, 1)
    updatedPlatforms.splice(targetIndex, 0, draggingPlatform.value)
    platforms.value = updatedPlatforms
    
    // 保存排序
    savePlatformOrder(updatedPlatforms)
  }
  
  draggingPlatform.value = null
  dragOverPlatform.value = null
}

// 保存平台排序
async function savePlatformOrder(orderedPlatforms) {
  try {
    const orderData = orderedPlatforms.map((platform, index) => ({
      id: platform.id,
      order: index + 1
    }))
    
    await platformApi.updateOrder(orderData)
    emit('update')
  } catch (error) {
    console.error('保存平台排序失败:', error)
  }
}

// 监听show属性变化，当modal打开时加载平台数据
watch(() => props.show, (newVal) => {
  if (newVal) {
    loadPlatforms()
  }
})

// 组件挂载时如果已经显示，加载平台数据
onMounted(() => {
  if (props.show) {
    loadPlatforms()
  }
})
</script>

<style scoped>
.platform-manager {
  width: 100%;
}

.manager-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}

.manager-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.add-btn {
  padding: 10px 20px;
  border: none;
  border-radius: 10px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.add-btn:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.loading-state {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 60px 20px;
}

.empty-state {
  text-align: center;
  padding: 60px 20px;
  color: #9ca3af;
}

.empty-icon {
  font-size: 3rem;
  margin-bottom: 16px;
}

.empty-state p {
  margin: 0;
  font-size: 1rem;
}

.platform-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.platform-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 20px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  transition: all 0.2s ease;
  cursor: grab;
}

.platform-item:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.platform-item:active {
  cursor: grabbing;
}

.platform-item.dragging {
  opacity: 0.5;
  transform: rotate(5deg);
}

.platform-item.drag-over {
  border: 2px dashed #667eea;
  background: rgba(102, 126, 234, 0.05);
}

.drag-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 6px;
  cursor: grab;
  color: #9ca3af;
  transition: all 0.2s ease;
}

.drag-handle:hover {
  background: #f3f4f6;
  color: #6b7280;
}

.platform-info {
  flex: 1;
}

.platform-actions {
  display: flex;
  gap: 8px;
}

.platform-info {
  flex: 1;
}

.platform-name {
  font-size: 1.1rem;
  font-weight: 600;
  color: #1f2937;
}

.platform-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 8px 12px;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  background: #f3f4f6;
  color: #4b5563;
}

.action-btn:hover {
  transform: translateY(-1px);
}

.edit-btn:hover {
  background: #dbeafe;
  color: #1e40af;
}

.delete-btn:hover {
  background: #fee2e2;
  color: #991b1b;
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: none;
  justify-content: center;
  align-items: center;
  z-index: 1000;
}

.modal-overlay.show {
  display: flex;
}

.modal-container {
  background: #fff;
  border-radius: 12px;
  width: 90%;
  max-width: 500px;
  max-height: 90vh;
  overflow-y: auto;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.2);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
  margin: 0;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: #6b7280;
  cursor: pointer;
  transition: color 0.2s ease;
}

.close-btn:hover {
  color: #1f2937;
}

.modal-body {
  padding: 20px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px;
  border-top: 1px solid #e5e7eb;
}

.form-group {
  margin-bottom: 20px;
}

.form-label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: #374151;
  margin-bottom: 8px;
}

.form-input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  font-size: 0.95rem;
  transition: all 0.2s ease;
}

.form-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.form-input.is-invalid {
  border-color: #ef4444;
}

.invalid-feedback {
  color: #ef4444;
  font-size: 0.875rem;
  margin-top: 4px;
}

.alert {
  padding: 12px 16px;
  border-radius: 8px;
  font-size: 0.875rem;
}

.alert-danger {
  background: #fee2e2;
  color: #991b1b;
  border: 1px solid #fecaca;
}

.delete-confirm-section {
  padding: 10px 0;
}

.delete-warning {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background: #fffbeb;
  border-radius: 8px;
  color: #92400e;
  font-size: 0.95rem;
}

.delete-warning i {
  font-size: 1.5rem;
  flex-shrink: 0;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background: #e5e7eb;
  color: #374151;
}

.btn-secondary:hover:not(:disabled) {
  background: #d1d5db;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn-danger {
  background: #ef4444;
  color: #fff;
}

.btn-danger:hover:not(:disabled) {
  background: #dc2626;
  transform: translateY(-1px);
}
</style>