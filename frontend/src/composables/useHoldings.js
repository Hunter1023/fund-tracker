import { computed, onMounted, ref } from 'vue'
import { holdingApi, platformApi } from '../services/api'

export function useHoldings() {
  const holdings = ref([])
  const loading = ref(false)
  const isLoaded = ref(false)
  const sortField = ref('one_month_rate')
  const sortDirection = ref('desc')
  const transactionType = ref('sync')
  const selectedPlatform = ref('支付宝')
  const platforms = ref([])

  async function loadPlatforms() {
    try {
      const response = await platformApi.get()
      const platformNames = response.data.map(p => p.name)
      platforms.value = platformNames
    } catch (error) {
      console.error('加载平台列表失败:', error)
    }
  }

  function sortFunds(holdingsList, field, direction) {
    if (!Array.isArray(holdingsList)) {
      return []
    }
    if (!field) {
      return holdingsList
    }

    return [...holdingsList].sort((a, b) => {
      let aValue, bValue

      switch(field) {
        case 'tags':
          aValue = a.tags || '未分类'
          bValue = b.tags || '未分类'
          break
        case 'name':
          aValue = a.fund_name || ''
          bValue = b.fund_name || ''
          break
        case 'daily_change_rate':
          aValue = parseFloat(a.daily_change_rate) || 0
          bValue = parseFloat(b.daily_change_rate) || 0
          break
        case 'estimate_change_rate':
          aValue = parseFloat(a.estimate_change_rate) || 0
          bValue = parseFloat(b.estimate_change_rate) || 0
          break
        case 'estimate_profit':
          aValue = parseFloat(a.estimate_profit) || 0
          bValue = parseFloat(b.estimate_profit) || 0
          break
        case 'one_month_rate':
          aValue = parseFloat(a.one_month_rate) || 0
          bValue = parseFloat(b.one_month_rate) || 0
          break
        case 'profit':
          aValue = parseFloat(a.profit_loss) || 0
          bValue = parseFloat(b.profit_loss) || 0
          break
        case 'cost':
          aValue = parseFloat(a.cost) || 0
          bValue = parseFloat(b.cost) || 0
          break
        case 'current_value':
          aValue = parseFloat(a.current_value) || parseFloat(a.cost) || 0
          bValue = parseFloat(b.current_value) || parseFloat(b.cost) || 0
          break
        default:
          return 0
      }

      if (field === 'name' || field === 'tags') {
        const isEnglishA = /^[a-zA-Z0-9\s]+$/.test(aValue)
        const isEnglishB = /^[a-zA-Z0-9\s]+$/.test(bValue)

        if (isEnglishA && !isEnglishB) {
          return direction === 'asc' ? -1 : 1
        } else if (!isEnglishA && isEnglishB) {
          return direction === 'asc' ? 1 : -1
        } else {
          if (direction === 'asc') {
            return aValue.localeCompare(bValue)
          } else {
            return bValue.localeCompare(aValue)
          }
        }
      } else {
        if (direction === 'asc') {
          return aValue - bValue
        } else {
          return bValue - aValue
        }
      }
    })
  }

  const sortedHoldings = computed(() => {
    const filteredHoldings = holdings.value.filter(h => (h.platform || '其他') === selectedPlatform.value)
    return sortFunds(filteredHoldings, sortField.value, sortDirection.value)
  })

  const summary = computed(() => {
    let totalAmount = 0
    let totalValue = 0
    let totalProfit = 0
    let totalTodayProfit = 0

    const filteredHoldings = holdings.value.filter(h => (h.platform || '其他') === selectedPlatform.value)

    if (Array.isArray(filteredHoldings)) {
      filteredHoldings.forEach(holding => {
        const profitLoss = parseFloat(holding.profit_loss) || 0
        const estimateProfit = parseFloat(holding.estimate_profit) || 0

        totalAmount += holding.cost
        totalValue += holding.current_value || holding.cost
        totalProfit += profitLoss
        totalTodayProfit += estimateProfit
      })
    }

    const totalProfitRate = totalAmount > 0 ? (totalProfit / totalAmount) * 100 : 0

    return {
      totalAmount,
      totalValue,
      totalProfit,
      totalProfitRate,
      totalTodayProfit,
      fundCount: Array.isArray(filteredHoldings) ? filteredHoldings.length : 0
    }
  })

  async function loadHoldings() {
    loading.value = true
    isLoaded.value = false
    try {
      const response = await holdingApi.get()
      holdings.value = Array.isArray(response.data) ? [...response.data] : []
      isLoaded.value = true
    } catch (error) {
      console.error('加载持仓失败:', error)
      holdings.value = []
      isLoaded.value = true
    } finally {
      loading.value = false
    }
  }

  async function addHolding(data) {
    try {
      const response = await holdingApi.add(data)
      if (response.data.success) {
        await loadHoldings()
      }
      return response.data
    } catch (error) {
      console.error('添加持仓失败:', error)
      throw error
    }
  }

  async function updateHolding(fundCode, data) {
    try {
      const response = await holdingApi.update(fundCode, data)
      if (response.data.success) {
        await loadHoldings()
      }
      return response.data
    } catch (error) {
      console.error('更新持仓失败:', error)
      throw error
    }
  }

  async function deleteHolding(fundCode) {
    try {
      const response = await holdingApi.delete(fundCode)
      if (response.data.success) {
        await loadHoldings()
      }
      return response.data
    } catch (error) {
      console.error('删除持仓失败:', error)
      throw error
    }
  }

  function handleSort(field) {
    if (sortField.value === field) {
      sortDirection.value = sortDirection.value === 'asc' ? 'desc' : 'asc'
    } else {
      sortField.value = field
      sortDirection.value = 'desc'
    }
  }

  function getCurrentDate() {
    const today = new Date()
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  }

  function getChangeRateColor(rate) {
    const numRate = parseFloat(rate)
    if (isNaN(numRate)) return '#6c757d'
    return numRate > 0 ? '#dc3545' : '#28a745'
  }

  onMounted(() => {
    loadHoldings()
    loadPlatforms()
  })

  return {
    holdings,
    loading,
    isLoaded,
    sortField,
    sortDirection,
    transactionType,
    selectedPlatform,
    sortedHoldings,
    platforms,
    summary,
    loadHoldings,
    loadPlatforms,
    addHolding,
    updateHolding,
    deleteHolding,
    handleSort,
    getCurrentDate,
    getChangeRateColor
  }
}
