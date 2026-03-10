<template>
  <div class="app-container">
    <div class="header-section">
      <div class="header-content">
        <h1 class="app-title">🐥叽咕宝</h1>
        <p class="app-subtitle">实时基金估值工具</p>
      </div>
    </div>

    <div v-if="loading" class="spinner-overlay">
      <div class="spinner-content">
        <div class="spinner-border text-primary" role="status">
          <span class="visually-hidden">加载中...</span>
        </div>
      </div>
    </div>

    <div class="search-section">
      <div class="search-container">
        <span class="search-icon">
          <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" class="bi bi-search" viewBox="0 0 16 16">
            <path d="M11.742 10.344a6.5 6.5 0 1 0-1.397 1.398h-.001c.03.04.062.078.098.115l3.85 3.85a1 1 0 0 0 1.415-1.414l-3.85-3.85a1.007 1.007 0 0 0-.115-.1zM12 6.5a5.5 5.5 0 1 1-11 0 5.5 5.5 0 0 1 11 0z"/>
          </svg>
        </span>
        <input
          type="text"
          class="search-input"
          v-model="searchKeyword"
          placeholder="输入基金代码或名称"
          autocomplete="off"
          @input="handleSearch"
          @focus="handleSearch"
          @click="handleSearch"
        />
        <div
          v-if="showSearchDropdown && searchResults.length > 0"
          class="search-dropdown"
        >
          <div
            v-for="fund in searchResults"
            :key="fund.fund_code"
            class="dropdown-item"
          >
            <div class="dropdown-item-header">
              <div class="fund-info">
                <div class="fund-name">{{ fund.fund_name }}</div>
                <div class="fund-code">{{ fund.fund_code }}</div>
              </div>
              <div class="fund-badges">
                <span v-if="isInWatchlist(fund.fund_code)" class="badge badge-watchlist">已在自选</span>
                <span v-if="isInHoldings(fund.fund_code)" class="badge badge-holding">已在持仓</span>
              </div>
            </div>
            <div class="dropdown-item-actions">
              <button
                v-if="!isInWatchlist(fund.fund_code)"
                class="action-btn btn-watchlist"
                @click.stop="openTagsModal(fund, 'watchlist')"
              >
                加入自选
              </button>
              <button
                v-if="!isInHoldings(fund.fund_code)"
                class="action-btn btn-holding"
                @click.stop="openFundDetailForHolding(fund)"
              >
                同步持仓
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="tabs-section">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'holding' }"
        @click="activeTab = 'holding'"
      >
        持仓管理
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'watchlist' }"
        @click="activeTab = 'watchlist'"
      >
        自选基金
      </button>
    </div>

    <div class="content-section">
      <Watchlist v-show="activeTab === 'watchlist'" ref="watchlistRef" />
      <Holdings v-show="activeTab === 'holding'" ref="holdingsRef" />
    </div>

    <!-- 标签输入模态框 -->
    <div v-if="showTagsModal" class="modal-overlay" @click="closeTagsModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>{{ modalTitle }}</h3>
          <button class="close-btn" @click="closeTagsModal">&times;</button>
        </div>
        <div class="modal-body">
          <div class="form-group">
            <label class="form-label">基金信息</label>
            <div class="fund-info-display">
              <div class="fund-name">{{ selectedFund?.fund_name }}</div>
              <div class="fund-code">{{ selectedFund?.fund_code }}</div>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">板块标签</label>
            <div class="tag-input-container">
              <input
                type="text"
                class="form-input"
                v-model="tagsInput"
                placeholder="请输入板块标签（如：Ai, 新能源）"
                @keyup.enter="confirmTags"
                @input="filterTags"
                @focus="showDropdown = true"
                @blur="hideDropdown"
              >
              <div class="tag-dropdown" v-if="showDropdown && filteredTags.length > 0">
                <div
                  v-for="tag in filteredTags"
                  :key="tag"
                  class="dropdown-item"
                  @mousedown="selectTag(tag)"
                >
                  {{ tag }}
                </div>
              </div>
            </div>
            <div class="form-hint">多个标签请用逗号分隔</div>
          </div>
          <div class="form-group" v-if="existingTags.length > 0">
            <label class="form-label">已存在的标签</label>
            <div class="common-tags">
              <span
                v-for="tag in existingTags"
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
          <button class="btn btn-secondary" @click="closeTagsModal">取消</button>
          <button class="btn btn-primary" @click="confirmTags" :disabled="!selectedFund">确认</button>
        </div>
      </div>
    </div>

    <!-- 基金详情模态框 -->
    <FundDetailModal
      v-model:show="showFundDetailModal"
      :fund-data="currentFund"
      :holding-data="currentHolding"
      @confirm="handleDetailConfirm"
    />
  </div>
</template>

<script setup>
import { nextTick, onMounted, ref, watch } from 'vue'
import FundDetailModal from './components/FundDetailModal.vue'
import Holdings from './components/Holdings.vue'
import Watchlist from './components/Watchlist.vue'
import { fundApi, holdingApi, watchlistApi, tagsApi } from './services/api'

const activeTab = ref('holding')
const loading = ref(false)
const searchKeyword = ref('')
const searchResults = ref([])
const showSearchDropdown = ref(false)
const watchlistRef = ref(null)
const holdingsRef = ref(null)
const watchlistFunds = ref([])
const holdingsFunds = ref([])

// 基金详情模态框
const showFundDetailModal = ref(false)
const currentFund = ref(null)
const currentHolding = ref(null)

// 标签输入模态框
const showTagsModal = ref(false)
const selectedFund = ref(null)
const selectedAction = ref('')
const tagsInput = ref('')
const modalTitle = ref('')
const existingTags = ref([])
const showDropdown = ref(false)
const filteredTags = ref([])

let searchTimeout = null

function showLoading() {
  loading.value = true
}

function hideLoading() {
  loading.value = false
}

// 避免重复请求的标志
let isLoadingData = false

async function loadWatchlistAndHoldings() {
  if (isLoadingData) return

  isLoadingData = true
  try {
    // 加载自选基金
    if (watchlistRef.value && watchlistRef.value.funds) {
      watchlistFunds.value = watchlistRef.value.funds
    } else {
      const watchlistResponse = await watchlistApi.get()
      watchlistFunds.value = watchlistResponse.data || []
    }

    // 加载持仓基金
    if (holdingsRef.value && holdingsRef.value.holdings) {
      holdingsFunds.value = holdingsRef.value.holdings
    } else {
      const holdingsResponse = await holdingApi.get()
      holdingsFunds.value = holdingsResponse.data || []
    }
  } catch (error) {
    console.error('加载自选和持仓失败:', error)
  } finally {
    isLoadingData = false
  }
}

async function handleSearch() {
  const keyword = searchKeyword.value.trim()

  if (searchTimeout) {
    clearTimeout(searchTimeout)
  }

  if (!keyword) {
    searchResults.value = []
    showSearchDropdown.value = false
    return
  }

  searchTimeout = setTimeout(async () => {
    try {
      // 先加载自选和持仓数据，用于判断搜索结果是否已存在
      await loadWatchlistAndHoldings()

      const response = await fundApi.search(keyword)
      searchResults.value = response.data
      showSearchDropdown.value = true
    } catch (error) {
      console.error('搜索失败:', error)
    }
  }, 150)
}

function isInWatchlist(fundCode) {
  return watchlistFunds.value.some(fund => fund.fund_code === fundCode)
}

function isInHoldings(fundCode) {
  return holdingsFunds.value.some(fund => fund.fund_code === fundCode)
}

// 打开基金详情模态框用于添加持仓
function openFundDetailForHolding(fund) {
  currentFund.value = {
    fund_code: fund.fund_code,
    fund_name: fund.fund_name
  }
  currentHolding.value = null
  showFundDetailModal.value = true
  showSearchDropdown.value = false
}

// 处理基金详情模态框确认
async function handleDetailConfirm() {
  await loadWatchlistAndHoldings()
  if (holdingsRef.value && holdingsRef.value.loadHoldings) {
    await holdingsRef.value.loadHoldings()
  }
}

// 打开标签输入模态框
function openTagsModal(fund, action) {
  selectedFund.value = fund
  selectedAction.value = action
  tagsInput.value = ''

  if (action === 'watchlist') {
    modalTitle.value = '加入自选 - 选择板块标签'
  }

  showTagsModal.value = true
  // 加载已存在的标签
  loadExistingTags()
  // 清空搜索结果，避免模态框打开时搜索结果仍然显示
  showSearchDropdown.value = false
}

// 关闭标签输入模态框
function closeTagsModal() {
  showTagsModal.value = false
  selectedFund.value = null
  selectedAction.value = ''
  tagsInput.value = ''
}

// 加载已存在的标签
async function loadExistingTags() {
  try {
    const response = await tagsApi.get()
    existingTags.value = response.data.tags
  } catch (error) {
    console.error('加载标签失败:', error)
  }
}

// 过滤标签
function filterTags() {
  const input = tagsInput.value.trim()
  if (!input) {
    filteredTags.value = existingTags.value
    return
  }

  // 过滤出包含输入内容的标签
  filteredTags.value = existingTags.value.filter(tag =>
    tag.toLowerCase().includes(input.toLowerCase())
  )
  showDropdown.value = filteredTags.value.length > 0
}

// 隐藏下拉菜单
function hideDropdown() {
  // 延迟隐藏，以便可以点击下拉项
  setTimeout(() => {
    showDropdown.value = false
  }, 200)
}

// 选择标签
function selectTag(tag) {
  const currentTags = tagsInput.value.trim()
  const tagsArray = currentTags ? currentTags.split(',').map(t => t.trim()) : []

  if (!tagsArray.includes(tag)) {
    tagsArray.push(tag)
    tagsInput.value = tagsArray.join(', ')
  }
  showDropdown.value = false
}

// 添加标签
function addTag(tag) {
  const currentTags = tagsInput.value.trim()
  const tagsArray = currentTags ? currentTags.split(',').map(t => t.trim()) : []

  if (!tagsArray.includes(tag)) {
    tagsArray.push(tag)
    tagsInput.value = tagsArray.join(', ')
  }
}

// 确认标签并执行操作
async function confirmTags() {
  if (!selectedFund.value) return

  showLoading()
  try {
    const tags = tagsInput.value.trim()

    // 加入自选
    if (watchlistRef.value && watchlistRef.value.addToWatchlist) {
      await watchlistRef.value.addToWatchlist(selectedFund.value.fund_code, tags)
      // 更新本地自选基金列表
      await loadWatchlistAndHoldings()
    }

    // 关闭模态框
    closeTagsModal()
  } catch (error) {
    console.error('操作失败:', error)
  } finally {
    hideLoading()
  }
}

function handleClickOutside(event) {
  const searchContainer = event.target.closest('.input-group')
  if (!searchContainer) {
    searchResults.value = []
    showSearchDropdown.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
  // 初始加载自选和持仓数据
  loadWatchlistAndHoldings()
})

watch(activeTab, async (newTab) => {
  await nextTick()
  if (newTab === 'watchlist' && watchlistRef.value && watchlistRef.value.loadWatchlist) {
    try {
      await watchlistRef.value.loadWatchlist()
      // 更新本地自选基金列表
      await loadWatchlistAndHoldings()
    } catch (error) {
      console.error('加载自选基金失败:', error)
    }
  } else if (newTab === 'holding' && holdingsRef.value && holdingsRef.value.loadHoldings) {
    try {
      await holdingsRef.value.loadHoldings()
      // 更新本地持仓基金列表
      await loadWatchlistAndHoldings()
    } catch (error) {
      console.error('加载持仓基金失败:', error)
    }
  }
})
</script>

<style scoped>
.app-container {
  min-height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
}

.header-section {
  text-align: center;
  margin-bottom: 30px;
  padding: 20px 0;
}

.header-content {
  display: inline-block;
  text-align: right;
  max-width: 100%;
}

.app-title {
  font-size: 2.5rem;
  font-weight: 700;
  color: #fff;
  margin: 0 0 10px 0;
  text-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  text-align: center;
  margin-bottom: 10px;
}

.app-subtitle {
  font-size: 1rem;
  color: rgba(255, 255, 255, 0.85);
  margin: 0;
  font-weight: 300;
  text-align: right;
}

.spinner-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255, 255, 255, 0.8);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
  backdrop-filter: blur(4px);
}

.spinner-content {
  background: #fff;
  padding: 40px;
  border-radius: 16px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
}

.search-section {
  margin-bottom: 24px;
}

.search-container {
  max-width: 600px;
  margin: 0 auto;
  position: relative;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
  display: flex;
  align-items: center;
  padding: 0 16px;
  transition: box-shadow 0.3s ease;
}

.search-container:focus-within {
  box-shadow: 0 8px 30px rgba(0, 0, 0, 0.15);
}

.search-icon {
  color: #9ca3af;
  display: flex;
  align-items: center;
  margin-right: 12px;
}

.search-input {
  flex: 1;
  border: none;
  outline: none;
  padding: 16px 0;
  font-size: 1rem;
  color: #1f2937;
  background: transparent;
}

.search-input::placeholder {
  color: #9ca3af;
}

.search-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.15);
  max-height: 400px;
  overflow-y: auto;
  z-index: 1000;
  padding: 8px;
}

.dropdown-item {
  padding: 16px;
  border-radius: 8px;
  transition: background-color 0.2s ease;
  margin-bottom: 4px;
}

.dropdown-item:hover {
  background-color: #f9fafb;
}

.dropdown-item-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.fund-info {
  flex: 1;
}

.fund-name {
  font-weight: 600;
  color: #1f2937;
  font-size: 0.95rem;
  margin-bottom: 4px;
}

.fund-code {
  font-size: 0.85rem;
  color: #6b7280;
}

.fund-badges {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.badge {
  display: inline-block;
  padding: 4px 10px;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: 20px;
}

.badge-watchlist {
  background-color: #e0e7ff;
  color: #4f46e5;
}

.badge-holding {
  background-color: #d1fae5;
  color: #059669;
}

.dropdown-item-tags {
  margin: 12px 0;
}

.tags-input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 0.875rem;
  transition: all 0.2s ease;
}

.tags-input:focus {
  outline: none;
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.dropdown-item-actions {
  display: flex;
  gap: 8px;
}

.action-btn {
  flex: 1;
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-watchlist {
  background-color: #4f46e5;
  color: #fff;
}

.btn-watchlist:hover {
  background-color: #4338ca;
  transform: translateY(-1px);
}

.btn-holding {
  background-color: #059669;
  color: #fff;
}

.btn-holding:hover {
  background-color: #047857;
  transform: translateY(-1px);
}

.tabs-section {
  display: flex;
  gap: 12px;
  margin-bottom: 24px;
  max-width: 600px;
  margin-left: auto;
  margin-right: auto;
}

.tab-btn {
  flex: 1;
  padding: 14px 24px;
  border: none;
  border-radius: 12px;
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
  background-color: rgba(255, 255, 255, 0.9);
  color: #6b7280;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.tab-btn:hover {
  background-color: #fff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.tab-btn.active {
  background-color: #fff;
  color: #4f46e5;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  font-weight: 600;
}

.content-section {
  background: #fff;
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  padding: 24px;
  max-width: 1200px;
  margin: 0 auto;
}

/* 模态框样式 */
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
  max-width: 500px;
  width: 90%;
  max-height: 80vh;
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
}

.modal-header h3 {
  margin: 0;
  font-size: 1.25rem;
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
  transition: background-color 0.2s ease;
}

.close-btn:hover {
  background-color: #f3f4f6;
}

.modal-body {
  padding: 24px;
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

.fund-info-display {
  background: #f9fafb;
  padding: 16px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}

.fund-info-display .fund-name {
  font-size: 1rem;
  font-weight: 500;
  color: #111827;
  margin-bottom: 4px;
}

.fund-info-display .fund-code {
  font-size: 0.875rem;
  color: #6b7280;
}

.form-input {
  width: 100%;
  padding: 12px 16px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  font-size: 1rem;
  transition: all 0.2s ease;
}

.form-input:focus {
  outline: none;
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.1);
}

.form-hint {
  font-size: 0.75rem;
  color: #6b7280;
  margin-top: 4px;
}

.modal-footer {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  padding: 20px 24px;
  border-top: 1px solid #e5e7eb;
}

.btn {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-secondary {
  background-color: #f3f4f6;
  color: #374151;
}

.btn-secondary:hover {
  background-color: #e5e7eb;
}

.btn-primary {
  background-color: #4f46e5;
  color: #fff;
}

.btn-primary:hover {
  background-color: #4338ca;
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn:disabled:hover {
  background-color: #4f46e5;
}

.tag-input-container {
  position: relative;
}

.tag-dropdown {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: #fff;
  border: 2px solid #e5e7eb;
  border-radius: 8px;
  margin-top: 4px;
  max-height: 200px;
  overflow-y: auto;
  z-index: 10;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
}

.dropdown-item {
  padding: 10px 16px;
  cursor: pointer;
  transition: all 0.2s ease;
  margin-bottom: 0;
}

.dropdown-item:hover {
  background-color: #f3f4f6;
  color: #1f2937;
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
</style>
