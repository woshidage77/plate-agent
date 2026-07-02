<template>
  <div class="login-page">
    <div class="login-card">
      <h1>PlateAgent</h1>
      <p>车牌识别智能体管理后台</p>
      <form @submit.prevent="handleLogin">
        <input v-model="form.username" placeholder="用户名" />
        <input v-model="form.password" type="password" placeholder="密码" />
        <button type="submit">登 录</button>
      </form>
      <p v-if="error" class="error">{{ error }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const form = reactive({ username: '', password: '' })
const error = ref('')

async function handleLogin() {
  error.value = ''
  try {
    await api.login(form)
    router.push('/dashboard')
  } catch (e) {
    error.value = e.response?.data?.error || '登录失败'
  }
}
</script>

<style scoped>
.login-page { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: #0f1923; }
.login-card { width: 380px; padding: 40px; background: #1a2736; border-radius: 12px; border: 1px solid #2a3a4a; text-align: center; }
.login-card h1 { font-size: 28px; color: #4fc3f7; margin-bottom: 8px; }
.login-card p { color: #8fa4b8; font-size: 13px; margin-bottom: 28px; }
input { width: 100%; padding: 12px 16px; margin-bottom: 14px; background: #0f1923; border: 1px solid #2a3a4a; border-radius: 8px; color: #e0e0e0; font-size: 14px; outline: none; }
input:focus { border-color: #4fc3f7; }
button { width: 100%; padding: 12px; background: #4fc3f7; color: #0f1923; border: none; border-radius: 8px; font-size: 15px; font-weight: 600; cursor: pointer; }
button:hover { background: #39b8e8; }
.error { color: #ef5350; font-size: 13px; margin-top: 12px; }
</style>