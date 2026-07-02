import { defineStore } from 'pinia'
import { ref } from 'vue'
import api from '../api'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref('')

  async function login(credentials) {
    const { data } = await api.login(credentials)
    token.value = data.token
    username.value = data.username
    localStorage.setItem('token', data.token)
  }

  function logout() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('token')
  }

  return { token, username, login, logout }
})