<template>
  <div class="holdings-container">
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
        <div
          class="summary-value"
          :class="
            summary.hasTradingDayData && summary.totalTodayProfit >= 0
              ? 'profit-positive'
              : summary.hasTradingDayData
                ? 'profit-negative'
                : ''
          "
        >
          {{
            summary.hasTradingDayData
              ? "¥" + formatAmount(summary.totalTodayProfit)
              : "-"
          }}
        </div>
      </div>
      <div class="summary-item">
        <div class="summary-label">持有收益</div>
        <div
          class="summary-value"
          :class="
            summary.totalProfit >= 0 ? 'profit-positive' : 'profit-negative'
          "
        >
          ¥{{ formatAmount(summary.totalProfit) }} ({{
            summary.totalProfitRate.toFixed(2)
          }}%)
        </div>
      </div>
      <div class="summary-item">
        <div class="summary-label">总金额</div>
        <div class="summary-value">¥{{ formatAmount(summary.totalValue) }}</div>
      </div>
      <div class="summary-item">
        <div class="summary-label">总成本</div>
        <div class="summary-value">
          ¥{{ formatAmount(summary.totalAmount) }}
        </div>
      </div>
      <div class="summary-item">
        <div class="summary-label">基金数量</div>
        <div class="summary-value">{{ summary.fundCount }}</div>
      </div>
    </div>

    <!-- 板块分布 - 可展开/收起 -->
    <div class="sector-distribution-section">
      <div
        class="sector-header"
        @click="showSectorDistribution = !showSectorDistribution"
      >
        <h3 class="sector-title">板块分布</h3>
        <i
          :class="
            showSectorDistribution ? 'bi bi-chevron-up' : 'bi bi-chevron-down'
          "
          class="toggle-icon"
        ></i>
      </div>
      <div
        v-if="showSectorDistribution && sortedHoldings.length > 0"
        class="chart-container"
      >
        <div class="pie-chart-wrapper">
          <div class="chart-area">
            <canvas ref="pieChart"></canvas>
          </div>
          <div ref="legendContainer" class="custom-legend"></div>
        </div>
      </div>
    </div>

    <div v-if="sortedHoldings.length === 0" class="empty-state">
      <div class="empty-icon">💼</div>
      <p>暂无持仓</p>
      <div class="action-bar empty-action-bar">
        <button class="sync-btn" @click="showSearchModal = true">
          <i class="bi bi-plus-circle me-2"></i>添加持仓
        </button>
      </div>
    </div>

    <div v-show="sortedHoldings.length > 0">
      <div class="table-container">
        <div class="frozen-table-wrapper">
          <div class="frozen-column">
            <table class="frozen-table">
              <thead>
                <tr>
                  <th
                    :class="[
                      'table-header',
                      { sortable: columns[0]?.sortable },
                    ]"
                    @click="columns[0]?.sortable && handleSort(columns[0]?.key)"
                  >
                    <div class="header-content">
                      <span>{{ columns[0]?.label }}</span>
                      <span v-if="columns[0]?.sortable" class="sort-icon">
                        <i
                          v-if="sortField === columns[0]?.key"
                          :class="
                            sortDirection === 'asc'
                              ? 'bi bi-caret-up-fill'
                              : 'bi bi-caret-down-fill'
                          "
                          class="sort-active"
                        ></i>
                        <i v-else class="bi bi-caret-up-down"></i>
                      </span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="holding in sortedHoldings"
                  :key="`${holding.fund_code}-${holding.platform || '默认'}`"
                  class="table-row"
                >
                  <td>
                    <div class="fund-name-cell">
                      <div
                        class="fund-name clickable"
                        @click="openFundDetail(holding)"
                      >
                        {{ holding.fund_name }}
                      </div>
                      <div class="fund-info-row">
                        <span
                          v-if="isUpdatedToday(holding)"
                          class="badge update-badge"
                          >已更新</span
                        >
                        <div class="fund-code">
                          {{ holding.fund_code }}
                        </div>
                      </div>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="scrollable-table-wrapper" ref="tableWrapper">
            <table class="custom-table">
              <thead>
                <tr>
                  <th
                    v-for="column in columns.slice(1)"
                    :key="column.key"
                    :class="['table-header', { sortable: column.sortable }]"
                    @click="column.sortable && handleSort(column.key)"
                  >
                    <div class="header-content">
                      <span>{{ column.label }}</span>
                      <span v-if="column.sortable" class="sort-icon">
                        <i
                          v-if="sortField === column.key"
                          :class="
                            sortDirection === 'asc'
                              ? 'bi bi-caret-up-fill'
                              : 'bi bi-caret-down-fill'
                          "
                          class="sort-active"
                        ></i>
                        <i v-else class="bi bi-caret-up-down"></i>
                      </span>
                    </div>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="holding in sortedHoldings"
                  :key="`${holding.fund_code}-${holding.platform || '默认'}`"
                  class="table-row"
                >
                  <td>
                    <div class="tags-container">
                      <div
                        v-for="tag in (holding.tags || '')
                          .split(',')
                          .filter((t) => t.trim())"
                        :key="tag"
                        class="tag-item"
                      >
                        <span
                          class="tag-badge"
                          :class="`tag-${getTagColorIndex(tag)}`"
                        >
                          {{ tag.trim() }}
                        </span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div
                      class="rate-cell"
                      :style="{
                        color: getChangeRateColor(holding.daily_change_rate),
                      }"
                    >
                      <div class="rate-value">
                        {{ holding.daily_change_rate }}%
                      </div>
                      <div v-if="!isUpdatedToday(holding)" class="rate-date">
                        {{ getMonthDay(holding.fsrq) }}
                      </div>
                    </div>
                  </td>
                  <td>
                    <div class="rate-cell">
                      <div
                        class="rate-value"
                        :style="{
                          color:
                            holding.estimate_change_rate !== null &&
                            holding.estimate_change_rate !== undefined &&
                            holding.estimate_change_rate !== '-'
                              ? getChangeRateColor(holding.estimate_change_rate)
                              : '#6c757d',
                        }"
                      >
                        {{
                          holding.estimate_change_rate !== null &&
                          holding.estimate_change_rate !== undefined &&
                          holding.estimate_change_rate !== "-"
                            ? holding.estimate_change_rate + "%"
                            : "-"
                        }}
                      </div>
                      <div
                        v-if="
                          holding.estimate_time &&
                          holding.estimate_change_rate !== '-'
                        "
                        class="rate-date"
                      >
                        {{ formatEstimateTime(holding.estimate_time) }}
                      </div>
                    </div>
                  </td>
                  <td>
                    <div
                      class="rate-value"
                      :style="{
                        color:
                          holding.estimate_profit !== null &&
                          holding.estimate_profit !== undefined
                            ? getChangeRateColor(holding.estimate_profit)
                            : '#6c757d',
                      }"
                    >
                      {{
                        holding.estimate_profit !== null &&
                        holding.estimate_profit !== undefined
                          ? "¥" + formatAmount(holding.estimate_profit || 0)
                          : "-"
                      }}
                    </div>
                  </td>
                  <td>
                    <div
                      class="rate-value"
                      :style="{
                        color: getChangeRateColor(holding.one_month_rate),
                      }"
                    >
                      {{ (holding.one_month_rate || 0).toFixed(2) }}%
                    </div>
                  </td>
                  <td>
                    <div
                      class="rate-cell"
                      :style="{
                        color: getChangeRateColor(calculateProfit(holding)),
                      }"
                    >
                      <div class="rate-value">
                        ¥{{ formatAmount(calculateProfit(holding)) }}
                      </div>
                      <div class="rate-value">
                        {{ calculateProfitRate(holding).toFixed(2) }}%
                      </div>
                    </div>
                  </td>
                  <td>
                    <div class="rate-value">
                      ¥{{ formatAmount(holding.current_value) }}
                    </div>
                  </td>
                  <td>
                    <div class="rate-value">
                      ¥{{ formatAmount(holding.cost) }}
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div class="action-bar">
          <button class="sync-btn" @click="showSearchModal = true">
            <i class="bi bi-plus-circle me-2"></i>添加持仓
          </button>
        </div>
      </div>
    </div>

    <FundDetailModal
      v-model:show="showDetailModal"
      :fund-data="currentFund"
      :holding-data="currentHolding"
      :platform="selectedPlatform"
      :add-holding="addHolding"
      @confirm="handleDetailConfirm"
    />

    <SearchFundModal
      v-model:show="showSearchModal"
      :platform="selectedPlatform"
      @select="handleSelectFund"
    />

    <PlatformManager
      v-model:show="showPlatformManager"
      @update="handlePlatformUpdate"
    />
  </div>
</template>

<script setup>
import Chart from "chart.js/auto";
import { nextTick, onMounted, ref, watch } from "vue";
import { useHoldings } from "../composables/useHoldings";
import FundDetailModal from "./FundDetailModal.vue";
import PlatformManager from "./PlatformManager.vue";
import SearchFundModal from "./SearchFundModal.vue";

const {
  holdings,
  isLoaded,
  sortField,
  sortDirection,
  sortedHoldings,
  platforms,
  selectedPlatform,
  summary,
  loadHoldings,
  loadPlatforms,
  addHolding,
  updateHoldingLocally,
  handleSort,
  getCurrentDate,
  getChangeRateColor,
} = useHoldings();

const pieChart = ref(null);
const legendContainer = ref(null);
const tableWrapper = ref(null);
let chartInstance = null;

const showDetailModal = ref(false);
const currentFund = ref(null);
const currentHolding = ref(null);
const showSearchModal = ref(false);
const showPlatformManager = ref(false);
const showSectorDistribution = ref(false);

function openFundDetail(holding) {
  if (!holding) return;

  currentFund.value = {
    fund_code: holding.fund_code,
    fund_name: holding.fund_name,
    tags: holding.tags || "",
  };
  currentHolding.value = {
    current_value: holding.current_value || holding.cost,
    cost: holding.cost,
    shares: holding.shares,
    avg_cost: holding.avg_cost,
    profit_loss: holding.profit_loss || 0,
    platform: holding.platform,
  };
  showDetailModal.value = true;
}

function handleDetailConfirm(updatedHolding) {
  if (updatedHolding) {
    updateHoldingLocally(updatedHolding);
  }
  // 不再重新加载持仓列表，因为addHolding函数已经在本地更新了数据
}

function handleSelectFund(fund) {
  currentFund.value = {
    fund_code: fund.fund_code,
    fund_name: fund.fund_name,
  };
  currentHolding.value = null;
  showDetailModal.value = true;
}

function openAddHolding() {
  showSearchModal.value = true;
}

async function handlePlatformUpdate() {
  await loadPlatforms();
  await loadHoldings();
}

function syncRowHeights() {
  requestAnimationFrame(() => {
    const frozenTable = document.querySelector(".frozen-table");
    const scrollableTable = document.querySelector(".custom-table");

    if (!frozenTable || !scrollableTable) return;

    const frozenTheadRows = frozenTable.querySelectorAll("thead tr");
    const scrollableTheadRows = scrollableTable.querySelectorAll("thead tr");
    const frozenTbodyRows = frozenTable.querySelectorAll("tbody tr");
    const scrollableTbodyRows = scrollableTable.querySelectorAll("tbody tr");

    frozenTheadRows.forEach((frozenRow) => {
      frozenRow.style.height = "";
    });
    scrollableTheadRows.forEach((scrollableRow) => {
      scrollableRow.style.height = "";
    });
    frozenTbodyRows.forEach((frozenRow) => {
      frozenRow.style.height = "";
    });
    scrollableTbodyRows.forEach((scrollableRow) => {
      scrollableRow.style.height = "";
    });

    requestAnimationFrame(() => {
      frozenTheadRows.forEach((frozenRow, index) => {
        const scrollableRow = scrollableTheadRows[index];
        if (scrollableRow) {
          const scrollableHeight = scrollableRow.offsetHeight;
          const frozenHeight = frozenRow.offsetHeight;
          const maxHeight = Math.max(scrollableHeight, frozenHeight);
          frozenRow.style.height = maxHeight + "px";
          scrollableRow.style.height = maxHeight + "px";
        }
      });

      frozenTbodyRows.forEach((frozenRow, index) => {
        const scrollableRow = scrollableTbodyRows[index];
        if (scrollableRow) {
          const scrollableHeight = scrollableRow.offsetHeight;
          const frozenHeight = frozenRow.offsetHeight;
          const maxHeight = Math.max(scrollableHeight, frozenHeight);
          frozenRow.style.height = maxHeight + "px";
          scrollableRow.style.height = maxHeight + "px";
        }
      });
    });
  });
}

// 组件挂载时自动加载数据
// 加载平台数据和持仓数据，确保页面刷新时能正常显示
onMounted(async () => {
  await nextTick();
  // 加载平台数据，确保平台列表能正常显示
  await loadPlatforms();
  // 加载持仓数据，确保页面刷新时能正常显示
  await loadHoldings();
  await nextTick();
  syncRowHeights();
  updatePieChart();
});

// 监听持仓数据变化，同步行高并更新饼图
watch(
  sortedHoldings,
  async () => {
    await nextTick();
    syncRowHeights();
    updatePieChart();
  },
  { deep: true },
);

// 监听平台切换，重新同步行高
watch(
  selectedPlatform,
  async () => {
    await nextTick();
    syncRowHeights();
  },
);

// 监听展开状态变化，当展开时更新饼图
watch(showSectorDistribution, async (newValue) => {
  if (newValue) {
    await nextTick();
    updatePieChart();
  }
});

// 按板块汇总持仓
function getSectorSummary() {
  const sectorMap = new Map();
  const totalAmount = sortedHoldings.value.reduce(
    (sum, holding) => sum + holding.cost,
    0,
  );

  sortedHoldings.value.forEach((holding) => {
    const sector = holding.tags || "未分类";
    const currentAmount = sectorMap.get(sector) || 0;
    sectorMap.set(sector, currentAmount + holding.cost);
  });

  const sectors = [];
  sectorMap.forEach((amount, sector) => {
    sectors.push({
      sector,
      amount,
      percentage: totalAmount > 0 ? (amount / totalAmount) * 100 : 0,
    });
  });

  return sectors.sort((a, b) => b.amount - a.amount);
}

// 更新饼图
function updatePieChart() {
  if (!pieChart.value || !showSectorDistribution.value) return;

  const sectors = getSectorSummary();
  const labels = sectors.map((s) => s.sector);
  const data = sectors.map((s) => s.amount);

  // 生成按成本占比渐变的彩虹颜色（清新明亮，相邻颜色有明显跨度）
  function generateGradientColors(sectors) {
    const colors = [];

    sectors.forEach((sector, index) => {
      // 计算色相：均匀分布在彩虹色谱上（0-360度）
      const hue = (index / sectors.length) * 360;

      // 饱和度：使用中等饱和度（50-60%），颜色更鲜艳
      const saturation = 55;

      // 亮度：根据占比调整，占比越大亮度越低（颜色越深）
      const maxPercentage = sectors[0].percentage;
      const minPercentage = sectors[sectors.length - 1].percentage;

      let lightness;
      if (maxPercentage === minPercentage) {
        lightness = 65;
      } else {
        // 占比越大亮度越低（40-75%之间）
        const ratio = sector.percentage / maxPercentage;
        lightness = 75 - ratio * 35;
      }

      colors.push(`hsl(${hue}, ${saturation}%, ${lightness}%)`);
    });

    return colors;
  }

  // 销毁旧图表
  if (chartInstance) {
    chartInstance.destroy();
  }

  // 创建新图表
  const backgroundColors = generateGradientColors(sectors);
  chartInstance = new Chart(pieChart.value, {
    type: "doughnut",
    data: {
      labels: labels,
      datasets: [
        {
          data: data,
          backgroundColor: backgroundColors,
          borderColor: "#fff",
          borderWidth: 3,
          hoverOffset: 15,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: "50%",
      plugins: {
        legend: {
          display: false,
        },
        tooltip: {
          backgroundColor: "rgba(0, 0, 0, 0.8)",
          padding: 12,
          cornerRadius: 8,
          callbacks: {
            label: function (context) {
              const label = context.label || "";
              const value = context.raw || 0;
              const percentage =
                sectors[context.dataIndex].percentage.toFixed(2);
              return `${label}: ¥${value.toFixed(2)} (${percentage}%)`;
            },
          },
        },
      },
      animation: {
        animateRotate: true,
        animateScale: true,
      },
    },
  });

  // 生成自定义图例
  generateCustomLegend(sectors, backgroundColors);
}

// 生成自定义图例
function generateCustomLegend(sectors, backgroundColors) {
  if (!legendContainer.value) return;

  // 清空容器
  legendContainer.value.innerHTML = "";

  // 每列6个图示
  const itemsPerColumn = 6;
  const columns = Math.ceil(sectors.length / itemsPerColumn);

  // 创建容器
  const legendWrapper = document.createElement("div");
  legendWrapper.style.display = "flex";
  legendWrapper.style.flexDirection = "row";
  legendWrapper.style.gap = "20px";
  legendWrapper.style.alignItems = "flex-start";
  legendWrapper.style.width = "100%";
  legendWrapper.style.flexWrap = "wrap";

  // 生成列
  for (let i = 0; i < columns; i++) {
    const column = document.createElement("div");
    column.style.display = "flex";
    column.style.flexDirection = "column";
    column.style.gap = "12px";

    // 生成当前列的图例项
    const startIndex = i * itemsPerColumn;
    const endIndex = Math.min(startIndex + itemsPerColumn, sectors.length);

    for (let j = startIndex; j < endIndex; j++) {
      const sector = sectors[j];
      const item = document.createElement("div");
      item.style.display = "flex";
      item.style.alignItems = "center";
      item.style.gap = "10px";
      item.style.fontSize = "12px";
      item.style.whiteSpace = "nowrap";

      // 颜色块
      const colorBox = document.createElement("div");
      colorBox.style.width = "16px";
      colorBox.style.height = "16px";
      colorBox.style.borderRadius = "6px";
      colorBox.style.backgroundColor = backgroundColors[j];

      // 文本
      const text = document.createElement("span");
      const percentage = sector.percentage.toFixed(1);
      text.textContent = `${sector.sector} (${percentage}%)`;

      item.appendChild(colorBox);
      item.appendChild(text);
      column.appendChild(item);
    }

    legendWrapper.appendChild(column);
  }

  legendContainer.value.appendChild(legendWrapper);
}

const columns = [
  { key: "name", label: "名称", sortable: true },
  { key: "tags", label: "板块", sortable: true },
  { key: "daily_change_rate", label: "最新涨幅", sortable: true },
  { key: "estimate_change_rate", label: "估算涨幅", sortable: true },
  { key: "estimate_profit", label: "今日收益", sortable: true },
  { key: "one_month_rate", label: "近1月", sortable: true },
  { key: "profit", label: "持有收益", sortable: true },
  { key: "current_value", label: "持仓金额", sortable: true },
  { key: "cost", label: "持仓成本", sortable: true },
];

function isUpdatedToday(holding) {
  const fsrq = holding.fsrq || "";
  if (!fsrq) return false;
  return fsrq === getCurrentDate();
}

function getMonthDay(dateStr) {
  if (!dateStr) return "";
  const dateParts = dateStr.split("-");
  if (dateParts.length >= 3) {
    return `${dateParts[1]}-${dateParts[2]}`;
  }
  return "";
}

function formatEstimateTime(timeStr) {
  if (!timeStr) return "";
  // 如果时间格式是 "YYYY-MM-DD HH:mm:ss"，去掉年份
  if (timeStr.includes("-") && timeStr.includes(":")) {
    const parts = timeStr.split(" ");
    if (parts.length >= 2) {
      const dateParts = parts[0].split("-");
      if (dateParts.length >= 3) {
        return `${dateParts[1]}-${dateParts[2]} ${parts[1]}`;
      }
    }
  }
  // 如果是其他格式，直接返回
  return timeStr;
}

function calculateProfit(holding) {
  return parseFloat(holding.profit_loss) || 0;
}

function calculateProfitRate(holding) {
  return parseFloat(holding.profit_loss_rate) || 0;
}

function getTagColorIndex(tag) {
  const colors = ["blue", "green", "orange", "purple", "teal", "pink"];
  let hash = 0;
  for (let i = 0; i < tag.length; i++) {
    hash = tag.charCodeAt(i) + ((hash << 5) - hash);
  }
  return colors[Math.abs(hash) % colors.length];
}

function formatAmount(amount) {
  return parseFloat(amount).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

defineExpose({
  loadHoldings,
  loadPlatforms,
  holdings,
  isLoaded,
});
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

.frozen-table-wrapper {
  display: flex;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  overflow: hidden;
}

.frozen-column {
  position: sticky;
  left: 0;
  z-index: 10;
  background: #fff;
  flex-shrink: 0;
}

.frozen-table {
  width: 160px;
  min-width: 160px;
  border-collapse: separate;
  border-spacing: 0;
  table-layout: fixed;
}

.frozen-table .table-row td {
  padding: 16px;
  border-bottom: 1px solid #e5e7eb;
  font-size: 0.875rem;
  text-align: left;
  box-sizing: border-box;
  height: 100%;
}

.frozen-table .table-row:last-child td {
  border-bottom: none;
  border-bottom-left-radius: 12px;
}

.scrollable-table-wrapper {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  flex: 1;
}

.custom-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  background: #fff;
  min-width: 740px;
}

@media (max-width: 768px) {
  .frozen-column {
    width: 120px;
  }

  .frozen-table {
    width: 120px;
    min-width: 120px;
  }
}

.custom-table th:nth-child(1),
.custom-table td:nth-child(1) {
  width: 120px;
  max-width: 120px;
  min-width: 100px;
}

.custom-table th:nth-child(2),
.custom-table td:nth-child(2) {
  width: 100px;
  max-width: 100px;
  min-width: 80px;
}

.custom-table th:nth-child(3),
.custom-table td:nth-child(3) {
  width: 100px;
  max-width: 100px;
  min-width: 80px;
}

.custom-table th:nth-child(4),
.custom-table td:nth-child(4) {
  width: 100px;
  max-width: 100px;
  min-width: 80px;
}

.custom-table th:nth-child(5),
.custom-table td:nth-child(5) {
  width: 80px;
  max-width: 80px;
  min-width: 60px;
}

.custom-table th:nth-child(6),
.custom-table td:nth-child(6) {
  width: 100px;
  max-width: 100px;
  min-width: 80px;
}

.custom-table th:nth-child(7),
.custom-table td:nth-child(7) {
  width: 100px;
  max-width: 100px;
  min-width: 80px;
}

.custom-table th:nth-child(8),
.custom-table td:nth-child(8) {
  width: 100px;
  max-width: 100px;
  min-width: 80px;
}

.table-header {
  background: #495057;
  color: #fff;
  padding: 14px 16px;
  font-weight: 600;
  font-size: 0.875rem;
  text-align: center;
  border: none;
  position: relative;
  white-space: nowrap;
}

.table-header:first-child {
  border-top-left-radius: 12px;
  border-top-right-radius: 0;
}

.frozen-table .table-header:first-child {
  border-top-right-radius: 0;
}

.custom-table .table-header:first-child {
  border-top-left-radius: 0;
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

.table-header:not(:last-child) {
  border-right: 1px solid #495057;
}

.table-header.sortable:hover:not(:last-child) {
  border-right-color: #343a40;
}

.header-content {
  display: flex;
  align-items: center;
  justify-content: center;
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
  white-space: nowrap;
  text-align: center;
  box-sizing: border-box;
  height: 100%;
}

.table-row td:nth-child(1) {
  text-align: left;
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
  white-space: normal;
  word-break: break-word;
}

.fund-name {
  font-weight: 600;
  color: #1f2937;
  font-size: 0.875rem;
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
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

.tags-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}

.tag-item {
  margin-bottom: 0;
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
  white-space: nowrap;
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
  max-width: 100%;
  margin: 0 auto;
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: 20px;
}

.chart-area {
  flex: 1;
  min-height: 250px;
}

.custom-legend {
  flex: 0 0 400px;
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
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    padding: 12px;
    justify-content: center;
  }

  .summary-item:nth-child(1),
  .summary-item:nth-child(2) {
    flex: 0 0 calc(50% - 3px);
  }

  .summary-item:nth-child(3),
  .summary-item:nth-child(4),
  .summary-item:nth-child(5) {
    flex: 0 0 calc(33.333% - 4px);
  }

  .summary-item {
    text-align: center;
  }

  .summary-label {
    font-size: 0.7rem;
    margin-bottom: 2px;
  }

  .summary-value {
    font-size: 0.9rem;
    font-weight: 600;
  }

  .custom-table th:nth-child(1),
  .custom-table td:nth-child(1) {
    width: 120px;
    max-width: 120px;
    min-width: 100px;
  }

  .custom-table th:nth-child(2),
  .custom-table td:nth-child(2) {
    width: 100px;
    max-width: 100px;
    min-width: 80px;
  }

  .fund-name {
    font-size: 0.8rem;
    line-height: 1.3;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .fund-code {
    font-size: 0.7rem;
  }

  .badge {
    font-size: 0.6rem;
    padding: 2px 6px;
  }

  .table-row td {
    padding: 12px 8px;
    font-size: 0.8rem;
  }

  .table-header {
    padding: 12px 8px;
    font-size: 0.8rem;
  }

  .platform-tab {
    font-size: 0.9rem;
  }

  .sector-title {
    font-size: 0.9rem;
  }

  .action-bar {
    padding: 0;
  }

  .table-container {
    margin-bottom: 16px;
  }

  .pie-chart-wrapper {
    flex-direction: column;
    gap: 16px;
  }

  .chart-area {
    min-height: 150px;
    max-height: 180px;
  }

  .custom-legend {
    flex: 0 0 auto;
    width: 100%;
  }

  .chart-container {
    padding: 16px;
  }
}
</style>
