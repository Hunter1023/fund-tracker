import axios from "axios";

const API_BASE_URL = "/api";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// 缓存管理
const cache = {
  platforms: {
    data: null,
    timestamp: 0,
  },
  tags: {
    data: null,
    timestamp: 0,
  },
  fundHistory: {
    data: {},
    timestamp: {},
  },
  // 缓存有效期（毫秒）
  expiry: 3600000, // 1小时
};

// 检查缓存是否有效
function isCacheValid(cacheItem) {
  return cacheItem.data && Date.now() - cacheItem.timestamp < cache.expiry;
}

export const fundApi = {
  search: (keyword, signal) =>
    api.get(`/fund/search?keyword=${encodeURIComponent(keyword)}`, { signal }),

  getChart: (fundCode) => api.get(`/fund/${fundCode}/chart`),
  getHistory: async (fundCode) => {
    const now = Date.now();
    // 检查缓存
    if (
      cache.fundHistory.data[fundCode] &&
      now - cache.fundHistory.timestamp[fundCode] < cache.expiry
    ) {
      return { data: cache.fundHistory.data[fundCode] };
    }
    // 缓存无效，请求新数据
    const response = await api.get(`/fund/${fundCode}/history`);
    // 更新缓存
    cache.fundHistory.data[fundCode] = response.data;
    cache.fundHistory.timestamp[fundCode] = now;
    return response;
  },
  getCompleteInfo: async (fundCode) => {
    const now = Date.now();
    // 检查缓存
    if (
      cache.fundHistory.data[fundCode] &&
      now - cache.fundHistory.timestamp[fundCode] < cache.expiry
    ) {
      // 如果已有历史数据缓存，直接使用
      return {
        data: {
          fund_info: null,
          history_data: cache.fundHistory.data[fundCode],
          transactions: [],
        },
      };
    }
    // 缓存无效，请求新数据
    const response = await api.get(`/fund/${fundCode}/complete`);
    // 更新缓存
    if (response.data.history_data) {
      cache.fundHistory.data[fundCode] = response.data.history_data;
      cache.fundHistory.timestamp[fundCode] = now;
    }
    return response;
  },
  get: (fundCode) => api.get(`/fund/${fundCode}`),
};

export const watchlistApi = {
  get: () => api.get("/watchlist"),
  add: (fundCode, tags = "") =>
    api.post("/watchlist", { fund_code: fundCode, tags }),
  remove: (fundCode) =>
    api.delete("/watchlist", { data: { fund_code: fundCode } }),
  updateTags: (fundCode, tags) =>
    api.put("/watchlist/tags", { fund_code: fundCode, tags }),
};

export const holdingApi = {
  get: () => api.get("/holding"),
  add: (data) => api.post("/holding", data),
  update: (fundCode, data) => api.put(`/holding/${fundCode}`, data),
  updateTags: (fundCode, tags) =>
    api.put("/holding/tags", { fund_code: fundCode, tags }),
  delete: (fundCode, platform = "其他") =>
    api.delete(`/holding/${fundCode}`, { data: { platform } }),
  getTransactions: (fundCode) => api.get(`/transaction/${fundCode}`),
};

export const platformApi = {
  get: async () => {
    if (isCacheValid(cache.platforms)) {
      return { data: cache.platforms.data };
    }
    const response = await api.get("/platform");
    cache.platforms.data = response.data;
    cache.platforms.timestamp = Date.now();
    return response;
  },
  add: async (name) => {
    const response = await api.post("/platform", { name });
    // 清除缓存，下次需要重新获取
    cache.platforms.data = null;
    return response;
  },
  update: async (id, name) => {
    const response = await api.put(`/platform/${id}`, { name });
    // 清除缓存，下次需要重新获取
    cache.platforms.data = null;
    return response;
  },
  delete: async (id) => {
    const response = await api.delete(`/platform/${id}`);
    // 清除缓存，下次需要重新获取
    cache.platforms.data = null;
    return response;
  },
  updateOrder: async (orderData) => {
    const response = await api.put("/platform/order", { order: orderData });
    // 清除缓存，下次需要重新获取
    cache.platforms.data = null;
    return response;
  },
};

export const tagsApi = {
  get: async () => {
    if (isCacheValid(cache.tags)) {
      return { data: cache.tags.data };
    }
    const response = await api.get("/tags");
    cache.tags.data = response.data;
    cache.tags.timestamp = Date.now();
    return response;
  },
};

export default api;
