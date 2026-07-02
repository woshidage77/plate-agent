import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 15000,
})

api.interceptors.request.use(config => {
  const token = localStorage.getItem('token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  res => res,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('token')
      window.location.hash = '#/login'
    }
    return Promise.reject(err)
  }
)

export default {
  login: (data) => api.post('/auth/login', data),
  getRecords: (params) => api.get('/records', { params }),
  getTodayStats: () => api.get('/records/stats/today'),
  getHourlyStats: () => api.get('/records/stats/hourly'),
  getBlacklist: (params) => api.get('/records/blacklist', { params }),
}