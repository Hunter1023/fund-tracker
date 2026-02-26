<template>
  <div class="modal-overlay" :class="{ show: show }" :style="{ display: show ? 'flex' : 'none' }">
    <div class="modal-container confirm-modal">
      <div class="modal-header">
        <h3 class="modal-title">确认操作</h3>
        <button type="button" class="close-btn" @click="$emit('update:show', false)">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="modal-body">
        <div class="confirm-message">
          <i class="bi bi-question-circle confirm-icon"></i>
          <p>{{ message }}</p>
        </div>
      </div>
      <div class="modal-footer">
        <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
        <button type="button" class="btn btn-danger" @click="handleConfirm">确定</button>
      </div>
    </div>
  </div>
</template>

<script setup>
const props = defineProps({
  show: Boolean,
  message: {
    type: String,
    default: '确定要执行此操作吗？'
  }
})

const emit = defineEmits(['update:show', 'confirm'])

function handleConfirm() {
  emit('confirm')
  emit('update:show', false)
}

function handleCancel() {
  emit('update:show', false)
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
  max-width: 400px;
  width: 90%;
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
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.modal-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}

.close-btn {
  background: none;
  border: none;
  font-size: 20px;
  color: #6b7280;
  cursor: pointer;
  padding: 4px;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background-color: #f3f4f6;
  color: #1f2937;
}

.modal-body {
  padding: 24px;
}

.confirm-message {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.confirm-icon {
  font-size: 24px;
  color: #f59e0b;
  flex-shrink: 0;
  margin-top: 2px;
}

.confirm-message p {
  margin: 0;
  font-size: 15px;
  color: #4b5563;
  line-height: 1.5;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 16px 24px;
  border-top: 1px solid #e5e7eb;
}

.btn {
  padding: 8px 20px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  border: none;
}

.btn-secondary {
  background: #f3f4f6;
  color: #4b5563;
}

.btn-secondary:hover {
  background: #e5e7eb;
}

.btn-danger {
  background: #ef4444;
  color: white;
}

.btn-danger:hover {
  background: #dc2626;
}
</style>
