<template>
  <div class="modal-overlay" :class="{ show: show }" :style="{ display: show ? 'flex' : 'none' }">
    <div class="modal-container">
      <div class="modal-header">
        <h3 class="modal-title">基金详情</h3>
        <button type="button" class="close-btn" @click="$emit('update:show', false)">
          <i class="bi bi-x-lg"></i>
        </button>
      </div>
      <div class="modal-body">
        <div class="fund-info" v-if="fundData">
          <div class="fund-name-row">
            <div class="fund-name">{{ fundData.fund_name }}</div>
            <div class="fund-tags" :class="{ 'no-tags': !fundTags }">
              <span class="tag-item" v-if="fundTags">{{ fundTags }}</span>
              <span class="tag-item no-tag" v-else>未分类</span>
              <button type="button" class="edit-tag-btn" @click="showEditTagModal" title="修改板块">
                <i class="bi bi-pencil-square"></i>
              </button>
            </div>
          </div>
          <div class="fund-code">{{ fundData.fund_code }}</div>
        </div>

        <div class="holding-info" v-if="holdingData">
          <div class="info-row">
            <span class="info-label">持仓金额</span>
            <span class="info-value">¥{{ formatAmount(holdingData.current_value || holdingData.cost) }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">持有份额</span>
            <span class="info-value">{{ holdingData.shares.toFixed(2) }}</span>
          </div>
          <div class="info-row">
            <span class="info-label">平均成本</span>
            <span class="info-value">¥{{ formatAmount4(holdingData.avg_cost) }}</span>
          </div>
        </div>

        <div class="chart-section" v-if="fundData">
          <div class="chart-header">
            <h4 class="chart-title">历史净值走势</h4>
            <div class="time-range-selector">
              <button
                v-for="range in timeRanges"
                :key="range.value"
                class="range-btn"
                :class="{ active: selectedRange === range.value }"
                @click="changeTimeRange(range.value)"
              >
                {{ range.label }}
              </button>
            </div>
          </div>
          <div class="chart-wrapper" v-if="!chartLoading">
            <canvas ref="chartCanvas"></canvas>
          </div>
          <div class="chart-loading" v-else>
            <div class="spinner-border text-primary" role="status">
              <span class="visually-hidden">加载中...</span>
            </div>
          </div>
        </div>

        <div v-if="holdingData">
          <div class="tabs">
            <button
              class="tab-btn"
              :class="{ active: showOperation && activeTab === 'buy' }"
              @click="showOperationArea('buy')"
            >
              加仓
            </button>
            <button
              class="tab-btn"
              :class="{ active: showOperation && activeTab === 'sell' }"
              @click="showOperationArea('sell')"
            >
              减仓
            </button>
            <button
              class="tab-btn"
              :class="{ active: showOperation && activeTab === 'edit' }"
              @click="showOperationArea('edit')"
            >
              修改持仓
            </button>
            <button
              class="tab-btn delete-btn"
              :class="{ active: showOperation && activeTab === 'delete' }"
              @click="showOperationArea('delete')"
            >
              <i class="bi bi-trash"></i>
            </button>
          </div>

          <div v-if="showOperation" class="form-section">
            <div v-if="activeTab === 'buy'">
              <div class="form-group">
                <label class="form-label">加仓金额（元）</label>
                <input
                  type="number"
                  class="form-input"
                  :class="{ 'is-invalid': validationErrors.buyAmount }"
                  v-model="buyAmount"
                  placeholder="请输入加仓金额"
                  min="0"
                  step="0.01"
                >
                <div v-if="validationErrors.buyAmount" class="invalid-feedback">
                  {{ validationErrors.buyAmount }}
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">加仓日期</label>
                <input
                  type="date"
                  class="form-input"
                  v-model="buyDate"
                  :max="today"
                >
              </div>
            </div>
            <div v-else-if="activeTab === 'sell'">
              <div class="form-group">
                <label class="form-label">减仓份额</label>
                <input
                  type="number"
                  class="form-input"
                  :class="{ 'is-invalid': validationErrors.sellShares }"
                  v-model="sellShares"
                  placeholder="请输入减仓份额"
                  min="0"
                  step="0.01"
                >
                <div v-if="holdingData" class="hint-text">
                  可用份额：{{ holdingData.shares.toFixed(2) }}
                </div>
                <div v-if="validationErrors.sellShares" class="invalid-feedback">
                  {{ validationErrors.sellShares }}
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">减仓日期</label>
                <input
                  type="date"
                  class="form-input"
                  v-model="sellDate"
                  :max="today"
                >
              </div>
            </div>
            <div v-else-if="activeTab === 'edit'" class="form-section">
              <div class="form-group">
                <label class="form-label">平台</label>
                <select
                  class="form-input"
                  v-model="editPlatform"
                >
                  <option v-for="platform in platforms" :key="platform" :value="platform">
                    {{ platform }}
                  </option>
                </select>
              </div>
              <div class="form-group">
                <label class="form-label">持仓金额（元）</label>
                <input
                  type="number"
                  class="form-input"
                  :class="{ 'is-invalid': validationErrors.editAmount }"
                  v-model="editAmount"
                  placeholder="请输入持仓金额"
                  min="0"
                  step="0.01"
                >
                <div v-if="validationErrors.editAmount" class="invalid-feedback">
                  {{ validationErrors.editAmount }}
                </div>
              </div>
              <div class="form-group">
                <label class="form-label">持有收益（元）</label>
                <input
                  type="number"
                  class="form-input"
                  :class="{ 'is-invalid': validationErrors.editProfit }"
                  v-model="editProfit"
                  placeholder="请输入持有收益"
                  step="0.01"
                >
                <div v-if="validationErrors.editProfit" class="invalid-feedback">
                  {{ validationErrors.editProfit }}
                </div>
              </div>
              <div class="hint-text">
                当前持仓金额：¥{{ formatAmount(holdingData.current_value || holdingData.cost) }}，持有收益：¥{{ formatAmount(holdingData.profit_loss) }}
              </div>
            </div>
            <div v-else-if="activeTab === 'delete'" class="delete-confirm-section">
              <div class="delete-warning">
                <i class="bi bi-exclamation-triangle"></i>
                <span>确定要删除该基金的持仓吗？此操作不可恢复。</span>
              </div>
            </div>
            <div v-else-if="activeTab === 'tags'" class="form-section">
              <div class="form-group">
                <label class="form-label">板块标签</label>
                <input
                  type="text"
                  class="form-input"
                  :class="{ 'is-invalid': validationErrors.tags }"
                  v-model="tagsInput"
                  placeholder="请输入板块标签（如：Ai, 新能源）"
                >
                <div class="form-hint">多个标签请用逗号分隔</div>
                <div v-if="validationErrors.tags" class="invalid-feedback">
                  {{ validationErrors.tags }}
                </div>
              </div>
            </div>
            <div v-if="validationErrors.general" class="alert alert-danger mt-3">
              {{ validationErrors.general }}
            </div>
          </div>
        </div>

        <div v-else class="add-holding-section">
          <div v-if="!showAddHoldingForm">
            <button
              type="button"
              class="btn btn-primary btn-block"
              @click="showAddHoldingForm = true"
            >
              添加持仓
            </button>
          </div>
          <div v-else class="add-holding-form">
            <div class="form-group">
              <label class="form-label">平台</label>
              <select
                class="form-input"
                v-model="addPlatform"
              >
                <option v-for="platform in platforms" :key="platform" :value="platform">
                  {{ platform }}
                </option>
              </select>
            </div>
            <div class="form-group">
              <label class="form-label">板块标签</label>
              <input
                type="text"
                class="form-input"
                :class="{ 'is-invalid': validationErrors.addTags }"
                v-model="addTags"
                placeholder="请输入板块标签（如：Ai, 新能源）"
              >
              <div class="form-hint">多个标签请用逗号分隔</div>
              <div v-if="validationErrors.addTags" class="invalid-feedback">
                {{ validationErrors.addTags }}
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">持仓金额（元）</label>
              <input
                type="number"
                class="form-input"
                :class="{ 'is-invalid': validationErrors.addCurrentValue }"
                v-model="addCurrentValue"
                placeholder="请输入持仓金额"
                min="0"
                step="0.01"
              >
              <div v-if="validationErrors.addCurrentValue" class="invalid-feedback">
                {{ validationErrors.addCurrentValue }}
              </div>
            </div>
            <div class="form-group">
              <label class="form-label">持有收益（元）</label>
              <input
                type="number"
                class="form-input"
                :class="{ 'is-invalid': validationErrors.addProfit }"
                v-model="addProfit"
                placeholder="请输入持有收益"
                step="0.01"
              >
              <div v-if="validationErrors.addProfit" class="invalid-feedback">
                {{ validationErrors.addProfit }}
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="modal-footer" v-if="showOperation || showAddHoldingForm || showTagModal">
        <button type="button" class="btn btn-secondary" @click="handleCancel">取消</button>
        <button type="button" class="btn btn-primary" @click="handleConfirm" :disabled="loading">
          {{ loading ? '处理中...' : '确认' }}
        </button>
      </div>
    </div>

    <!-- 板块修改弹窗 -->
    <div class="modal-overlay" :class="{ show: showTagModal }" :style="{ display: showTagModal ? 'flex' : 'none' }">
      <div class="modal-container tag-modal">
        <div class="modal-header">
          <h3 class="modal-title">修改板块</h3>
          <button type="button" class="close-btn" @click="showTagModal = false">
            <i class="bi bi-x-lg"></i>
          </button>
        </div>
        <div class="modal-body">
          <div class="form-section">
            <div class="form-group">
              <label class="form-label">板块标签</label>
              <input
                type="text"
                class="form-input"
                :class="{ 'is-invalid': validationErrors.tags }"
                v-model="tagsInput"
                placeholder="请输入板块标签（如：Ai, 新能源）"
              >
              <div class="form-hint">多个标签请用逗号分隔</div>
              <div v-if="validationErrors.tags" class="invalid-feedback">
                {{ validationErrors.tags }}
              </div>
            </div>
            <div v-if="validationErrors.general" class="alert alert-danger mt-3">
              {{ validationErrors.general }}
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button type="button" class="btn btn-secondary" @click="showTagModal = false">取消</button>
          <button type="button" class="btn btn-primary" @click="confirmTagUpdate" :disabled="loading">
            {{ loading ? '处理中...' : '确认' }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import Chart from 'chart.js/auto'
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { fundApi, holdingApi, platformApi } from '../services/api'

function formatAmount(amount) {
  return parseFloat(amount).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })
}

function formatAmount4(amount) {
  return parseFloat(amount).toLocaleString('zh-CN', {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4
  })
}

const props = defineProps({
  show: Boolean,
  fundData: {
    type: Object,
    default: () => ({})
  },
  holdingData: {
    type: Object,
    default: null
  },
  platform: {
    type: String,
    default: ''
  }
})

const emit = defineEmits(['update:show', 'confirm'])

const activeTab = ref('buy')
const buyAmount = ref('')
const buyDate = ref('')
const sellShares = ref('')
const sellDate = ref('')
const editAmount = ref('')
const editProfit = ref('')
const editPlatform = ref('其他')
const addCurrentValue = ref('')
const addProfit = ref('')
const addTags = ref('')
const addPlatform = ref('其他')
const tagsInput = ref('')
const loading = ref(false)
const chartLoading = ref(false)
const selectedRange = ref('1month')
const chartCanvas = ref(null)
const platforms = ref(['其他'])
let chartInstance = null

const showOperation = ref(false)
const showAddHoldingForm = ref(false)
const showTagModal = ref(false)
const validationErrors = ref({})
const fundTags = ref('')

// 获取当前日期
const today = computed(() => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
})

const timeRanges = [
  { label: '近1周', value: '1week' },
  { label: '近1月', value: '1month' },
  { label: '近3月', value: '3month' },
  { label: '近1年', value: '1year' }
]

async function loadPlatforms() {
  try {
    const response = await platformApi.get()
    platforms.value = response.data.map(p => p.name)
  } catch (error) {
    console.error('加载平台列表失败:', error)
  }
}

watch(() => props.show, (newVal) => {
  if (newVal) {
    loadPlatforms()
    activeTab.value = 'buy'
    buyAmount.value = ''
    buyDate.value = today.value  // 设置默认加仓日期为当天
    sellShares.value = ''
    sellDate.value = today.value  // 设置默认减仓日期为当天
    editAmount.value = ''
    editProfit.value = ''
    addCurrentValue.value = ''
    addProfit.value = ''
    addTags.value = ''
    tagsInput.value = ''
    showOperation.value = false
    showAddHoldingForm.value = false
    fundTags.value = props.fundData.tags || ''
    
    // 如果是添加新持仓（holdingData为null），设置默认平台
    if (!props.holdingData && props.platform) {
      addPlatform.value = props.platform
    }
    
    // 异步加载历史数据，不阻塞其他操作
    loadHistoryData()
  }
})

watch(selectedRange, async () => {
  await loadHistoryData()
})

async function loadHistoryData() {
  if (!props.fundData || !props.fundData.fund_code) return

  chartLoading.value = true
  try {
    const [historyResponse, transactionResponse] = await Promise.all([
      fundApi.getHistory(props.fundData.fund_code),
      holdingApi.getTransactions(props.fundData.fund_code)
    ])
    
    const historyData = historyResponse.data
    const transactions = transactionResponse.data || []
    
    const filteredData = filterDataByRange(historyData.net_values, selectedRange.value)
    
    chartLoading.value = false
    await nextTick()
    
    if (chartCanvas.value) {
      renderChart(filteredData, transactions)
    } else {
      console.error('chartCanvas.value 不存在，无法渲染图表')
    }
  } catch (error) {
    console.error('加载历史数据失败:', error)
    chartLoading.value = false
  }
}

function filterDataByRange(data, range) {
  if (!data || data.length === 0) return []

  const latestDate = new Date(data[0].date)
  let startDate

  switch (range) {
    case '1week':
      startDate = new Date(latestDate.getTime() - 7 * 24 * 60 * 60 * 1000)
      break
    case '1month':
      startDate = new Date(latestDate.getTime() - 30 * 24 * 60 * 60 * 1000)
      break
    case '3month':
      startDate = new Date(latestDate.getTime() - 90 * 24 * 60 * 60 * 1000)
      break
    case '1year':
      startDate = new Date(latestDate.getTime() - 365 * 24 * 60 * 60 * 1000)
      break
    default:
      return data
  }

  const filtered = data.filter(item => {
    const itemDate = new Date(item.date)
    return itemDate >= startDate
  })

  return filtered
}

function renderChart(data, transactions) {
  if (!chartCanvas.value) {
    console.error('chartCanvas.value 不存在')
    return
  }

  if (!data || data.length === 0) {
    console.error('数据为空，无法渲染图表')
    return
  }

  if (chartInstance) {
    chartInstance.destroy()
  }

  const ctx = chartCanvas.value.getContext('2d')
  const reversedData = [...data].reverse()
  const labels = reversedData.map(item => {
    const dateParts = item.date.split('-')
    return `${dateParts[0]}-${dateParts[1]}-${dateParts[2]}`
  })
  
  const baseValue = parseFloat(reversedData[0].unit_net_value)
  const changeRates = reversedData.map(item => {
    const currentValue = parseFloat(item.unit_net_value)
    return ((currentValue - baseValue) / baseValue * 100).toFixed(2)
  })

  const transactionDates = new Set()
  const transactionMap = new Map()
  
  if (transactions && transactions.length > 0) {
    transactions.forEach(transaction => {
      const transactionDate = transaction.date.split(' ')[0]
      transactionDates.add(transactionDate)
      
      if (!transactionMap.has(transactionDate)) {
        transactionMap.set(transactionDate, transaction.type)
      }
    })
  }

  const pointRadius = reversedData.map(item => {
    return transactionDates.has(item.date) ? 5 : 0
  })
  
  const pointBackgroundColor = reversedData.map(item => {
    const transactionType = transactionMap.get(item.date)
    return transactionType === 'buy' ? '#22c55e' : '#ef4444'
  })

  const displayLabelIndices = []
  if (labels.length > 0) {
    displayLabelIndices.push(0)
    if (labels.length > 1) {
      displayLabelIndices.push(Math.floor(labels.length / 2))
    }
    if (labels.length > 2) {
      displayLabelIndices.push(labels.length - 1)
    }
  }

  const labelCallback = function(value, index, values) {
    const dataIndex = index
    if (displayLabelIndices.includes(dataIndex)) {
      return labels[dataIndex]
    }
    return ''
  }

  try {
    chartInstance = new Chart(ctx, {
      type: 'line',
      data: {
        labels: labels,
        datasets: [
          {
            label: '',
            data: changeRates,
            borderColor: '#667eea',
            backgroundColor: 'transparent',
            fill: false,
            tension: 0,
            pointRadius: pointRadius,
            pointBackgroundColor: pointBackgroundColor,
            pointBorderColor: '#fff',
            pointBorderWidth: 2,
            pointHoverRadius: 7
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: 'index',
          intersect: false
        },
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            callbacks: {
              title: function(context) {
                const item = reversedData[context[0].dataIndex]
                return item.date
              },
              label: function(context) {
                const value = context.raw
                const item = reversedData[context.dataIndex]
                const transactionType = transactionMap.get(item.date)
                
                let result = `${value}%`
                if (transactionType) {
                  result += ` (${transactionType === 'buy' ? '加仓' : '减仓'})`
                }
                return result
              }
            }
          }
        },
        scales: {
          x: {
            grid: {
              display: false
            },
            ticks: {
              callback: function(value, index, values) {
                if (displayLabelIndices.includes(index)) {
                  return labels[index]
                }
                return ''
              },
              autoSkip: false,
              maxRotation: 0,
              minRotation: 0,
              font: {
                size: 10
              }
            }
          },
          y: {
            type: 'linear',
            display: true,
            position: 'left',
            title: {
              display: true,
              text: '涨幅(%)'
            },
            grid: {
              color: 'rgba(0, 0, 0, 0.05)'
            }
          }
        }
      }
    })
  } catch (error) {
    console.error('创建图表时出错:', error)
  }
}

async function changeTimeRange(range) {
  selectedRange.value = range
}

function showEditTagModal() {
  tagsInput.value = fundTags.value || ''
  validationErrors.value = {}
  showTagModal.value = true
}

async function confirmTagUpdate() {
  validationErrors.value = {}
  
  const tags = tagsInput.value.trim()
  
  loading.value = true
  try {
    // 同时更新自选和持仓的板块标签
    // 先更新持仓的板块标签
    try {
      await holdingApi.updateTags(props.fundData.fund_code, tags)
    } catch (error) {
      console.log('更新持仓标签失败（可能不在持仓列表中）:', error)
    }
    
    // 再更新自选的板块标签
    try {
      const { watchlistApi } = await import('../services/api')
      await watchlistApi.updateTags(props.fundData.fund_code, tags)
    } catch (error) {
      console.log('更新自选标签失败（可能不在自选列表中）:', error)
    }
    
    fundTags.value = tags
    showTagModal.value = false
    emit('confirm')
  } catch (error) {
    console.error('修改板块失败:', error)
    validationErrors.value.general = '修改板块失败，请重试'
  } finally {
    loading.value = false
  }
}

function showOperationArea(tab) {
  activeTab.value = tab
  showOperation.value = true
  
  // 当选择修改持仓时，填充当前持仓数据
  if (tab === 'edit' && props.holdingData) {
    editAmount.value = (props.holdingData.current_value || props.holdingData.cost).toString()
    editProfit.value = (props.holdingData.profit_loss || 0).toString()
    editPlatform.value = props.holdingData.platform || '其他'
  } else if (tab === 'buy') {
    buyAmount.value = ''
  } else if (tab === 'sell') {
    sellShares.value = ''
  } else if (tab === 'tags') {
    tagsInput.value = fundTags.value || ''
  }
}

function cancelAddHolding() {
  addCurrentValue.value = ''
  addProfit.value = ''
  showAddHoldingForm.value = false
}

function handleCancel() {
  if (showAddHoldingForm.value) {
    cancelAddHolding()
  } else if (showOperation.value) {
    showOperation.value = false
    // 重置相关表单数据
    buyAmount.value = ''
    sellShares.value = ''
    editAmount.value = ''
    editProfit.value = ''
    validationErrors.value = {}
  }
}

function handleConfirm() {
  if (showAddHoldingForm.value) {
    confirmAddHolding()
  } else if (showOperation.value) {
    confirm()
  }
}

async function confirmAddHolding() {
  // 重置验证错误
  validationErrors.value = {}
  
  const currentValue = parseFloat(addCurrentValue.value)
  const profit = parseFloat(addProfit.value)
  const tags = addTags.value.trim()
  const platform = addPlatform.value
  
  // 验证持仓金额
  if (addCurrentValue.value === '' || isNaN(currentValue) || currentValue <= 0) {
    validationErrors.value.addCurrentValue = '请输入有效的持仓金额（大于0）'
    return
  }
  
  // 验证持有收益
  if (addProfit.value === '' || isNaN(profit)) {
    validationErrors.value.addProfit = '请输入有效的持有收益'
    return
  }

  // 计算持仓成本：当前价值 - 持有收益
  const cost = currentValue - profit

  loading.value = true
  try {
    const response = await holdingApi.add({
        fund_code: props.fundData.fund_code,
        type: 'sync',
        current_value: currentValue,
        profit: profit,
        tags: tags,
        platform: platform
      })
    
    // 检查响应是否成功
    if (response && response.data) {
      if (response.data.error) {
        validationErrors.value.general = response.data.error
      } else {
        emit('confirm')
        emit('update:show', false)
      }
    } else {
      emit('confirm')
      emit('update:show', false)
    }
  } catch (error) {
    console.error('添加持仓失败:', error)
    // 显示错误提示，但不使用alert
    if (error.response && error.response.data && error.response.data.error) {
      validationErrors.value.general = error.response.data.error
    } else {
      validationErrors.value.general = '添加持仓失败，请重试'
    }
  } finally {
    loading.value = false
  }
}

async function confirm() {
  // 重置验证错误
  validationErrors.value = {}
  
  if (activeTab.value === 'buy') {
    const amount = parseFloat(buyAmount.value)
    if (buyAmount.value === '' || isNaN(amount) || amount <= 0) {
      validationErrors.value.buyAmount = '请输入有效的加仓金额（大于0）'
      return
    }

    loading.value = true
    try {
      await holdingApi.add({
        fund_code: props.fundData.fund_code,
        type: 'buy',
        cost: amount,
        buy_date: buyDate.value,
        platform: props.holdingData?.platform || props.platform || '其他'  // 传递平台参数
      })
      emit('confirm')
      emit('update:show', false)
    } catch (error) {
      console.error('加仓失败:', error)
      validationErrors.value.general = '加仓失败，请重试'
    } finally {
      loading.value = false
    }
  } else if (activeTab.value === 'sell') {
    const shares = parseFloat(sellShares.value)
    if (sellShares.value === '' || isNaN(shares) || shares <= 0) {
      validationErrors.value.sellShares = '请输入有效的减仓份额（大于0）'
      return
    }

    if (props.holdingData && shares > props.holdingData.shares) {
      validationErrors.value.sellShares = '减仓份额不能超过可用份额'
      return
    }

    loading.value = true
    try {
      await holdingApi.add({
        fund_code: props.fundData.fund_code,
        type: 'sell',
        shares: shares,
        sell_date: sellDate.value,
        platform: props.holdingData?.platform || props.platform || '其他'  // 传递平台参数
      })
      emit('confirm')
      emit('update:show', false)
    } catch (error) {
      console.error('减仓失败:', error)
      validationErrors.value.general = '减仓失败，请重试'
    } finally {
      loading.value = false
    }
  } else if (activeTab.value === 'edit') {
    const currentValue = parseFloat(editAmount.value)
    const profit = parseFloat(editProfit.value)
    const platform = editPlatform.value
    
    if (editAmount.value === '' || isNaN(currentValue) || currentValue <= 0) {
      validationErrors.value.editAmount = '请输入有效的持仓金额（大于0）'
    }
    
    if (editProfit.value === '' || isNaN(profit)) {
      validationErrors.value.editProfit = '请输入有效的持有收益'
    }
    
    // 如果有验证错误，返回
    if (Object.keys(validationErrors.value).length > 0) {
      return
    }

    // 计算持仓成本：当前价值 - 持有收益
    const cost = currentValue - profit

    loading.value = true
    try {
      await holdingApi.update(props.fundData.fund_code, {
        current_value: currentValue,
        profit: profit,
        platform: platform
      })
      emit('confirm')
      emit('update:show', false)
    } catch (error) {
      console.error('修改持仓失败:', error)
      validationErrors.value.general = '修改持仓失败，请重试'
    } finally {
      loading.value = false
    }
  } else if (activeTab.value === 'delete') {
    loading.value = true
    try {
      const platform = props.holdingData?.platform || props.platform || '其他'
      await holdingApi.delete(props.fundData.fund_code, platform)
      emit('confirm')
      emit('update:show', false)
    } catch (error) {
      console.error('删除持仓失败:', error)
      validationErrors.value.general = '删除持仓失败，请重试'
    } finally {
      loading.value = false
    }
  }
}

onBeforeUnmount(() => {
  if (chartInstance) {
    chartInstance.destroy()
  }
})
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
  max-width: 800px;
  width: 95%;
  max-height: 95vh;
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

.fund-info {
  margin-bottom: 20px;
  padding: 16px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border-radius: 12px;
  color: #fff;
}

.fund-name-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.fund-name {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 4px;
}

.fund-tags {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tag-item {
  font-size: 0.85rem;
  padding: 4px 12px;
  background: rgba(255, 255, 255, 0.2);
  border-radius: 12px;
  backdrop-filter: blur(4px);
}

.edit-tag-btn {
  background: rgba(255, 255, 255, 0.15);
  border: none;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 6px;
  color: #fff;
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}

.edit-tag-btn:hover {
  background: rgba(255, 255, 255, 0.25);
}

.fund-tags.no-tags {
  background: rgba(255, 255, 255, 0.1);
}

.fund-tags.no-tags .no-tag {
  color: rgba(255, 255, 255, 0.7);
}

.fund-tags.no-tags .edit-tag-btn {
  opacity: 0.8;
}

.fund-tags.no-tags .edit-tag-btn:hover {
  opacity: 1;
  background: rgba(255, 255, 255, 0.2);
}

.fund-code {
  font-size: 0.9rem;
  opacity: 0.9;
}

.holding-info {
  margin-bottom: 20px;
  padding: 16px;
  background: #f9fafb;
  border-radius: 12px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
}

.info-row:last-child {
  margin-bottom: 0;
}

.info-label {
  font-size: 0.875rem;
  color: #6b7280;
}

.info-value {
  font-size: 0.875rem;
  font-weight: 600;
  color: #1f2937;
}

.chart-section {
  margin-bottom: 24px;
  padding: 20px;
  background: #f8f9fa;
  border-radius: 12px;
}

.chart-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.chart-title {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
  color: #1f2937;
}

.time-range-selector {
  display: flex;
  gap: 6px;
}

.range-btn {
  padding: 6px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #fff;
  font-size: 0.8rem;
  font-weight: 500;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s ease;
}

.range-btn:hover {
  border-color: #4f46e5;
  color: #4f46e5;
}

.range-btn.active {
  border-color: #4f46e5;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.chart-wrapper {
  position: relative;
  height: 300px;
  width: 100%;
}

.chart-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 300px;
}

.tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
}

.tab-btn {
  flex: 1;
  padding: 10px;
  border: 2px solid #e5e7eb;
  border-radius: 10px;
  background: #fff;
  font-size: 0.9rem;
  font-weight: 500;
  color: #6b7280;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tab-btn:hover {
  border-color: #4f46e5;
  color: #4f46e5;
}

.tab-btn.active {
  border-color: #4f46e5;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
}

.form-section {
  margin-top: 20px;
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

.form-input.is-invalid {
  border-color: #dc3545;
  box-shadow: 0 0 0 3px rgba(220, 53, 69, 0.1);
}

.invalid-feedback {
  margin-top: 4px;
  font-size: 0.8rem;
  color: #dc3545;
}

.alert {
  padding: 12px;
  border-radius: 8px;
  font-size: 0.9rem;
  margin-bottom: 16px;
}

.alert-danger {
  background-color: #f8d7da;
  color: #721c24;
  border: 1px solid #f5c6cb;
}

.hint-text {
  margin-top: 8px;
  font-size: 0.8rem;
  color: #6b7280;
}

.add-holding-section {
  margin-top: 20px;
  padding: 20px;
  background: #f9fafb;
  border-radius: 12px;
  text-align: center;
}

.btn-block {
  width: 100%;
  padding: 12px 20px;
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

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-secondary {
  background-color: #f3f4f6;
  color: #6b7280;
}

.btn-secondary:hover:not(:disabled) {
  background-color: #e5e7eb;
  color: #1f2937;
}

.btn-primary {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff;
  box-shadow: 0 2px 8px rgba(102, 126, 234, 0.3);
}

.btn-primary:hover:not(:disabled) {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
}

.btn:active:not(:disabled) {
  transform: translateY(0);
}

.delete-btn {
  color: #dc3545;
  border-color: #dc3545;
  border-width: 1px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 40px;
}

.delete-btn:hover {
  border-color: #dc3545;
  color: #dc3545;
  background-color: #fff5f5;
}

.delete-btn.active {
  border-color: #dc3545;
  background: #dc3545;
  color: #fff;
}

.delete-btn i {
  font-size: 1.1rem;
}

.delete-confirm-section {
  margin-top: 20px;
}

.delete-warning {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  background-color: #fff5f5;
  border: 1px solid #feb2b2;
  border-radius: 8px;
  color: #c53030;
  font-size: 0.9rem;
  margin-bottom: 20px;
}

.delete-warning i {
  font-size: 1.2rem;
}

.tag-modal {
  max-width: 500px;
  width: 90%;
}

.tag-modal .form-section {
  margin-top: 0;
}

.tag-modal .form-group {
  margin-bottom: 20px;
}

.form-hint {
  font-size: 0.8rem;
  color: #6b7280;
  margin-top: 6px;
}

@media (max-width: 768px) {
  .modal-container {
    max-width: 95%;
    max-height: 90vh;
  }
  
  .chart-header {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .time-range-selector {
    width: 100%;
    justify-content: space-between;
  }
  
  .range-btn {
    flex: 1;
    text-align: center;
  }
  
  .chart-wrapper {
    height: 250px;
  }
  
  .chart-loading {
    height: 250px;
  }
}
</style>
