<template>
  <div class="app-container">
    <aside class="sidebar" v-if="route.name !== 'Login'">
      <div class="logo">PlateAgent</div>
      <nav>
        <router-link to="/dashboard" class="nav-item">
          <span>📊</span> 监控大屏
        </router-link>
        <router-link to="/records" class="nav-item">
          <span>📋</span> 识别记录
        </router-link>
        <router-link to="/agent-lab" class="nav-item nav-highlight">
          <span>🤖</span> AI 实验室
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <button @click="logout" class="btn-logout">退出</button>
      </div>
    </aside>
    <main :class="{ 'full-width': route.name === 'Login' }">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { useRoute, useRouter } from 'vue-router'
const route = useRoute()
const router = useRouter()
function logout() {
  localStorage.removeItem('token')
  router.push('/login')
}
</script>

<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f1923; color: #e0e0e0; }
.app-container { display: flex; min-height: 100vh; }
.sidebar { width: 220px; background: #1a2736; border-right: 1px solid #2a3a4a; display: flex; flex-direction: column; padding: 20px 0; }
.logo { font-size: 20px; font-weight: 700; color: #4fc3f7; padding: 0 20px 24px; letter-spacing: 1px; }
.nav-item { display: flex; align-items: center; gap: 10px; padding: 12px 20px; color: #8fa4b8; text-decoration: none; font-size: 14px; transition: all 0.2s; }
.nav-item:hover, .nav-item.router-link-active { background: #243447; color: #4fc3f7; }
.nav-highlight { border-left: 3px solid #4fc3f7; }
.sidebar-footer { margin-top: auto; padding: 0 20px; }
.btn-logout { width: 100%; padding: 10px; background: transparent; border: 1px solid #3a4a5a; color: #8fa4b8; border-radius: 6px; cursor: pointer; font-size: 13px; }
.btn-logout:hover { background: #2a3a4a; color: #e0e0e0; }
main { flex: 1; padding: 24px; overflow-y: auto; }
main.full-width { padding: 0; }
</style>
