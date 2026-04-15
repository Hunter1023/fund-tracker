<template>
  <div class="modal-overlay" @click.self="$emit('close')">
    <div class="auth-modal">
      <div class="modal-header">
        <h3>登录 / 注册</h3>
        <button class="close-btn" @click="$emit('close')">&times;</button>
      </div>

      <div class="modal-body">
        <div v-if="error" class="error-message">{{ error }}</div>

        <div class="auth-tabs">
          <button
            v-if="emailEnabled"
            class="tab-btn"
            :class="{ active: activeTab === 'email' }"
            @click="switchTab('email')"
          >
            邮箱登录
          </button>
          <button
            class="tab-btn"
            :class="{ active: activeTab === 'account' }"
            @click="switchTab('account')"
          >
            账号登录
          </button>
          <button
            v-if="githubEnabled"
            class="tab-btn"
            :class="{ active: activeTab === 'github' }"
            @click="switchTab('github')"
          >
            GitHub
          </button>
        </div>

        <div v-if="activeTab === 'email'" class="tab-content">
          <div class="form-group">
            <label class="form-label">邮箱</label>
            <input
              type="email"
              class="form-input"
              v-model="email"
              placeholder="请输入邮箱"
            />
          </div>
          <div class="form-group">
            <label class="form-label">验证码</label>
            <div class="code-row">
              <input
                type="text"
                class="form-input code-input"
                v-model="emailCode"
                placeholder="请输入验证码"
                maxlength="6"
                @keyup.enter="handleEmailLogin"
              />
              <button
                class="btn btn-code"
                @click="handleSendCode"
                :disabled="codeCooldown > 0 || sendingCode"
              >
                {{ sendingCode ? "发送中..." : codeCooldown > 0 ? `${codeCooldown}s` : "获取验证码" }}
              </button>
            </div>
          </div>
          <button
            class="btn btn-primary btn-submit"
            @click="handleEmailLogin"
            :disabled="submitting"
          >
            {{ submitting ? "处理中..." : "登录 / 注册" }}
          </button>
          <p class="tab-hint">首次使用的邮箱将自动注册账号</p>
        </div>

        <div v-if="activeTab === 'account'" class="tab-content">
          <template v-if="!isRegister">
            <div class="form-group">
              <label class="form-label">用户名</label>
              <input
                type="text"
                class="form-input"
                v-model="username"
                placeholder="请输入用户名"
                @keyup.enter="handleAccountLogin"
              />
            </div>
            <div class="form-group">
              <label class="form-label">密码</label>
              <input
                type="password"
                class="form-input"
                v-model="password"
                placeholder="请输入密码"
                @keyup.enter="handleAccountLogin"
              />
            </div>
            <button
              class="btn btn-primary btn-submit"
              @click="handleAccountLogin"
              :disabled="submitting"
            >
              {{ submitting ? "处理中..." : "登录" }}
            </button>
            <div class="auth-switch">
              还没有账号？<a href="#" @click.prevent="isRegister = true">立即注册</a>
            </div>
          </template>
          <template v-else>
            <div class="form-group">
              <label class="form-label">用户名</label>
              <input
                type="text"
                class="form-input"
                v-model="username"
                placeholder="请输入用户名"
              />
            </div>
            <div class="form-group">
              <label class="form-label">密码</label>
              <input
                type="password"
                class="form-input"
                v-model="password"
                placeholder="请输入密码（至少6位）"
              />
            </div>
            <div class="form-group">
              <label class="form-label">确认密码</label>
              <input
                type="password"
                class="form-input"
                v-model="passwordConfirm"
                placeholder="请再次输入密码"
                @keyup.enter="handleAccountRegister"
              />
            </div>
            <button
              class="btn btn-primary btn-submit"
              @click="handleAccountRegister"
              :disabled="submitting"
            >
              {{ submitting ? "处理中..." : "注册" }}
            </button>
            <div class="auth-switch">
              已有账号？<a href="#" @click.prevent="isRegister = false">去登录</a>
            </div>
          </template>
        </div>

        <div v-if="activeTab === 'github'" class="tab-content">
          <div class="github-login-area">
            <svg viewBox="0 0 16 16" width="48" height="48" fill="#24292e">
              <path
                d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
              />
            </svg>
            <p class="github-hint">使用 GitHub 账号授权登录</p>
            <button class="btn btn-github" @click="handleGithubLogin">
              <svg viewBox="0 0 16 16" width="20" height="20" fill="currentColor">
                <path
                  d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z"
                />
              </svg>
              GitHub 登录
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref, onUnmounted } from "vue";
import { authApi, setAuthData } from "../services/api";

const emit = defineEmits(["close", "login-success"]);

const activeTab = ref("account");
const email = ref("");
const emailCode = ref("");
const username = ref("");
const password = ref("");
const passwordConfirm = ref("");
const isRegister = ref(false);
const error = ref("");
const submitting = ref(false);
const sendingCode = ref(false);
const codeCooldown = ref(0);
const githubEnabled = ref(false);
const emailEnabled = ref(false);

let cooldownTimer = null;

onMounted(async () => {
  try {
    const [githubRes, emailRes] = await Promise.all([
      authApi.getGithubConfig().catch(() => ({ data: { enabled: false } })),
      authApi.getEmailConfig().catch(() => ({ data: { enabled: false } })),
    ]);
    githubEnabled.value = githubRes.data.enabled;
    emailEnabled.value = emailRes.data.enabled;

    if (emailEnabled.value) {
      activeTab.value = "email";
    } else if (githubEnabled.value) {
      activeTab.value = "github";
    } else {
      activeTab.value = "account";
    }
  } catch {
    activeTab.value = "account";
  }
});

onUnmounted(() => {
  if (cooldownTimer) clearInterval(cooldownTimer);
});

function switchTab(tab) {
  activeTab.value = tab;
  error.value = "";
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

async function handleSendCode() {
  error.value = "";
  if (!email.value.trim()) {
    error.value = "请输入邮箱";
    return;
  }

  sendingCode.value = true;
  try {
    await authApi.sendEmailCode(email.value.trim());
    startCooldown(60);
  } catch (err) {
    if (err.response?.data?.error) {
      error.value = err.response.data.error;
    } else {
      error.value = "验证码发送失败，请稍后重试";
    }
  } finally {
    sendingCode.value = false;
  }
}

async function handleEmailLogin() {
  error.value = "";
  if (!email.value.trim()) {
    error.value = "请输入邮箱";
    return;
  }
  if (!emailCode.value.trim()) {
    error.value = "请输入验证码";
    return;
  }

  submitting.value = true;
  try {
    const response = await authApi.emailLogin(email.value.trim(), emailCode.value.trim());
    const { token, user } = response.data;
    setAuthData(token, user);
    emit("login-success", user);
  } catch (err) {
    if (err.response?.data?.error) {
      error.value = err.response.data.error;
    } else {
      error.value = "登录失败，请稍后重试";
    }
  } finally {
    submitting.value = false;
  }
}

async function handleAccountLogin() {
  error.value = "";
  if (!username.value.trim()) {
    error.value = "请输入用户名";
    return;
  }
  if (!password.value) {
    error.value = "请输入密码";
    return;
  }

  submitting.value = true;
  try {
    const response = await authApi.login(username.value.trim(), password.value);
    const { token, user } = response.data;
    setAuthData(token, user);
    emit("login-success", user);
  } catch (err) {
    if (err.response?.data?.error) {
      error.value = err.response.data.error;
    } else {
      error.value = "登录失败，请稍后重试";
    }
  } finally {
    submitting.value = false;
  }
}

async function handleAccountRegister() {
  error.value = "";
  if (!username.value.trim()) {
    error.value = "请输入用户名";
    return;
  }
  if (!password.value) {
    error.value = "请输入密码";
    return;
  }
  if (password.value.length < 6) {
    error.value = "密码长度不能少于6位";
    return;
  }
  if (password.value !== passwordConfirm.value) {
    error.value = "两次输入的密码不一致";
    return;
  }

  submitting.value = true;
  try {
    const response = await authApi.register(username.value.trim(), password.value);
    const { token, user } = response.data;
    setAuthData(token, user);
    emit("login-success", user);
  } catch (err) {
    if (err.response?.data?.error) {
      error.value = err.response.data.error;
    } else {
      error.value = "注册失败，请稍后重试";
    }
  } finally {
    submitting.value = false;
  }
}

function handleGithubLogin() {
  const redirectUri = `${window.location.origin}`;
  authApi.getGithubConfig().then((res) => {
    if (res.data.client_id) {
      window.location.href = `https://github.com/login/oauth/authorize?client_id=${res.data.client_id}&redirect_uri=${encodeURIComponent(redirectUri)}&scope=user:email`;
    }
  });
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
  justify-content: center;
  align-items: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.auth-modal {
  background: #fff;
  border-radius: 16px;
  width: 400px;
  max-width: 90vw;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border-bottom: 1px solid #eee;
}

.modal-header h3 {
  margin: 0;
  font-size: 1.3rem;
  color: #333;
}

.close-btn {
  background: none;
  border: none;
  font-size: 1.5rem;
  color: #999;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.close-btn:hover {
  color: #333;
}

.modal-body {
  padding: 24px;
}

.error-message {
  background: #fee;
  color: #c33;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 16px;
  font-size: 0.9rem;
}

.auth-tabs {
  display: flex;
  gap: 0;
  margin-bottom: 20px;
  border-bottom: 2px solid #eee;
}

.tab-btn {
  flex: 1;
  padding: 10px 0;
  border: none;
  background: none;
  font-size: 0.95rem;
  color: #999;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  margin-bottom: -2px;
  transition: all 0.2s;
}

.tab-btn:hover {
  color: #667eea;
}

.tab-btn.active {
  color: #667eea;
  border-bottom-color: #667eea;
  font-weight: 500;
}

.tab-content {
  min-height: 180px;
}

.form-group {
  margin-bottom: 16px;
}

.form-label {
  display: block;
  font-size: 0.85rem;
  color: #666;
  margin-bottom: 6px;
  font-weight: 500;
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 0.95rem;
  transition: border-color 0.2s;
  box-sizing: border-box;
}

.form-input:focus {
  outline: none;
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
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
  padding: 10px 14px;
  background: #667eea;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 0.85rem;
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

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 0.95rem;
  cursor: pointer;
  transition: all 0.2s;
  text-decoration: none;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  width: 100%;
}

.btn-primary:hover:not(:disabled) {
  opacity: 0.9;
  transform: translateY(-1px);
}

.btn-primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-submit {
  margin-top: 8px;
  padding: 12px;
  font-size: 1rem;
  font-weight: 500;
}

.tab-hint {
  text-align: center;
  margin-top: 12px;
  font-size: 0.8rem;
  color: #999;
}

.auth-switch {
  text-align: center;
  margin-top: 16px;
  font-size: 0.85rem;
  color: #999;
}

.auth-switch a {
  color: #667eea;
  text-decoration: none;
  font-weight: 500;
}

.auth-switch a:hover {
  text-decoration: underline;
}

.github-login-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 24px 0;
  gap: 16px;
}

.github-hint {
  color: #666;
  font-size: 0.9rem;
  margin: 0;
}

.btn-github {
  background: #24292e;
  color: #fff;
  padding: 12px 32px;
  gap: 8px;
  font-size: 0.95rem;
  border-radius: 8px;
}

.btn-github:hover {
  background: #2f363d;
}
</style>
