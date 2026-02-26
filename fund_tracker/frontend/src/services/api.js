import axios from 'axios'

const API_BASE_URL = '/api'

const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json'
  }
})

export const fundApi = {
  search: (keyword) => api.get(`/fund/search?keyword=${encodeURIComponent(keyword)}`),
  getChart: (fundCode) => api.get(`/fund/${fundCode}/chart`),
  getHistory: (fundCode) => api.get(`/fund/${fundCode}/history`),
  get: (fundCode) => api.get(`/fund/${fundCode}`)
}

export const watchlistApi = {
  get: () => api.get('/watchlist'),
  add: (fundCode, tags = '') => api.post('/watchlist', { fund_code: fundCode, tags }),
  remove: (fundCode) => api.delete('/watchlist', { data: { fund_code: fundCode } }),
  updateTags: (fundCode, tags) => api.put('/watchlist/tags', { fund_code: fundCode, tags })
}

export const holdingApi = {
  get: () => api.get('/holding'),
  add: (data) => api.post('/holding', data),
  update: (fundCode, data) => api.put(`/holding/${fundCode}`, data),
  updateTags: (fundCode, tags) => api.put('/holding/tags', { fund_code: fundCode, tags }),
  delete: (fundCode, platform = '其他') => api.delete(`/holding/${fundCode}`, { data: { platform } }),
  getTransactions: (fundCode) => api.get(`/transaction/${fundCode}`)
}

export const platformApi = {
  get: () => api.get('/platform'),
  add: (name) => api.post('/platform', { name }),
  update: (id, name) => api.put(`/platform/${id}`, { name }),
  delete: (id) => api.delete(`/platform/${id}`),
  updateOrder: (orderData) => api.put('/platform/order', { order: orderData })
}

export default api
