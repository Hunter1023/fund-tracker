import axios from "axios";

const API_BASE_URL = "/api";

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem("auth_token");
      localStorage.removeItem("auth_user");
      window.dispatchEvent(new CustomEvent("auth-changed", { detail: null }));
    }
    return Promise.reject(error);
  },
);

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
  expiry: 3600000,
};

function isCacheValid(cacheItem) {
  return cacheItem.data && Date.now() - cacheItem.timestamp < cache.expiry;
}

export function clearAllCache() {
  cache.platforms.data = null;
  cache.tags.data = null;
  cache.fundHistory.data = {};
  cache.fundHistory.timestamp = {};
}

export const authApi = {
  register: (username, password) =>
    api.post("/auth/register", { username, password }),

  login: (username, password) =>
    api.post("/auth/login", { username, password }),

  sendEmailCode: (email) => api.post("/auth/email/send-code", { email }),

  emailLogin: (email, code) => api.post("/auth/email/login", { email, code }),

  githubAuth: (code) => api.post("/auth/github", { code }),

  getMe: () => api.get("/auth/me"),

  getGithubConfig: () => api.get("/auth/github/config"),

  getEmailConfig: () => api.get("/auth/email/config"),
};

export function getStoredUser() {
  try {
    const user = localStorage.getItem("auth_user");
    return user ? JSON.parse(user) : null;
  } catch {
    return null;
  }
}

export function getStoredToken() {
  return localStorage.getItem("auth_token");
}

export function setAuthData(token, user) {
  localStorage.setItem("auth_token", token);
  localStorage.setItem("auth_user", JSON.stringify(user));
  window.dispatchEvent(new CustomEvent("auth-changed", { detail: user }));
}

export function clearAuthData() {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_user");
  clearAllCache();
  window.dispatchEvent(new CustomEvent("auth-changed", { detail: null }));
}

export const fundApi = {
  search: (keyword, signal) =>
    api.get(`/fund/search?keyword=${encodeURIComponent(keyword)}`, { signal }),

  getChart: (fundCode) => api.get(`/fund/${fundCode}/chart`),
  getHistory: async (fundCode) => {
    const now = Date.now();
    if (
      cache.fundHistory.data[fundCode] &&
      now - cache.fundHistory.timestamp[fundCode] < cache.expiry
    ) {
      return { data: cache.fundHistory.data[fundCode] };
    }
    const response = await api.get(`/fund/${fundCode}/history`);
    cache.fundHistory.data[fundCode] = response.data;
    cache.fundHistory.timestamp[fundCode] = now;
    return response;
  },
  getCompleteInfo: async (fundCode) => {
    const now = Date.now();
    if (
      cache.fundHistory.data[fundCode] &&
      now - cache.fundHistory.timestamp[fundCode] < cache.expiry
    ) {
      return {
        data: {
          fund_info: null,
          history_data: cache.fundHistory.data[fundCode],
          transactions: [],
        },
      };
    }
    const response = await api.get(`/fund/${fundCode}/complete`);
    if (response.data.history_data) {
      cache.fundHistory.data[fundCode] = response.data.history_data;
      cache.fundHistory.timestamp[fundCode] = now;
    }
    return response;
  },
  get: (fundCode) => api.get(`/fund/${fundCode}`),
};

export const watchlistApi = {
  get: () => api.get("/watchlist", { params: { _t: Date.now() } }),
  add: (fundCode, tags = "") =>
    api.post("/watchlist", { fund_code: fundCode, tags }),
  remove: (fundCode) =>
    api.delete("/watchlist", { data: { fund_code: fundCode } }),
  updateTags: (fundCode, tags) =>
    api.put("/watchlist/tags", { fund_code: fundCode, tags }),
};

export const holdingApi = {
  get: () => api.get("/holding", { params: { _t: Date.now() } }),
  getCodes: () => api.get("/holding/codes"),
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
    cache.platforms.data = null;
    return response;
  },
  update: async (id, name) => {
    const response = await api.put(`/platform/${id}`, { name });
    cache.platforms.data = null;
    return response;
  },
  delete: async (id) => {
    const response = await api.delete(`/platform/${id}`);
    cache.platforms.data = null;
    return response;
  },
  updateOrder: async (orderData) => {
    const response = await api.put("/platform/order", { order: orderData });
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
