<template>
  <div class="holdings-container">
    <div v-if="loading" class="skeleton-container">
      <div class="skeleton-summary">
        <div v-for="i in 5" :key="i" class="skeleton-summary-item">
          <div class="skeleton-label"></div>
          <div class="skeleton-value"></div>
        </div>
      </div>
      <div class="skeleton-table">
        <div v-for="i in 5" :key="i" class="skeleton-row">
          <div v-for="j in 9" :key="j" class="skeleton-cell"></div>
        </div>
      </div>
    </div>

    <div v-else>
      <div class="platform-tabs">
        <button
          v-for="platform in platforms"
          :key="platform"
          :class="['platform-tab', { active: selectedPlatform === platform }]"
          @click="selectedPlatform = platform"
        >
          {{ platform }}
        </button>
        <button
          class="platform-tab manage-tab"
          @click="showPlatformManager = true"
          title="管理平台"
        >
          <i class="bi bi-gear"></i>
        </button>
      </div>

      <div class="summary-card">
        <div class="summary-item">
          <div class="summary-label">今日收益</div>
          <div class="summary-value" :class="summary.totalTodayProfit >= 0 ? 'profit-positive' : 'profit-negative'">
            ¥{{ formatAmount(summary.totalTodayProfit) }}
          </div>
        </div>
        <div class="summary-item">
          <div class="summary-label">持有收益</div>
          <div class="summary-value" :class="summary.totalProfit >= 0 ? 'profit-positive' : 'profit-negative'">
            ¥{{ formatAmount(summary.totalProfit) }} ({{ summary.totalProfitRate.toFixed(2) }}%)
          </div>
        </div>
        <div class="summary-item">
          <div class="summary-label">总金额</div>
          <div class="summary-value">¥{{ formatAmount(summary.totalValue) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">总成本</div>
          <div class="summary-value">¥{{ formatAmount(summary.totalAmount) }}</div>
        </div>
        <div class="summary-item">
          <div class="summary-label">基金数量</div>
          <div class="summary-value">{{ summary.fundCount }}</div>
        </div>
      </div>

      <!-- 板块分布 - 可展开/收起 -->
      <div class="sector-distribution-section">
        <div class="sector-header" @click="showSectorDistribution = !showSectorDistribution">
          <h3 class="sector-title">板块分布</h3>
          <i :class="showSectorDistribution ? 'bi bi-chevron-up' : 'bi bi-chevron-down'" class="toggle-icon"></i>
        </div>
        <div v-if="showSectorDistribution && sortedHoldings.length > 0" class="chart-container">
          <div class="pie-chart-wrapper" style="display: flex; align-items: center; gap: 20px;">
            <div style="flex: 1;">
              <canvas ref="pieChart"></canvas>
            </div>
            <div ref="legendContainer" class="custom-legend" style="width: 300px;"></div>
          </div>
        </div>
      </div>

      <div v-if="sortedHoldings.length === 0" class="empty-state">
        <div class="empty-icon">💼</div>
        <p>暂无持仓</p>
        <div class="action-bar empty-action-bar">
          <button 
            class="sync-btn"
            @click="showSearchModal = true"
            :disabled="loading"
          >
            <i class="bi bi-plus-circle me-2"></i>添加持仓
          </button>
        </div>
      </div>

      <div v-else>
        <div class="table-container">
        <div class="table-wrapper">
          <table class="custom-table">
            <thead>
              <tr>
                <th
                  v-for="column in columns"
                  :key="column.key"
                  :class="['table-header', { sortable: column.sortable }]"
                  @click="column.sortable && handleSort(column.key)"
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
              <tr v-for="holding in sortedHoldings" :key="`${holding.fund_code}-${holding.platform || '其他'}`" class="table-row">
                <td>
                  <div v-for="tag in (holding.tags || '').split(',').filter(t => t.trim())" :key="tag" class="tag-item">
                    <span class="tag-badge" :class="`tag-${getTagColorIndex(tag)}`">
                      {{ tag.trim() }}
                    </span>
                  </div>
                </td>
                <td>
                  <div class="fund-name-cell">
                    <div class="fund-name clickable" @click="openFundDetail(holding)">{{ holding.fund_name }}</div>
                    <div class="fund-info-row">
                      <span v-if="isUpdatedToday(holding)" class="badge update-badge">已更新</span>
                      <div class="fund-code">
                        {{ holding.fund_code }}
                      </div>
                    </div>
                  </div>
                </td>
                <td>
                  <div class="rate-cell" :style="{ color: getChangeRateColor(holding.daily_change_rate) }">
                    <div class="rate-value">{{ holding.daily_change_rate }}%</div>
                    <div v-if="!isUpdatedToday(holding)" class="rate-date">{{ getMonthDay(holding.fsrq) }}</div>
                  </div>
                </td>
                <td>
                  <div class="rate-value" :style="{ color: getChangeRateColor(holding.estimate_change_rate) }">
                    {{ holding.estimate_change_rate }}%
                  </div>
                </td>
                <td>
                  <div class="rate-value" :style="{ color: getChangeRateColor(holding.estimate_profit) }">
                    ¥{{ formatAmount(holding.estimate_profit || 0) }}
                  </div>
                </td>
                <td>
                  <div class="rate-value" :style="{ color: getChangeRateColor(holding.one_month_rate) }">
                    {{ (holding.one_month_rate || 0).toFixed(2) }}%
                  </div>
                </td>
                <td>
                  <div class="rate-cell" :style="{ color: getChangeRateColor(calculateProfit(holding)) }">
                    <div class="rate-value">¥{{ formatAmount(calculateProfit(holding)) }}</div>
                    <div class="rate-value">{{ calculateProfitRate(holding).toFixed(2) }}%</div>
                  </div>
                </td>
                <td>
                  <div class="rate-value">¥{{ formatAmount(holding.current_value) }}</div>
                </td>
                <td>
                  <div class="rate-value">¥{{ formatAmount(holding.cost) }}</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="action-bar">
          <button 
            class="sync-btn"
            @click="showSearchModal = true"
            :disabled="loading"
          >
            <i class="bi bi-plus-circle me-2"></i>添加持仓
          </button>
        </div>
        </div>
      </div>
    </div>

    <FundDetailModal
      v-model:show="showDetailModal"
      :fund-data="currentFund"
      :holding-data="currentHolding"
      :platform="selectedPlatform"
      @confirm="handleDetailConfirm"
    />

    <SearchFundModal
      v-model:show="showSearchModal"
      :platform="selectedPlatform"
      @select="handleSelectFund"
    />

    <PlatformManager
      v-model:show="showPlatformManager"
      @update="loadPlatforms"
    />
  </div>
</template>

<script setup>
import Chart from 'chart.js/auto'
import { nextTick, onMounted, ref, watch } from 'vue'
import { useHoldings } from '../composables/useHoldings'
import FundDetailModal from './FundDetailModal.vue'
import PlatformManager from './PlatformManager.vue'
import SearchFundModal from './SearchFundModal.vue'

const {
  holdings,
  loading,
  isLoaded,
  sortField,
  sortDirection,
  sortedHoldings,
  platforms,
  selectedPlatform,
  summary,
  loadHoldings,
  loadPlatforms,
  handleSort,
  getCurrentDate,
  getChangeRateColor
} = useHoldings()

const pieChart = ref(null)
const legendContainer = ref(null)
let chartInstance = null

const showDetailModal = ref(false)
const currentFund = ref(null)
const currentHolding = ref(null)
const showSearchModal = ref(false)
const showPlatformManager = ref(false)
const showSectorDistribution = ref(false)

function openFundDetail(holding) {
  if (!holding) return
  
  currentFund.value = {
    fund_code: holding.fund_code,
    fund_name: holding.fund_name,
    tags: holding.tags || ''
  }
  currentHolding.value = {
    current_value: holding.current_value || holding.cost,
    cost: holding.cost,
    shares: holding.shares,
    avg_cost: holding.avg_cost,
    profit_loss: holding.profit_loss || 0,
    platform: holding.platform
  }
  showDetailModal.value = true
}

async function handleDetailConfirm() {
  await loadHoldings()
}

function handleSelectFund(fund) {
  currentFund.value = {
    fund_code: fund.fund_code,
    fund_name: fund.fund_name
  }
  currentHolding.value = null
  showDetailModal.value = true
}

function openAddHolding() {
  showSearchModal.value = true
}

// 组件挂载时自动加载数据
onMounted(async () => {
  await loadHoldings()
  await nextTick()
  updatePieChart()
})

// 监听持仓数据变化，更新饼图
watch(sortedHoldings, async () => {
  await nextTick()
  updatePieChart()
}, { deep: true })

// 监听展开状态变化，当展开时更新饼图
watch(showSectorDistribution, async (newValue) => {
  if (newValue) {
    await nextTick()
    updatePieChart()
  }
})

// 按板块汇总持仓
function getSectorSummary() {
  const sectorMap = new Map()
  const totalAmount = sortedHoldings.value.reduce((sum, holding) => sum + holding.cost, 0)
  
  sortedHoldings.value.forEach(holding => {
    const sector = holding.tags || '未分类'
    const currentAmount = sectorMap.get(sector) || 0
    sectorMap.set(sector, currentAmount + holding.cost)
  })
  
  const sectors = []
  sectorMap.forEach((amount, sector) => {
    sectors.push({
      sector,
      amount,
      percentage: totalAmount > 0 ? (amount / totalAmount) * 100 : 0
    })
  })
  
  return sectors.sort((a, b) => b.amount - a.amount)
}

// 更新饼图
function updatePieChart() {
  if (!pieChart.value || !showSectorDistribution.value) return
  
  const sectors = getSectorSummary()
  const labels = sectors.map(s => s.sector)
  const data = sectors.map(s => s.amount)
  
  // 生成按成本占比渐变的彩虹颜色（清新明亮，相邻颜色有明显跨度）
  function generateGradientColors(sectors) {
    const colors = []
    
    sectors.forEach((sector, index) => {
      // 计算色相：均匀分布在彩虹色谱上（0-360度）
      const hue = (index / sectors.length) * 360
      
      // 饱和度：使用中等饱和度（50-60%），颜色更鲜艳
      const saturation = 55
      
      // 亮度：根据占比调整，占比越大亮度越低（颜色越深）
      const maxPercentage = sectors[0].percentage
      const minPercentage = sectors[sectors.length - 1].percentage
      
      let lightness
      if (maxPercentage === minPercentage) {
        lightness = 65
      } else {
        // 占比越大亮度越低（40-75%之间）
        const ratio = sector.percentage / maxPercentage
        lightness = 75 - ratio * 35
      }
      
      colors.push(`hsl(${hue}, ${saturation}%, ${lightness}%)`)
    })
    
    return colors
  }
  
  // 销毁旧图表
  if (chartInstance) {
    chartInstance.destroy()
  }
  
  // 创建新图表
  const backgroundColors = generateGradientColors(sectors)
  chartInstance = new Chart(pieChart.value, {
    type: 'doughnut',
    data: {
      labels: labels,
      datasets: [{
        data: data,
        backgroundColor: backgroundColors,
        borderColor: '#fff',
        borderWidth: 3,
        hoverOffset: 15
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '50%',
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          padding: 12,
          cornerRadius: 8,
          callbacks: {
            label: function(context) {
              const label = context.label || ''
              const value = context.raw || 0
              const percentage = sectors[context.dataIndex].percentage.toFixed(2)
              return `${label}: ¥${value.toFixed(2)} (${percentage}%)`
            }
          }
        }
      },
      animation: {
        animateRotate: true,
        animateScale: true
      }
    }
  })
  
  // 生成自定义图例
  generateCustomLegend(sectors, backgroundColors)
}

// 生成自定义图例
function generateCustomLegend(sectors, backgroundColors) {
  if (!legendContainer.value) return
  
  // 清空容器
  legendContainer.value.innerHTML = ''
  
  // 每列6个图示
  const itemsPerColumn = 6
  const columns = Math.ceil(sectors.length / itemsPerColumn)
  
  // 创建容器
  const legendWrapper = document.createElement('div')
  legendWrapper.style.display = 'flex'
  legendWrapper.style.flexDirection = 'row'
  legendWrapper.style.gap = '32px'
  legendWrapper.style.alignItems = 'flex-start'
  
  // 生成列
  for (let i = 0; i < columns; i++) {
    const column = document.createElement('div')
    column.style.display = 'flex'
    column.style.flexDirection = 'column'
    column.style.gap = '12px'
    
    // 生成当前列的图例项
    const startIndex = i * itemsPerColumn
    const endIndex = Math.min(startIndex + itemsPerColumn, sectors.length)
    
    for (let j = startIndex; j < endIndex; j++) {
      const sector = sectors[j]
      const item = document.createElement('div')
      item.style.display = 'flex'
      item.style.alignItems = 'center'
      item.style.gap = '10px'
      item.style.fontSize = '12px'
      item.style.whiteSpace = 'nowrap'
      
      // 颜色块
      const colorBox = document.createElement('div')
      colorBox.style.width = '16px'
      colorBox.style.height = '16px'
      colorBox.style.borderRadius = '6px'
      colorBox.style.backgroundColor = backgroundColors[j]
      
      // 文本
      const text = document.createElement('span')
      const percentage = sector.percentage.toFixed(1)
      text.textContent = `${sector.sector} (${percentage}%)`
      
      item.appendChild(colorBox)
      item.appendChild(text)
      column.appendChild(item)
    }
    
    legendWrapper.appendChild(column)
  }
  
  legendContainer.value.appendChild(legendWrapper)
}

const columns = [
  { key: 'tags', label: '板块', sortable: true },
  { key: 'name', label: '名称', sortable: true },
  { key: 'daily_change_rate', label: '最新涨幅', sortable: true },
  { key: 'estimate_change_rate', label: '估算涨幅', sortable: true },
  { key: 'estimate_profit', label: '今日收益', sortable: true },
  { key: 'one_month_rate', label: '近1月收益率', sortable: true },
  { key: 'profit', label: '持有收益', sortable: true },
  { key: 'current_value', label: '持仓金额', sortable: true },
  { key: 'cost', label: '持仓成本', sortable: true }
]

function isUpdatedToday(holding) {
  const fsrq = holding.fsrq || ''
  if (!fsrq) return false
  return fsrq === getCurrentDate()
}

function getMonthDay(dateStr) {
  if (!dateStr) return ''
  const dateParts = dateStr.split('-')
  if (dateParts.length >= 3) {
    return `${dateParts[1]}-${dateParts[2]}`
  }
  return ''
}

function calculateProfit(holding) {
  return parseFloat(holding.profit_loss) || 0
}

function calculateProfitRate(holding) {
  return parseFloat(holding.profit_loss_rate) || 0
}

function getTagColorIndex(tag) {
  const colors = ['blue', 'green', 'orange', 'purple', 'teal', 'pink']
  let hash = 0
  for (let i = 0; i < tag.length; i++) {
    hash = tag.charCodeAt(i) + ((hash << 5) - hash)
  }
  return colors[Math.abs(hash) % colors.length]
}

function formatAmount(amount) {
  return parseFloat(amount).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

defineExpose({
  loadHoldings
})
</script>

<style scoped>
.holdings-container {
  width: 100%;
}

.platform-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  padding: 0 4px;
  overflow-x: auto;
  scrollbar-width: thin;
}

.platform-tabs::-webkit-scrollbar {
  height: 6px;
}

.platform-tabs::-webkit-scrollbar-track {
  background: #f1f1f1;
  border-radius: 3px;
}

.platform-tabs::-webkit-scrollbar-thumb {
  background: #c1c1c1;
  border-radius: 3px;
}

.platform-tabs::-webkit-scrollbar-thumb:hover {
  background: #a1a1a1;
}

.platform-tab {
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  font-size: 0.9rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;
  background: #f5f7fa;
  color: #6b7280;
  white-space: nowrap;
}

.platform-tab:hover {
  background: #e5e7eb;
  color: #374151;
}

.platform-tab.active {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.platform-tab.manage-tab {
  padding: 10px 14px;
  background: #f3f4f6;
  color: #6b7280;
}

.platform-tab.manage-tab:hover {
  background: #e5e7eb;
  color: #374151;
}

.sync-btn {
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

.sync-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.sync-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.empty-action-bar {
  margin-top: 24px;
  display: flex;
  justify-content: center;
}

.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  padding: 60px 20px;
}

.skeleton-container {
  padding: 20px;
}

.skeleton-summary {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  margin-bottom: 24px;
  padding: 20px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
  border-radius: 12px;
}

.skeleton-summary-item {
  text-align: center;
}

.skeleton-label {
  height: 14px;
  background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
  margin-bottom: 8px;
  width: 60%;
  margin-left: auto;
  margin-right: auto;
}

.skeleton-value {
  height: 32px;
  background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
  width: 80%;
  margin-left: auto;
  margin-right: auto;
}

.skeleton-table {
  background: #fff;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}

.skeleton-row {
  display: grid;
  grid-template-columns: repeat(9, 1fr);
  gap: 8px;
  padding: 16px;
  border-bottom: 1px solid #f0f0f0;
}

.skeleton-row:last-child {
  border-bottom: none;
}

.skeleton-cell {
  height: 24px;
  background: linear-gradient(90deg, #e0e0e0 25%, #f0f0f0 50%, #e0e0e0 75%);
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
  border-radius: 4px;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

@media (max-width: 768px) {
  .skeleton-summary {
    grid-template-columns: 1fr;
  }
  
  .skeleton-row {
    grid-template-columns: repeat(3, 1fr);
  }
}

.summary-card {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 12px;
  margin-bottom: 24px;
  padding: 20px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}

.summary-item {
  text-align: center;
}

.summary-label {
  font-size: 0.875rem;
  color: #6b7280;
  margin-bottom: 8px;
}

.summary-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #1f2937;
}

.profit-positive {
  color: #ef4444;
}

.profit-negative {
  color: #10b981;
}

.table-header-title {
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
  margin-bottom: 16px;
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

.table-container {
  position: relative;
  margin-bottom: 24px;
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

.custom-table th:nth-child(2),
.custom-table td:nth-child(2) {
  width: 180px;
  max-width: 180px;
  min-width: 180px;
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

.fund-info-row {
  display: flex;
  align-items: center;
  gap: 8px;
  white-space: nowrap;
}

.fund-code {
  font-size: 0.8rem;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 6px;
}

.badge {
  display: inline-block;
  padding: 3px 10px;
  font-size: 0.7rem;
  font-weight: 500;
  border-radius: 16px;
  line-height: 1.2;
}

.update-badge {
  background-color: #d1fae5;
  color: #059669;
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



.pie-chart-wrapper {
  position: relative;
  height: 320px;
  max-width: 100%;
  margin: 0 auto;
  width: 100%;
}

/* 移除3D阴影效果 */
/* .pie-chart-wrapper::before {
  content: '';
  position: absolute;
  left: 50%;
  top: 50%;
  transform: translate(-50%, -45%);
  width: 60%;
  height: 60%;
  background: radial-gradient(ellipse at center, rgba(0,0,0,0.15) 0%, rgba(0,0,0,0) 70%);
  border-radius: 50%;
  z-index: 0;
  pointer-events: none;
} */

.action-bar {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
  padding: 0;
  background: transparent;
  border-radius: 0;
  box-shadow: none;
  align-items: center;
}

.sector-distribution-section {
  margin-bottom: 24px;
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
  overflow: hidden;
}

.sector-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%);
  cursor: pointer;
  transition: all 0.2s ease;
}

.sector-header:hover {
  background: linear-gradient(135deg, #e4e8ec 0%, #d5d9df 100%);
}

.sector-title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
  color: #1f2937;
}

.toggle-icon {
  font-size: 1rem;
  color: #6b7280;
  transition: transform 0.2s ease;
}

.chart-container {
  padding: 20px;
  background: #fff;
  border-radius: 0 0 12px 12px;
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 768px) {
  .summary-card {
    grid-template-columns: 1fr;
  }
  
  .summary-value {
    font-size: 1.25rem;
  }
  
  .action-bar {
    padding: 0;
  }
  
  .table-container {
    margin-bottom: 16px;
  }
  
  .pie-chart-wrapper {
    height: 250px;
  }
  
  .chart-container {
    padding: 16px;
  }
}
</style>
