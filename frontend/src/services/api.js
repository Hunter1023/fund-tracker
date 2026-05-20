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

let isRefreshing = false;
let refreshSubscribers = [];

function subscribeTokenRefresh(resolve) {
  refreshSubscribers.push(resolve);
}

function onTokenRefreshed(newToken) {
  refreshSubscribers.forEach((resolve) => resolve(newToken));
  refreshSubscribers = [];
}

function onRefreshFailed() {
  refreshSubscribers.forEach((resolve) => resolve(null));
  refreshSubscribers = [];
}

async function tryRefreshToken() {
  const refreshToken = localStorage.getItem("refresh_token");
  if (!refreshToken) {
    return null;
  }

  try {
    const response = await axios.post(`${API_BASE_URL}/auth/refresh`, null, {
      headers: {
        Authorization: `Bearer ${refreshToken}`,
        "Content-Type": "application/json",
      },
    });

    const { token, refresh_token, user } = response.data;
    localStorage.setItem("auth_token", token);
    localStorage.setItem("refresh_token", refresh_token);
    localStorage.setItem("auth_user", JSON.stringify(user));
    window.dispatchEvent(new CustomEvent("auth-changed", { detail: user }));
    return token;
  } catch {
    return null;
  }
}

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (
      error.response &&
      error.response.status === 401 &&
      !originalRequest._retry
    ) {
      originalRequest._retry = true;

      if (!isRefreshing) {
        isRefreshing = true;
        const newToken = await tryRefreshToken();
        isRefreshing = false;

        if (newToken) {
          onTokenRefreshed(newToken);
          originalRequest.headers.Authorization = `Bearer ${newToken}`;
          return api(originalRequest);
        } else {
          onRefreshFailed();
          clearAuthData();
          return Promise.reject(error);
        }
      }

      return new Promise((resolve) => {
        subscribeTokenRefresh((newToken) => {
          if (newToken) {
            originalRequest.headers.Authorization = `Bearer ${newToken}`;
            resolve(api(originalRequest));
          } else {
            resolve(Promise.reject(error));
          }
        });
      });
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

export const userApi = {
  getProfile: () => api.get("/user/profile"),

  updateProfile: (data) => api.put("/user/profile", data),

  sendLinkEmailCode: (email) => api.post("/auth/email/send-code", { email }),

  linkEmail: (email, code) => api.post("/user/email/link", { email, code }),

  setPassword: (password, confirmPassword) =>
    api.post("/user/password/set", {
      password,
      confirm_password: confirmPassword,
    }),

  linkGithub: (code) => api.post("/user/github/link", { code }),

  getGithubConfig: () => api.get("/auth/github/config"),
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

export function setAuthData(token, user, refreshToken) {
  localStorage.setItem("auth_token", token);
  localStorage.setItem("auth_user", JSON.stringify(user));
  if (refreshToken) {
    localStorage.setItem("refresh_token", refreshToken);
  }
  window.dispatchEvent(new CustomEvent("auth-changed", { detail: user }));
}

export function clearAuthData() {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_user");
  localStorage.removeItem("refresh_token");
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
    // 检查前端缓存是否有效
    if (
      cache.fundHistory.data[fundCode] &&
      now - cache.fundHistory.timestamp[fundCode] < cache.expiry
    ) {
      const cachedData = cache.fundHistory.data[fundCode];
      // 判断缓存的数据格式
      if (cachedData.net_values) {
        // 预加载的数据格式（来自 /fund/{fundCode}/history）
        return { data: { history_data: cachedData } };
      } else if (cachedData.history_data) {
        // 直接调用 complete 接口返回的格式
        return { data: cachedData };
      } else {
        // 未知格式，尝试使用缓存数据作为 history_data
        return { data: { history_data: cachedData } };
      }
    }
    const response = await api.get(`/fund/${fundCode}/complete`);
    if (response.data.history_data) {
      cache.fundHistory.data[fundCode] = response.data.history_data;
      cache.fundHistory.timestamp[fundCode] = Date.now();
    }
    return response;
  },
  get: (fundCode) => api.get(`/fund/${fundCode}`),

  preloadFundHistory: async (fundCodes) => {
    const now = Date.now();
    const promises = [];
    let cachedCount = 0;
    let needLoadCount = 0;

    console.log(`[预加载] 开始处理 ${fundCodes.length} 个基金`);

    for (const fundCode of fundCodes) {
      // 跳过已缓存的基金
      if (
        cache.fundHistory.data[fundCode] &&
        now - cache.fundHistory.timestamp[fundCode] < cache.expiry
      ) {
        cachedCount++;
        continue;
      }

      needLoadCount++;
      // 并行获取历史数据
      promises.push(
        api
          .get(`/fund/${fundCode}/history`)
          .then((response) => {
            console.log(`[预加载] 基金 ${fundCode} 加载成功，数据长度:`, response.data?.net_values?.length || 0);
            cache.fundHistory.data[fundCode] = response.data;
            cache.fundHistory.timestamp[fundCode] = Date.now();
            return { fundCode, success: true };
          })
          .catch((error) => {
            console.warn(`[预加载] 基金 ${fundCode} 加载失败:`, error);
            return { fundCode, success: false, error };
          }),
      );
    }

    console.log(`[预加载] 缓存命中: ${cachedCount} 个, 需要加载: ${needLoadCount} 个`);

    if (promises.length > 0) {
      console.log(`[预加载] 开始加载 ${promises.length} 个基金的历史数据...`);
      const results = await Promise.all(promises);
      const successCount = results.filter((r) => r.success).length;
      console.log(
        `[预加载] 加载完成: 成功 ${successCount} 个, 失败 ${results.length - successCount} 个`,
      );
      return results;
    } else {
      console.log("[预加载] 所有基金历史数据已在缓存中，无需加载");
      return [];
    }
  },
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
  delete: (fundCode, platform = "默认") =>
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
