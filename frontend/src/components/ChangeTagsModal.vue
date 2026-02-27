<template>
  <div class="modal-overlay" :class="{ show: show }" :style="{ display: show ? 'flex' : 'none' }">
    <div class="modal-container">
      <div class="modal-header">
        <h3 class="modal-title">修改标签</h3>
        <button type="button" class="close-btn" @click="$emit('update:show', false)">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="modal-body">
        <div class="form-group">
          <label for="tagsInput" class="form-label">标签（逗号分隔）</label>
          <input
            type="text"
            class="form-input"
            id="tagsInput"
            v-model="tagsInput"
            placeholder="例如：科技,成长"
          >
        </div>
        <div class="form-group">
          <label class="form-label">常用标签</label>
          <div class="common-tags">
            <span
              v-for="tag in commonTags"
              :key="tag"
              class="common-tag"
              @click="addTag(tag)"
            >
              {{ tag }}
            </span>
          </div>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" @click="$emit('update:show', false)">取消</button>
        <button type="button" class="btn btn-primary" @click="confirm">确认修改</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  show: Boolean,
  fundCode: String,
  currentTags: String
})

const emit = defineEmits(['update:show', 'confirm'])

const tagsInput = ref('')
const commonTags = ['科技', '成长', '价值', '指数', '债券', '混合']

watch(() => props.currentTags, (newVal) => {
  tagsInput.value = newVal || ''
}, { immediate: true })

function addTag(tag) {
  const currentTags = tagsInput.value.trim()
  const tagsArray = currentTags ? currentTags.split(',').map(t => t.trim()) : []

  if (!tagsArray.includes(tag)) {
    tagsArray.push(tag)
    tagsInput.value = tagsArray.join(', ')
  }
}

function confirm() {
  emit('confirm', tagsInput.value)
}
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.modal-overlay.show {
  opacity: 1;
}

.modal-container {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  max-width: 500px;
  width: 90%;
  max-height: 90vh;
  overflow-y: auto;
  transform: scale(0.9);
  transition: transform 0.3s ease;
}

.modal-overlay.show .modal-container {
  transform: scale(1);
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-title {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: #1f2937;
}

.close-btn {
  background: none;
  border: none;
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  color: #6b7280;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.close-btn:hover {
  background-color: #f3f4f6;
  color: #1f2937;
}

.modal-body {
  padding: 24px;
}

.form-group {
  margin-bottom: 20px;
}

.form-group:last-child {
  margin-bottom: 0;
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
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  font-size: 0.95rem;
  color: #1f2937;
  transition: all 0.2s ease;
  outline: none;
}

.form-input:focus {
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.form-input::placeholder {
  color: #9ca3af;
}

.common-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.common-tag {
  display: inline-block;
  padding: 6px 14px;
  font-size: 0.875rem;
  font-weight: 500;
  border-radius: 20px;
  background-color: #f3f4f6;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 2px solid transparent;
}

.common-tag:hover {
  background-color: #e5e7eb;
  color: #1f2937;
  transform: translateY(-1px);
}

.common-tag:active {
  transform: translateY(0);
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 20px 24px;
  border-top: 1px solid #e5e7eb;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 10px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-secondary {
  background-color: #f3f4f6;
  color: #6b7280;
}

.btn-secondary:hover {
  background-color: #e5e7eb;
  color: #1f2937;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn:active {
  transform: translateY(0);
}
</style>
