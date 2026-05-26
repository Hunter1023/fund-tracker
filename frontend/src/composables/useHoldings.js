import { computed, ref } from "vue";
import { fundApi, holdingApi, platformApi } from "../services/api";

const CACHE_KEY = "fund_holdings_cache";
const CACHE_EXPIRY = 60 * 1000; // 1分钟过期

function getCachedHoldings() {
  try {
    const cached = localStorage.getItem(CACHE_KEY);
    if (cached) {
      const data = JSON.parse(cached);
      // 检查缓存是否过期
      if (Date.now() - data.timestamp < CACHE_EXPIRY) {
        return data.holdings;
      }
    }
  } catch (error) {
    console.error("读取缓存失败:", error);
  }
  return null;
}

function setCachedHoldings(holdingsData) {
  try {
    localStorage.setItem(
      CACHE_KEY,
      JSON.stringify({
        holdings: holdingsData,
        timestamp: Date.now(),
      }),
    );
  } catch (error) {
    console.error("写入缓存失败:", error);
  }
}

export function useHoldings() {
  const holdings = ref([]);
  const isLoaded = ref(false);
  let isLoading = false;
  const isRefreshing = ref(false);
  const savedSortField = localStorage.getItem("holdings_sort_field");
  const savedSortDirection = localStorage.getItem("holdings_sort_direction");
  const sortField = ref(savedSortField || "current_value");
  const sortDirection = ref(savedSortDirection || "desc");
  const transactionType = ref("sync");
  const selectedPlatform = ref("默认");
  const platforms = ref([]);

  async function loadPlatforms() {
    try {
      const response = await platformApi.get();
      const platformNames = response.data.map((p) => p.name);
      // 确保"默认"平台被添加到平台列表中
      if (!platformNames.includes("默认")) {
        platformNames.unshift("默认");
      }
      platforms.value = platformNames;
      // 平台列表加载后自动选择第一个平台
      if (platformNames.length > 0) {
        selectedPlatform.value = platformNames[0];
      } else {
        // 如果没有平台，使用默认平台
        selectedPlatform.value = "默认";
      }
    } catch (error) {
      console.error("加载平台列表失败:", error);
      // 加载失败时使用默认平台
      platforms.value = ["默认"];
      selectedPlatform.value = "默认";
    }
  }

  function sortFunds(holdingsList, field, direction) {
    if (!Array.isArray(holdingsList)) {
      return [];
    }
    if (!field) {
      return holdingsList;
    }

    return [...holdingsList].sort((a, b) => {
      let aValue, bValue;

      switch (field) {
        case "tags":
          aValue = a.tags || "未分类";
          bValue = b.tags || "未分类";
          break;
        case "name":
          aValue = a.fund_name || "";
          bValue = b.fund_name || "";
          break;
        case "daily_change_rate":
          aValue = parseFloat(a.daily_change_rate) || 0;
          bValue = parseFloat(b.daily_change_rate) || 0;
          break;
        case "estimate_change_rate":
          aValue = parseFloat(a.estimate_change_rate) || 0;
          bValue = parseFloat(b.estimate_change_rate) || 0;
          break;
        case "estimate_profit":
          aValue = parseFloat(a.estimate_profit) || 0;
          bValue = parseFloat(b.estimate_profit) || 0;
          break;
        case "one_month_rate":
          aValue = parseFloat(a.one_month_rate) || 0;
          bValue = parseFloat(b.one_month_rate) || 0;
          break;
        case "profit":
          aValue = parseFloat(a.profit_loss) || 0;
          bValue = parseFloat(b.profit_loss) || 0;
          break;
        case "cost":
          aValue = parseFloat(a.cost) || 0;
          bValue = parseFloat(b.cost) || 0;
          break;
        case "current_value":
          aValue = parseFloat(a.current_value) || parseFloat(a.cost) || 0;
          bValue = parseFloat(b.current_value) || parseFloat(b.cost) || 0;
          break;
        default:
          return 0;
      }

      if (field === "name" || field === "tags") {
        const isEnglishA = /^[a-zA-Z0-9\s]+$/.test(aValue);
        const isEnglishB = /^[a-zA-Z0-9\s]+$/.test(bValue);

        if (isEnglishA && !isEnglishB) {
          return direction === "asc" ? -1 : 1;
        } else if (!isEnglishA && isEnglishB) {
          return direction === "asc" ? 1 : -1;
        } else {
          if (direction === "asc") {
            return aValue.localeCompare(bValue);
          } else {
            return bValue.localeCompare(aValue);
          }
        }
      } else {
        if (direction === "asc") {
          return aValue - bValue;
        } else {
          return bValue - aValue;
        }
      }
    });
  }

  const sortedHoldings = computed(() => {
    const filteredHoldings = holdings.value.filter((h) => {
      const holdingPlatform = h.platform || "默认";
      // 严格匹配平台名称
      return holdingPlatform === selectedPlatform.value;
    });
    return sortFunds(filteredHoldings, sortField.value, sortDirection.value);
  });

  const summary = computed(() => {
    let totalAmount = 0;
    let totalValue = 0;
    let totalProfit = 0;
    let totalTodayProfit = 0;
    let hasTradingDayData = false;

    const filteredHoldings = holdings.value.filter((h) => {
      const holdingPlatform = h.platform || "默认";
      // 严格匹配平台名称
      return holdingPlatform === selectedPlatform.value;
    });

    if (Array.isArray(filteredHoldings)) {
      filteredHoldings.forEach((holding) => {
        const profitLoss = parseFloat(holding.profit_loss) || 0;
        const estimateProfit = holding.estimate_profit;

        totalAmount += holding.cost;
        totalValue += holding.current_value || holding.cost;
        totalProfit += profitLoss;

        if (estimateProfit !== null && estimateProfit !== undefined) {
          hasTradingDayData = true;
          totalTodayProfit += parseFloat(estimateProfit) || 0;
        }
      });
    }

    const totalProfitRate =
      totalAmount > 0 ? (totalProfit / totalAmount) * 100 : 0;

    return {
      totalAmount,
      totalValue,
      totalProfit,
      totalProfitRate,
      totalTodayProfit,
      hasTradingDayData,
      fundCount: Array.isArray(filteredHoldings) ? filteredHoldings.length : 0,
    };
  });

  async function loadHoldings(forceRefresh = false) {
    if (!forceRefresh && isLoading) return;
    isLoading = true;

    try {
      // 非强制刷新时，先尝试读取缓存数据
      if (!forceRefresh) {
        const cachedHoldings = getCachedHoldings();
        if (cachedHoldings && cachedHoldings.length > 0) {
          holdings.value = [...cachedHoldings];
          isLoaded.value = true;
        }
      }

      // 标记正在刷新
      isRefreshing.value = true;

      // 发起请求获取最新数据（带重试机制）
      let newHoldings = [];
      let retryCount = 0;
      const maxRetries = 3;

      while (retryCount < maxRetries && newHoldings.length === 0) {
        if (retryCount > 0) {
          // 重试前等待500ms
          console.log(`[持仓] 第${retryCount}次重试，等待500ms...`);
          await new Promise(resolve => setTimeout(resolve, 500));
        }

        try {
          const response = await holdingApi.get();
          newHoldings = Array.isArray(response.data) ? [...response.data] : [];
          console.log(`[持仓] 请求${retryCount + 1}次，返回${newHoldings.length}条数据`);
          
          // 如果返回空数组且还有重试机会，继续重试
          if (newHoldings.length === 0 && retryCount < maxRetries - 1) {
            console.log(`[持仓] 第${retryCount + 1}次请求返回空数据，准备重试...`);
          }
        } catch (err) {
          console.error(`持仓请求失败 (尝试 ${retryCount + 1}/${maxRetries}):`, err);
          // 网络异常时也继续重试（除非是最后一次）
          if (retryCount >= maxRetries - 1) {
            break;
          }
        }
        retryCount++;
      }

      // 只在API返回有效数据时更新，避免偶发空响应导致页面空白
      if (newHoldings.length > 0) {
        setCachedHoldings(newHoldings);
        holdings.value = newHoldings;
        isLoaded.value = true;
      } else if (!isLoaded.value) {
        // 首次加载且API返回空，才设置为空数组
        holdings.value = [];
        isLoaded.value = true;
      }
    } catch (error) {
      console.error("加载持仓失败:", error);
      // 如果没有缓存数据，才设置为空数组
      if (!isLoaded.value) {
        holdings.value = [];
      }
    } finally {
      isLoading = false;
      isRefreshing.value = false;
    }
  }

  async function addHolding(data) {
    const platform = data.platform || selectedPlatform.value || "默认";

    if (data.type === "sync") {
      const newHolding = {
        fund_code: data.fund_code,
        fund_name: data.fund_name,
        cost: data.current_value - data.profit || 0,
        shares: 0,
        avg_cost: 0,
        current_value: data.current_value || 0,
        profit_loss: data.profit || 0,
        profit_loss_rate:
          ((data.profit || 0) / (data.current_value - data.profit || 1)) *
            100 || 0,
        estimate_change_rate: "0.00",
        estimate_profit: 0,
        daily_change_rate: "-",
        fsrq: "",
        one_month_rate: 0,
        tags: data.tags || "",
        platform: platform,
      };
      updateHoldingLocally(newHolding);
    } else if (data.type === "buy" || data.type === "sell") {
      let existingHolding = holdings.value.find(
        (h) =>
          h.fund_code === data.fund_code && (h.platform || "默认") === platform,
      );

      if (!existingHolding) {
        existingHolding = holdings.value.find(
          (h) => h.fund_code === data.fund_code,
        );
      }

      if (existingHolding) {
        if (data.type === "buy") {
          const newCurrentValue =
            existingHolding.current_value + (data.cost || 0);
          const estimateChangeRate =
            parseFloat(existingHolding.estimate_change_rate) || 0;
          const newEstimateProfit =
            (estimateChangeRate * newCurrentValue) / 100;

          const updatedHolding = {
            ...existingHolding,
            cost: existingHolding.cost + (data.cost || 0),
            shares:
              existingHolding.shares +
              ((data.cost || 0) / existingHolding.avg_cost || 0),
            avg_cost:
              (existingHolding.cost + (data.cost || 0)) /
                (existingHolding.shares +
                  ((data.cost || 0) / existingHolding.avg_cost || 0)) || 0,
            current_value: newCurrentValue,
            profit_loss: existingHolding.profit_loss,
            estimate_profit: newEstimateProfit,
          };
          updateHoldingLocally(updatedHolding);
        } else if (data.type === "sell") {
          const sellRatio = (data.shares || 0) / existingHolding.shares;
          const updatedHolding = {
            ...existingHolding,
            cost: existingHolding.cost * (1 - sellRatio),
            shares: existingHolding.shares - (data.shares || 0),
            current_value: existingHolding.current_value * (1 - sellRatio),
            profit_loss: existingHolding.profit_loss * (1 - sellRatio),
          };

          if (updatedHolding.shares <= 0.01) {
            const index = holdings.value.findIndex(
              (h) =>
                h.fund_code === data.fund_code &&
                (h.platform || "默认") === (existingHolding.platform || "默认"),
            );
            if (index !== -1) {
              holdings.value.splice(index, 1);
            }
          } else {
            updateHoldingLocally(updatedHolding);
          }
        }
      } else {
        if (data.type === "buy") {
          const newHolding = {
            fund_code: data.fund_code,
            fund_name: data.fund_name,
            cost: data.cost || 0,
            shares: data.cost || 0,
            avg_cost: 1,
            current_value: data.cost || 0,
            profit_loss: 0,
            profit_loss_rate: 0,
            estimate_change_rate: "0.00",
            estimate_profit: 0,
            daily_change_rate: "-",
            fsrq: "",
            one_month_rate: 0,
            tags: "",
            platform: platform,
          };
          updateHoldingLocally(newHolding);
        }
      }
    }

    let actualPlatform = platform;
    if (data.type === "buy" || data.type === "sell") {
      let existingHolding = holdings.value.find(
        (h) =>
          h.fund_code === data.fund_code && (h.platform || "默认") === platform,
      );
      if (!existingHolding) {
        existingHolding = holdings.value.find(
          (h) => h.fund_code === data.fund_code,
        );
      }
      if (existingHolding) {
        actualPlatform = existingHolding.platform || "默认";
      }
    }

    const requestData = {
      ...data,
      platform: actualPlatform,
    };

    syncHoldingToBackend(requestData, data.fund_code, actualPlatform);

    return { success: true };
  }

  async function syncHoldingToBackend(requestData, fundCode, actualPlatform) {
    try {
      const response = await holdingApi.add(requestData);
      if (!response.data.success) {
        await loadHoldings();
      } else {
        try {
          const fundResponse = await fundApi.get(fundCode);
          const fundData = fundResponse.data;
          if (fundData) {
            let currentHolding = holdings.value.find(
              (h) =>
                h.fund_code === fundCode &&
                (h.platform || "默认") === actualPlatform,
            );
            if (!currentHolding) {
              currentHolding = holdings.value.find(
                (h) => h.fund_code === fundCode,
              );
            }
            if (currentHolding) {
              const fsrq = fundData.fsrq || "";
              const today = getCurrentDate();
              const isToday = fsrq === today;

              const dailyChangeRate = fundData.daily_change_rate;
              const estimateChangeRate = fundData.estimate_change_rate;

              let estimateProfit;

              if (
                estimateChangeRate != null &&
                estimateChangeRate !== "-" &&
                estimateChangeRate !== undefined
              ) {
                const changeRate = parseFloat(estimateChangeRate) || 0;
                estimateProfit =
                  (changeRate * currentHolding.current_value) / 100;
              } else if (
                isToday &&
                dailyChangeRate != null &&
                dailyChangeRate !== "-" &&
                dailyChangeRate !== 0
              ) {
                const changeRate = parseFloat(dailyChangeRate) || 0;
                estimateProfit =
                  currentHolding.current_value * (changeRate / 100);
              } else {
                estimateProfit = null;
              }

              const updatedHolding = {
                ...currentHolding,
                daily_change_rate: fundData.daily_change_rate || "-",
                estimate_change_rate: fundData.estimate_change_rate || "0.00",
                estimate_profit: estimateProfit,
                fsrq: fundData.fsrq || "",
                one_month_rate: fundData.one_month_rate || 0,
                fund_name: fundData.fund_name || requestData.fund_name,
              };
              updateHoldingLocally(updatedHolding);
            }
          }
        } catch (error) {
          console.error("获取基金数据失败:", error);
        }
      }
    } catch (error) {
      console.error("添加持仓失败:", error);
      await loadHoldings();
    }
  }

  function updateHoldingLocally(updatedHolding) {
    if (!updatedHolding) return;

    let index = holdings.value.findIndex(
      (h) =>
        h.fund_code === updatedHolding.fund_code &&
        (h.platform || "默认") === (updatedHolding.platform || "默认"),
    );

    // 如果找不到对应平台的持仓，尝试查找该基金的任意一个持仓
    if (index === -1) {
      index = holdings.value.findIndex(
        (h) => h.fund_code === updatedHolding.fund_code,
      );
    }

    if (index !== -1) {
      // 使用 splice 方法更新数组元素，保持数组引用的稳定性
      holdings.value.splice(index, 1, { ...updatedHolding });
    } else {
      // 使用 push 方法添加新元素，保持数组引用的稳定性
      holdings.value.push({ ...updatedHolding });
    }
  }

  async function updateHolding(fundCode, data) {
    try {
      const response = await holdingApi.update(fundCode, data);
      if (response.data.success) {
        await loadHoldings();
      }
      return response.data;
    } catch (error) {
      console.error("更新持仓失败:", error);
      throw error;
    }
  }

  async function deleteHolding(fundCode) {
    try {
      const response = await holdingApi.delete(fundCode);
      if (response.data.success) {
        await loadHoldings();
      }
      return response.data;
    } catch (error) {
      console.error("删除持仓失败:", error);
      throw error;
    }
  }

  function handleSort(field) {
    if (sortField.value === field) {
      sortDirection.value = sortDirection.value === "asc" ? "desc" : "asc";
    } else {
      sortField.value = field;
      sortDirection.value = "desc";
    }
    localStorage.setItem("holdings_sort_field", sortField.value);
    localStorage.setItem("holdings_sort_direction", sortDirection.value);
  }

  function getCurrentDate() {
    const today = new Date();
    return `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}-${String(today.getDate()).padStart(2, "0")}`;
  }

  function getChangeRateColor(rate) {
    const numRate = parseFloat(rate);
    if (isNaN(numRate) || numRate === 0) return "#6c757d";
    return numRate > 0 ? "#dc3545" : "#28a745";
  }

  return {
    holdings,
    isLoaded,
    isRefreshing,
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
    updateHoldingLocally,
    deleteHolding,
    handleSort,
    getCurrentDate,
    getChangeRateColor,
  };
}
