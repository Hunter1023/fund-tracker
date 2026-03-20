import { computed, ref } from "vue";
import { fundApi, watchlistApi } from "../services/api";

export function useWatchlist() {
  const funds = ref([]);
  const loading = ref(false);
  const currentTag = ref("");
  const searchKeyword = ref("");
  const searchResults = ref([]);
  const showSearchDropdown = ref(false);
  const sortField = ref("daily_change_rate");
  const sortDirection = ref("desc");
  const columnOrder = ref([
    "tags",
    "name",
    "daily_change_rate",
    "estimate_change_rate",
    "one_month_rate",
    "three_month_rate",
    "one_year_rate",
    "action",
  ]);
  const draggedColumn = ref(null);
  const columnWidths = ref({});
  const holdingCodes = ref([]);

  const filteredFunds = computed(() => {
    let result = funds.value;

    if (currentTag.value) {
      result = result.filter((fund) => {
        const tags = fund.tags || "";
        const tagsArray = tags
          .split(",")
          .map((tag) => tag.trim())
          .filter((tag) => tag);
        return tagsArray.includes(currentTag.value);
      });
    }

    return sortFunds(result, sortField.value, sortDirection.value);
  });

  const allTags = computed(() => {
    const tags = new Set();
    funds.value.forEach((fund) => {
      const tagsList = fund.tags || "";
      const tagsArray = tagsList
        .split(",")
        .map((tag) => tag.trim())
        .filter((tag) => tag);
      tagsArray.forEach((tag) => tags.add(tag));
    });

    return Array.from(tags).sort((a, b) => {
      const isEnglishA = /^[a-zA-Z0-9\s]+$/.test(a);
      const isEnglishB = /^[a-zA-Z0-9\s]+$/.test(b);

      if (isEnglishA && !isEnglishB) {
        return -1;
      } else if (!isEnglishA && isEnglishB) {
        return 1;
      } else {
        return a.localeCompare(b);
      }
    });
  });

  const tagCounts = computed(() => {
    const counts = {};
    funds.value.forEach((fund) => {
      const tagsList = fund.tags || "";
      const tagsArray = tagsList
        .split(",")
        .map((tag) => tag.trim())
        .filter((tag) => tag);
      tagsArray.forEach((tag) => {
        counts[tag] = (counts[tag] || 0) + 1;
      });
    });
    return counts;
  });

  async function loadWatchlist() {
    loading.value = true;
    try {
      const response = await watchlistApi.get();
      funds.value = response.data;
    } catch (error) {
      console.error("加载自选失败:", error);
    } finally {
      loading.value = false;
    }
  }

  async function loadHoldingCodes() {
    try {
      const response = await holdingApi.getCodes();
      holdingCodes.value = response.data.fund_codes || [];
    } catch (error) {
      console.error("加载持仓基金代码失败:", error);
      holdingCodes.value = [];
    }
  }

  function isHolding(fundCode) {
    return holdingCodes.value.includes(fundCode);
  }

  async function addToWatchlist(fundCode, tags = "") {
    try {
      const response = await watchlistApi.add(fundCode, tags);
      if (response.data.success) {
        if (response.data.fund) {
          funds.value.push(response.data.fund);
        } else {
          const newFund = {
            fund_code: fundCode,
            tags: tags,
            fund_name: "",
            net_value: "",
            unit_net_value: "",
            estimate_net_value: "",
            estimate_change_rate: "-",
            estimate_time: "",
            one_month_rate: 0,
            three_month_rate: 0,
            one_year_rate: 0,
            daily_change_rate: "-",
          };
          funds.value.push(newFund);
        }

        // 异步获取基金最新数据并更新本地自选
        fundApi
          .get(fundCode)
          .then((fundResponse) => {
            const fundData = fundResponse.data;
            if (fundData) {
              const index = funds.value.findIndex(
                (f) => f.fund_code === fundCode,
              );
              if (index !== -1) {
                // 使用 splice 方法更新数组元素，保持数组引用的稳定性
                const updatedFund = {
                  ...funds.value[index],
                  fund_name: fundData.fund_name || funds.value[index].fund_name,
                  daily_change_rate: fundData.daily_change_rate || "-",
                  estimate_change_rate: fundData.estimate_change_rate || "-",
                  one_month_rate: fundData.one_month_rate || 0,
                  three_month_rate: fundData.three_month_rate || 0,
                  one_year_rate: fundData.one_year_rate || 0,
                  net_value: fundData.net_value || "",
                  unit_net_value: fundData.unit_net_value || "",
                  estimate_net_value: fundData.estimate_net_value || "",
                  estimate_time: fundData.estimate_time || "",
                };
                funds.value.splice(index, 1, updatedFund);
              }
            }
          })
          .catch((error) => {
            console.error("获取基金数据失败:", error);
          });
      }
      return response.data;
    } catch (error) {
      console.error("添加自选失败:", error);
      throw error;
    }
  }

  async function removeFromWatchlist(fundCode) {
    loading.value = true;
    try {
      const response = await watchlistApi.remove(fundCode);
      if (response.data.success) {
        await loadWatchlist();
      }
    } catch (error) {
      console.error("移除自选失败:", error);
    } finally {
      loading.value = false;
    }
  }

  async function changeFundTags(fundCode, tags) {
    try {
      const response = await watchlistApi.updateTags(fundCode, tags);
      if (response.data.success) {
        await loadWatchlist();
      }
      return response.data;
    } catch (error) {
      console.error("修改标签失败:", error);
      throw error;
    }
  }

  function sortFunds(fundsList, field, direction) {
    if (!field) {
      return fundsList;
    }

    return [...fundsList].sort((a, b) => {
      let aValue, bValue;

      switch (field) {
        case "tags":
          aValue = a.tags || "";
          bValue = b.tags || "";
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
        case "one_month_rate":
          aValue = parseFloat(a.one_month_rate) || 0;
          bValue = parseFloat(b.one_month_rate) || 0;
          break;
        case "three_month_rate":
          aValue = parseFloat(a.three_month_rate) || 0;
          bValue = parseFloat(b.three_month_rate) || 0;
          break;
        case "one_year_rate":
          aValue = parseFloat(a.one_year_rate) || 0;
          bValue = parseFloat(b.one_year_rate) || 0;
          break;
        default:
          return 0;
      }

      if (field === "tags" || field === "name") {
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

  function handleSort(field) {
    if (sortField.value === field) {
      sortDirection.value = sortDirection.value === "asc" ? "desc" : "asc";
    } else {
      sortField.value = field;
      sortDirection.value = "desc";
    }
  }

  function handleDragStart(columnKey) {
    draggedColumn.value = columnKey;
  }

  function handleDrop(columnKey) {
    if (draggedColumn.value && draggedColumn.value !== columnKey) {
      const draggedIndex = columnOrder.value.indexOf(draggedColumn.value);
      const targetIndex = columnOrder.value.indexOf(columnKey);

      columnOrder.value.splice(draggedIndex, 1);
      columnOrder.value.splice(targetIndex, 0, draggedColumn.value);
    }
    draggedColumn.value = null;
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
    funds,
    loading,
    currentTag,
    searchKeyword,
    searchResults,
    showSearchDropdown,
    sortField,
    sortDirection,
    columnOrder,
    filteredFunds,
    allTags,
    tagCounts,
    loadWatchlist,
    loadHoldingCodes,
    isHolding,
    addToWatchlist,
    removeFromWatchlist,
    changeFundTags,
    handleSort,
    handleDragStart,
    handleDrop,
    getCurrentDate,
    getChangeRateColor,
  };
}
