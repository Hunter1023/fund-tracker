<template>
  <div class="watchlist-container">
    <div class="filter-section">
      <div class="tag-tabs">
        <button
          @click="currentTag = ''"
          :class="['tag-tab', 'all-tab', !currentTag ? 'active' : '']"
        >
          全部 <span class="tag-count">({{ funds.length }})</span>
        </button>
        <button
          v-for="tag in allTags"
          :key="tag"
          @click="currentTag = tag"
          :class="['tag-tab', 'tag-item-tab', currentTag === tag ? `tag-${getTagColorIndex(tag)}` : '']"
        >
          <i class="bi bi-tag me-1"></i> {{ tag }} <span class="tag-count">({{ tagCounts[tag] || 0 }})</span>
        </button>
      </div>
    </div>

    <div v-if="loading" class="loading-container">
      <div class="spinner-border text-primary" role="status">
        <span class="visually-hidden">加载中...</span>
      </div>
    </div>

    <div v-else-if="filteredFunds.length === 0" class="empty-state">
      <div class="empty-icon">📊</div>
      <p>暂无基金</p>
    </div>

    <div v-else class="table-wrapper">
      <table class="custom-table">
        <thead>
          <tr>
            <th
              v-for="column in columns"
              :key="column.key"
              :data-column="column.key"
              :class="['table-header', { sortable: column.sortable }]"
              :style="{ minWidth: column.minWidth, width: column.width }"
              @click="column.sortable && handleSort(column.key)"
              draggable="true"
              @dragstart="handleDragStart(column.key)"
              @dragover.prevent
              @drop="handleDrop(column.key)"
            >
              <div class="header-content">
                <span>{{ column.label }}</span>
                <span v-if="column.sortable" class="sort-icon">
                    <i v-if="sortField === column.key" :class="sortDirection === 'asc' ? 'bi bi-caret-up-fill' : 'bi bi-caret-down-fill'" class="sort-active"></i>
                    <i v-else class="bi bi-caret-up-down"></i>
                  </span>
              </div>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="fund in filteredFunds" :key="fund.fund_code" class="table-row">
            <td v-for="column in columns" :key="column.key" :data-column="column.key">
              <template v-if="column.key === 'tags'">
                <div v-for="tag in (fund.tags || '').split(',').filter(t => t.trim())" :key="tag" class="tag-item">
                  <span class="tag-badge" :class="`tag-${getTagColorIndex(tag)}`" @click="currentTag = tag.trim()">
                    {{ tag.trim() }}
                  </span>
                </div>
              </template>
              <template v-else-if="column.key === 'name'">
                <div class="fund-name-cell">
                  <div class="fund-name clickable" @click="openFundDetail(fund)">{{ fund.fund_name }}</div>
                  <div class="fund-code">
                    {{ fund.fund_code }}
                    <span v-if="isHolding(fund.fund_code)" class="holding-badge">持有</span>
                    <span v-if="isUpdatedToday(fund)" class="update-badge">已更新</span>
                  </div>
                </div>
              </template>
              <template v-else-if="column.key === 'daily_change_rate'">
                <div class="rate-cell" :style="{ color: getChangeRateColor(fund.daily_change_rate) }">
                  <div class="rate-value">{{ fund.daily_change_rate }}%</div>
                  <div v-if="!isUpdatedToday(fund)" class="rate-date">{{ getMonthDay(fund.fsrq || fund.net_value) }}</div>
                </div>
              </template>
              <template v-else-if="column.key === 'estimate_change_rate'">
                <div class="rate-value" :style="{ color: getChangeRateColor(fund.estimate_change_rate) }">
                  {{ fund.estimate_change_rate }}%
                </div>
              </template>
              <template v-else-if="column.key === 'one_month_rate'">
                <div class="rate-value" :style="{ color: getChangeRateColor(fund.one_month_rate) }">
                  {{ fund.one_month_rate !== undefined ? fund.one_month_rate.toFixed(2) + '%' : '-' }}
                </div>
              </template>
              <template v-else-if="column.key === 'three_month_rate'">
                <div class="rate-value" :style="{ color: getChangeRateColor(fund.three_month_rate) }">
                  {{ fund.three_month_rate !== undefined ? fund.three_month_rate.toFixed(2) + '%' : '-' }}
                </div>
              </template>
              <template v-else-if="column.key === 'one_year_rate'">
                <div class="rate-value" :style="{ color: getChangeRateColor(fund.one_year_rate) }">
                  {{ fund.one_year_rate !== undefined ? fund.one_year_rate.toFixed(2) + '%' : '-' }}
                </div>
              </template>
              <template v-else-if="column.key === 'action'">
                <div class="action-cell">
                  <button
                    class="action-btn btn-delete"
                    @click="confirmRemoveFromWatchlist(fund)"
                  >
                    <i class="bi bi-trash"></i>
                  </button>
                </div>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <FundDetailModal
      v-model:show="showDetailModal"
      :fund-data="currentFund"
      :holding-data="currentHolding"
      @confirm="handleConfirm"
    />

    <ConfirmDialog
      v-model:show="showConfirmDialog"
      :message="confirmMessage"
      @confirm="handleConfirmDelete"
    />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useHoldings } from '../composables/useHoldings'
import { useWatchlist } from '../composables/useWatchlist'
import ConfirmDialog from './ConfirmDialog.vue'
import FundDetailModal from './FundDetailModal.vue'

const {
  funds,
  loading,
  currentTag,
  sortField,
  sortDirection,
  columnOrder,
  filteredFunds,
  allTags,
  tagCounts,
  loadWatchlist,
  addToWatchlist,
  removeFromWatchlist,
  handleSort,
  handleDragStart,
  handleDrop,
  getCurrentDate,
  getChangeRateColor
} = useWatchlist()

const {
  holdings,
  loadHoldings
} = useHoldings()

onMounted(() => {
  loadHoldings()
})

const showDetailModal = ref(false)
const currentFund = ref(null)
const currentHolding = ref(null)

const showConfirmDialog = ref(false)
const confirmMessage = ref('')
const fundToDelete = ref(null)

const columns = [
  { key: 'tags', label: '板块', sortable: true, minWidth: '80px', width: '120px' },
  { key: 'name', label: '名称', sortable: true, minWidth: '120px', width: '180px' },
  { key: 'daily_change_rate', label: '最新涨幅', sortable: true },
  { key: 'estimate_change_rate', label: '估算涨幅', sortable: true },
  { key: 'one_month_rate', label: '近1月', sortable: true },
  { key: 'three_month_rate', label: '近3月', sortable: true },
  { key: 'one_year_rate', label: '近1年', sortable: true },
  { key: 'action', label: '操作', sortable: false }
]

function isUpdatedToday(fund) {
  const netValueDate = fund.fsrq || fund.net_value
  if (!netValueDate) return false
  return netValueDate === getCurrentDate()
}

function getMonthDay(dateStr) {
  if (!dateStr) return ''
  const dateParts = dateStr.split('-')
  if (dateParts.length >= 3) {
    return `${dateParts[1]}-${dateParts[2]}`
  }
  return ''
}

function getTagColorIndex(tag) {
  const colors = ['blue', 'green', 'orange', 'purple', 'teal', 'pink']
  let hash = 0
  for (let i = 0; i < tag.length; i++) {
    hash = tag.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}

function isHolding(fundCode) {
  return holdings.value.some(holding => holding.fund_code === fundCode)
}

function openFundDetail(fund) {
  if (!fund) return
  
  const holding = holdings.value.find(h => h.fund_code === fund.fund_code)
  
  currentFund.value = {
    fund_code: fund.fund_code,
    fund_name: fund.fund_name,
    tags: fund.tags
  }
  
  if (holding) {
    currentHolding.value = {
      current_value: holding.current_value || holding.cost,
      shares: holding.shares,
      avg_cost: holding.avg_cost,
      profit_loss: holding.profit_loss || 0,
      profit_loss_rate: holding.profit_loss_rate
    }
  } else {
    currentHolding.value = null
  }
  
  showDetailModal.value = true
}

function confirmRemoveFromWatchlist(fund) {
  const fundName = fund.fund_name || fund.fund_code
  confirmMessage.value = `确定要将"${fundName}"从自选列表中移除吗？`
  fundToDelete.value = fund
  showConfirmDialog.value = true
}

function handleConfirmDelete() {
  if (fundToDelete.value) {
    removeFromWatchlist(fundToDelete.value.fund_code)
    fundToDelete.value = null
  }
}

function handleConfirm() {
  loadWatchlist()
  loadHoldings()
}

defineExpose({
  loadWatchlist,
  addToWatchlist
})
</script>

<style scoped>
.watchlist-container {
  width: 100%;
}

.filter-section {
  margin-bottom: 24px;
}

.tag-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.tag-tab {
  padding: 8px 16px;
  border: none;
  border-radius: 20px;
  font-size: 0.875rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-item-tab {
  background-color: #f3f4f6;
  color: #6b7280;
}

.tag-item-tab:hover {
  background-color: #e5e7eb;
}

.tag-item-tab.tag-blue,
.tag-item-tab.tag-green,
.tag-item-tab.tag-orange,
.tag-item-tab.tag-purple,
.tag-item-tab.tag-teal,
.tag-item-tab.tag-pink {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.all-tab {
  background-color: #e5e7eb;
  color: #374151;
}

.all-tab:hover {
  background-color: #d1d5db;
}

.all-tab.active {
  background-color: #374151;
  color: #fff;
  box-shadow: 0 2px 8px rgba(55, 65, 81, 0.3);
}

.tag-count {
  opacity: 0.8;
  font-size: 0.8rem;
  margin-left: 2px;
}

.loading-container {
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

.table-wrapper {
  overflow-x: auto;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.custom-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: #fff;
}

.table-header {
  background: #495057;
  color: #fff;
  padding: 14px 16px;
  font-weight: 600;
  font-size: 0.875rem;
  text-align: left;
  border: none;
  position: relative;
}

.table-header:first-child {
  border-top-left-radius: 12px;
}

.table-header:last-child {
  border-top-right-radius: 12px;
}

.table-header.sortable {
  cursor: pointer;
  user-select: none;
}

.table-header.sortable:hover {
  background: #343a40;
}

.header-content {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sort-icon i {
  opacity: 0.5;
  font-size: 0.75rem;
  color: #fff;
  transition: all 0.2s ease;
}

.sort-icon .sort-active {
  opacity: 1;
  color: #fff;
}

.table-header:hover .sort-icon i {
  opacity: 0.8;
}

.table-row {
  transition: background-color 0.2s ease;
}

.table-row:hover {
  background-color: #f9fafb;
}

.table-row td {
  padding: 16px;
  border-bottom: 1px solid #e5e7eb;
  font-size: 0.875rem;
}

.table-row:last-child td {
  border-bottom: none;
}

.table-row:last-child td:first-child {
  border-bottom-left-radius: 12px;
}

.table-row:last-child td:last-child {
  border-bottom-right-radius: 12px;
}

.tag-item {
  margin-bottom: 6px;
}

.tag-badge {
  display: inline-block;
  padding: 4px 12px;
  font-size: 0.75rem;
  font-weight: 500;
  border-radius: 4px;
  color: #fff;
  cursor: pointer;
  transition: all 0.2s ease;
  border: 1px solid transparent;
}

.tag-badge:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.tag-blue {
  background-color: #eff6ff;
  color: #1e40af;
  border-color: #bfdbfe;
}

.tag-green {
  background-color: #ecfdf5;
  color: #065f46;
  border-color: #a7f3d0;
}

.tag-orange {
  background-color: #fffbeb;
  color: #92400e;
  border-color: #fcd34d;
}

.tag-purple {
  background-color: #f5f3ff;
  color: #5b21b6;
  border-color: #ddd6fe;
}

.tag-teal {
  background-color: #ccfbf1;
  color: #0d9488;
  border-color: #99f6e4;
}

.tag-pink {
  background-color: #fdf2f8;
  color: #be185d;
  border-color: #fbcfe8;
}

.fund-name-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.fund-name {
  font-weight: 600;
  color: #1f2937;
  font-size: 0.95rem;
}

.fund-name.clickable {
  cursor: pointer;
  transition: color 0.2s ease;
}

.fund-name.clickable:hover {
  color: #4f46e5;
}

.fund-code {
  font-size: 0.8rem;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 6px;
}

.update-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 0.7rem;
  font-weight: 500;
  border-radius: 12px;
  background-color: #d1fae5;
  color: #059669;
}

.holding-badge {
  display: inline-block;
  padding: 2px 8px;
  font-size: 0.7rem;
  font-weight: 500;
  border-radius: 12px;
  background-color: #dbeafe;
  color: #2563eb;
  margin-right: 6px;
}

.rate-cell {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.rate-value {
  font-weight: 600;
  font-size: 0.95rem;
}

.rate-date {
  font-size: 0.75rem;
  color: #9ca3af;
}

.action-cell {
  display: flex;
  gap: 8px;
}

.action-btn {
  padding: 6px 12px;
  border: none;
  border-radius: 8px;
  font-size: 0.8rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-edit {
  background-color: #4f46e5;
  color: #fff;
}

.btn-edit:hover {
  background-color: #4338ca;
  transform: translateY(-1px);
}

.btn-delete {
  background-color: #ef4444;
  color: #fff;
  padding: 6px 10px;
}

.btn-delete:hover {
  background-color: #dc2626;
  transform: translateY(-1px);
}
</style>
