<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="modal-content">
      <div class="modal-header">
        <h3>用户信息</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="modal-body">
        <div class="profile-card">
          <div class="avatar-section">
            <img
              v-if="user.github_avatar"
              :src="user.github_avatar"
              class="avatar"
              alt="头像"
            />
            <div v-else class="avatar placeholder-avatar">
              <i class="bi bi-person-circle"></i>
            </div>
            <div class="nickname">
              {{ user.nickname || user.username || "用户" }}
            </div>
          </div>

          <div class="info-section">
            <div class="info-item">
              <label class="info-label">用户名</label>
              <div class="info-value">{{ user.username || "-" }}</div>
            </div>

            <div class="info-item">
              <label class="info-label">邮箱</label>
              <div class="info-value">
                <span v-if="user.email">{{ user.email }}</span>
                <span v-else class="unlinked">未绑定</span>
              </div>
              <button
                v-if="!user.email"
                class="link-btn"
                @click="showLinkEmail = true"
              >
                <i class="bi bi-link"></i> 绑定
              </button>
            </div>

            <div class="info-item">
              <label class="info-label">GitHub</label>
              <div class="info-value">
                <span v-if="user.github_username"
                  >@{{ user.github_username }}</span
                >
                <span v-else class="unlinked">未绑定</span>
              </div>
              <button
                v-if="!user.github_id"
                class="link-btn"
                @click="handleGithubLink"
              >
                <i class="bi bi-link"></i> 绑定
              </button>
            </div>

            <div class="info-item">
              <label class="info-label">登录密码</label>
              <div class="info-value">
                <span v-if="user.has_password">已设置</span>
                <span v-else class="unlinked">未设置</span>
              </div>
              <button
                v-if="!user.has_password"
                class="link-btn"
                @click="showSetPassword = true"
              >
                <i class="bi bi-key"></i> 设置
              </button>
            </div>

            <div class="info-item">
              <label class="info-label">注册时间</label>
              <div class="info-value">{{ formatDate(user.created_at) }}</div>
            </div>
          </div>
        </div>

        <div class="edit-section">
          <div class="section-title">
            <h3>编辑信息</h3>
          </div>
          <div class="edit-form">
            <div class="form-group">
              <label class="form-label">昵称</label>
              <input
                type="text"
                class="form-input"
                v-model="editNickname"
                placeholder="请输入昵称"
              />
            </div>
            <button
              class="btn btn-primary btn-update"
              @click="handleUpdateProfile"
              :disabled="!editNickname.trim() || editing"
            >
              {{ editing ? "更新中..." : "保存修改" }}
            </button>
          </div>
        </div>

        <div class="logout-section">
          <button class="btn btn-logout" @click="handleLogout">
            <i class="bi bi-box-arrow-right"></i> 退出登录
          </button>
        </div>
      </div>
    </div>

    <!-- 绑定邮箱模态框 -->
    <div
      v-if="showLinkEmail"
      class="modal-overlay"
      @click.self="showLinkEmail = false"
    >
      <div class="modal-content">
        <div class="modal-header">
          <h3>绑定邮箱</h3>
          <button class="close-btn" @click="showLinkEmail = false">
            &times;
          </button>
        </div>
        <div class="modal-body">
          <div v-if="linkEmailError" class="error-message">
            {{ linkEmailError }}
          </div>
          <div class="form-group">
            <label class="form-label">邮箱地址</label>
            <input
              type="email"
              class="form-input"
              v-model="linkEmail"
              placeholder="请输入邮箱"
            />
          </div>
          <div class="form-group">
            <label class="form-label">验证码</label>
            <div class="code-row">
              <input
                type="text"
                class="form-input code-input"
                v-model="linkEmailCode"
                placeholder="请输入验证码"
                maxlength="6"
              />
              <button
                class="btn btn-code"
                @click="handleSendLinkCode"
                :disabled="codeCooldown > 0 || sendingCode"
              >
                {{
                  sendingCode
                    ? "发送中..."
                    : codeCooldown > 0
                      ? `${codeCooldown}s`
                      : "获取验证码"
                }}
              </button>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showLinkEmail = false">
            取消
          </button>
          <button
            class="btn btn-primary"
            @click="handleLinkEmail"
            :disabled="linkingEmail"
          >
            {{ linkingEmail ? "绑定中..." : "确认绑定" }}
          </button>
        </div>
      </div>
    </div>

    <!-- 设置密码模态框 -->
    <div
      v-if="showSetPassword"
      class="modal-overlay"
      @click.self="showSetPassword = false"
    >
      <div class="modal-content">
        <div class="modal-header">
          <h3>设置登录密码</h3>
          <button class="close-btn" @click="showSetPassword = false">
            &times;
          </button>
        </div>
        <div class="modal-body">
          <div v-if="setPasswordError" class="error-message">
            {{ setPasswordError }}
          </div>
          <div class="form-group">
            <label class="form-label">密码</label>
            <input
              type="password"
              class="form-input"
              v-model="newPassword"
              placeholder="请输入密码（至少6位）"
            />
          </div>
          <div class="form-group">
            <label class="form-label">确认密码</label>
            <input
              type="password"
              class="form-input"
              v-model="confirmPassword"
              placeholder="请再次输入密码"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-secondary" @click="showSetPassword = false">
            取消
          </button>
          <button
            class="btn btn-primary"
            @click="handleSetPassword"
            :disabled="settingPassword"
          >
            {{ settingPassword ? "设置中..." : "确认设置" }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, onUnmounted, ref } from "vue";
import { setAuthData, userApi } from "../services/api";

const emit = defineEmits(["close", "user-updated", "logout"]);

const user = ref({
  id: null,
  email: null,
  username: null,
  nickname: null,
  github_id: null,
  github_username: null,
  github_avatar: null,
  has_password: false,
  created_at: null,
});

const editNickname = ref("");
const editing = ref(false);

const showLinkEmail = ref(false);
const linkEmail = ref("");
const linkEmailCode = ref("");
const linkEmailError = ref("");
const linkingEmail = ref(false);
const sendingCode = ref(false);
const codeCooldown = ref(0);
let cooldownTimer = null;

const showSetPassword = ref(false);
const newPassword = ref("");
const confirmPassword = ref("");
const setPasswordError = ref("");
const settingPassword = ref(false);

onMounted(async () => {
  await loadUserProfile();
});

onUnmounted(() => {
  if (cooldownTimer) clearInterval(cooldownTimer);
});

async function loadUserProfile() {
  try {
    const response = await userApi.getProfile();
    user.value = response.data.user;
    editNickname.value = user.value.nickname || "";
  } catch (error) {
    console.error("加载用户信息失败:", error);
  }
}

function formatDate(dateStr) {
  if (!dateStr) return "-";
  const date = new Date(dateStr);
  return date.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });
}

async function handleUpdateProfile() {
  if (!editNickname.value.trim()) return;
  editing.value = true;
  try {
    const response = await userApi.updateProfile({
      nickname: editNickname.value.trim(),
    });
    user.value = response.data.user;
    emit("user-updated", user.value);
  } catch (error) {
    console.error("更新用户信息失败:", error);
  } finally {
    editing.value = false;
  }
}

function startCooldown(seconds) {
  codeCooldown.value = seconds;
  cooldownTimer = setInterval(() => {
    codeCooldown.value--;
    if (codeCooldown.value <= 0) {
      clearInterval(cooldownTimer);
      cooldownTimer = null;
    }
  }, 1000);
}

async function handleSendLinkCode() {
  linkEmailError.value = "";
  if (!linkEmail.value.trim()) {
    linkEmailError.value = "请输入邮箱";
    return;
  }
  sendingCode.value = true;
  try {
    await userApi.sendLinkEmailCode(linkEmail.value.trim());
    startCooldown(60);
  } catch (error) {
    linkEmailError.value = error.response?.data?.error || "发送验证码失败";
  } finally {
    sendingCode.value = false;
  }
}

async function handleLinkEmail() {
  linkEmailError.value = "";
  if (!linkEmail.value.trim()) {
    linkEmailError.value = "请输入邮箱";
    return;
  }
  if (!linkEmailCode.value.trim()) {
    linkEmailError.value = "请输入验证码";
    return;
  }
  linkingEmail.value = true;
  try {
    const response = await userApi.linkEmail(
      linkEmail.value.trim(),
      linkEmailCode.value.trim(),
    );
    user.value = response.data.user;
    setAuthData(localStorage.getItem("auth_token"), user.value);
    emit("user-updated", user.value);
    showLinkEmail.value = false;
    linkEmail.value = "";
    linkEmailCode.value = "";
  } catch (error) {
    linkEmailError.value = error.response?.data?.error || "绑定失败";
  } finally {
    linkingEmail.value = false;
  }
}

async function handleSetPassword() {
  setPasswordError.value = "";
  if (!newPassword.value) {
    setPasswordError.value = "请输入密码";
    return;
  }
  if (newPassword.value.length < 6) {
    setPasswordError.value = "密码长度不能少于6位";
    return;
  }
  if (newPassword.value !== confirmPassword.value) {
    setPasswordError.value = "两次输入的密码不一致";
    return;
  }
  settingPassword.value = true;
  try {
    const response = await userApi.setPassword(
      newPassword.value,
      confirmPassword.value,
    );
    user.value = response.data.user;
    setAuthData(localStorage.getItem("auth_token"), user.value);
    emit("user-updated", user.value);
    showSetPassword.value = false;
    newPassword.value = "";
    confirmPassword.value = "";
  } catch (error) {
    setPasswordError.value = error.response?.data?.error || "设置失败";
  } finally {
    settingPassword.value = false;
  }
}

function handleGithubLink() {
  userApi.getGithubConfig().then((res) => {
    if (res.data.client_id) {
      const redirectUri = `${window.location.origin}/profile/github-callback`;
      window.location.href = `https://github.com/login/oauth/authorize?client_id=${res.data.client_id}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=user:email`;
    }
  });
}

function handleLogout() {
  emit("logout");
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
  z-index: 10000;
  backdrop-filter: blur(4px);
}

.modal-content {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
  max-width: 450px;
  width: 90%;
  max-height: 85vh;
  overflow-y: auto;
  animation: modalFadeIn 0.3s ease;
}

@keyframes modalFadeIn {
  from {
    opacity: 0;
    transform: translateY(-20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 24px;
  border-bottom: 1px solid #e5e7eb;
  position: sticky;
  top: 0;
  background: #fff;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.1rem;
  font-weight: 600;
  color: #111827;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  cursor: pointer;
  color: #6b7280;
  padding: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: background-color 0.2s;
}

.close-btn:hover {
  background-color: #f3f4f6;
}

.modal-body {
  padding: 20px 24px;
}

.profile-card {
  margin-bottom: 20px;
}

.avatar-section {
  text-align: center;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid #eee;
}

.avatar {
  width: 70px;
  height: 70px;
  border-radius: 50%;
  object-fit: cover;
  border: 3px solid #f0f0f0;
}

.placeholder-avatar {
  width: 70px;
  height: 70px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  font-size: 2.2rem;
  margin: 0 auto;
}

.nickname {
  margin-top: 10px;
  font-size: 1.1rem;
  font-weight: 600;
  color: #1f2937;
}

.info-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.info-label {
  width: 70px;
  font-size: 0.85rem;
  color: #6b7280;
  flex-shrink: 0;
}

.info-value {
  flex: 1;
  font-size: 0.875rem;
  color: #1f2937;
}

.info-value .unlinked {
  color: #9ca3af;
}

.link-btn {
  padding: 5px 10px;
  background: #f3f4f6;
  border: none;
  border-radius: 6px;
  font-size: 0.75rem;
  color: #667eea;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  gap: 3px;
}

.link-btn:hover {
  background: #e5e7eb;
}

.edit-section {
  padding-top: 20px;
  border-top: 1px solid #eee;
}

.section-title {
  margin-bottom: 16px;
}

.section-title h3 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 600;
  color: #1f2937;
}

.edit-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.form-label {
  font-size: 0.85rem;
  font-weight: 500;
  color: #374151;
}

.form-input {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 0.9rem;
  transition: border-color 0.2s;
}

.form-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
}

.btn {
  padding: 10px 18px;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-update {
  padding: 10px;
}

.btn-secondary {
  background: #f3f4f6;
  color: #374151;
}

.btn-secondary:hover {
  background: #e5e7eb;
}

.logout-section {
  padding-top: 16px;
  margin-top: 16px;
  border-top: 1px solid #eee;
}

.btn-logout {
  width: 100%;
  padding: 10px;
  background: none;
  border: 1px solid #ef4444;
  border-radius: 8px;
  color: #ef4444;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.btn-logout:hover {
  background: #fee2e2;
}

.error-message {
  background: #fee;
  color: #c33;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 0.85rem;
}

.code-row {
  display: flex;
  gap: 8px;
}

.code-input {
  flex: 1;
}

.btn-code {
  white-space: nowrap;
  padding: 10px 12px;
  background: #667eea;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 0.8rem;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn-code:hover:not(:disabled) {
  opacity: 0.9;
}

.btn-code:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.modal-footer {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
  padding: 14px 24px;
  border-top: 1px solid #e5e7eb;
}

@media (max-width: 480px) {
  .modal-content {
    width: 95%;
    max-height: 90vh;
  }

  .modal-header {
    padding: 16px 20px;
  }

  .modal-body {
    padding: 16px 20px;
  }

  .info-item {
    flex-wrap: wrap;
  }

  .info-label {
    width: 100%;
    margin-bottom: 3px;
  }

  .link-btn {
    margin-top: 4px;
  }
}
</style>
