<template>
  <div class="records-page">
    <h2>识别记录</h2>
    <div class="filters">
      <input v-model="searchPlate" placeholder="搜索车牌号..." @keyup.enter="search" />
      <select v-model="searchStatus">
        <option value="">全部状态</option>
        <option value="success">成功</option>
        <option value="partial">部分成功</option>
        <option value="failed">失败</option>
      </select>
      <button @click="search" class="btn-search">搜索</button>
      <button @click="loadBlacklist" class="btn-blacklist">黑名单记录</button>
    </div>

    <table>
      <thead>
        <tr>
          <th>ID</th><th>车牌号</th><th>图片</th><th>颜色</th><th>置信度</th><th>识别方式</th><th>黑名单</th><th>耗时</th><th>状态</th><th>时间</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in records" :key="r.id">
          <td>{{ r.id }}</td>
          <td><strong>{{ r.plateNumber }}</strong></td>
          <td class="img-cell">{{ r.imagePath ? '📷' : '-' }}</td>
          <td>{{ r.plateColor || '-' }}</td>
          <td>{{ r.avgConfidence ? (r.avgConfidence * 100).toFixed(1) + '%' : '-' }}</td>
          <td>{{ r.recognizeMethod || '-' }}</td>
          <td>{{ r.blacklistHit ? '⚠ ' + (r.blacklistType || '是') : '否' }}</td>
          <td>{{ r.processTimeMs ? r.processTimeMs + 'ms' : '-' }}</td>
          <td><span :class="'tag tag-' + r.status">{{ statusMap[r.status] || r.status }}</span></td>
          <td>{{ formatTime(r.createdAt) }}</td>
        </tr>
      </tbody>
    </table>

    <div class="pagination">
      <button :disabled="page === 0" @click="goPage(page - 1)">上一页</button>
      <span>第 {{ page + 1 }} 页 / 共 {{ totalPages }} 页</span>
      <button :disabled="page >= totalPages - 1" @click="goPage(page + 1)">下一页</button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const statusMap = { success: '成功', partial: '部分', failed: '失败' }
const searchPlate = ref('')
const searchStatus = ref('')
const records = ref([])
const page = ref(0)
const totalPages = ref(1)
const blacklistMode = ref(false)

function formatTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleString('zh-CN')
}

async function fetchData() {
  const params = { page: page.value, size: 20 }
  if (searchPlate.value) params.plate = searchPlate.value
  if (searchStatus.value) params.status = searchStatus.value
  try {
    const res = blacklistMode.value ? await api.getBlacklist(params) : await api.getRecords(params)
    records.value = res.data.content || []
    totalPages.value = res.data.totalPages || 1
  } catch (e) { console.error(e) }
}

function search() { page.value = 0; fetchData() }
function goPage(p) { page.value = p; fetchData() }
function loadBlacklist() { blacklistMode.value = !blacklistMode.value; page.value = 0; fetchData() }

onMounted(fetchData)
</script>

<style scoped>
.records-page { max-width: 1400px; }
h2 { font-size: 22px; font-weight: 600; margin-bottom: 18px; }
.filters { display: flex; gap: 10px; margin-bottom: 20px; }
.filters input, .filters select { padding: 10px 14px; background: #1a2736; border: 1px solid #2a3a4a; border-radius: 8px; color: #e0e0e0; font-size: 13px; outline: none; }
.filters input { width: 220px; }
.filters select { width: 140px; }
.btn-search { padding: 10px 20px; background: #4fc3f7; color: #0f1923; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; }
.btn-blacklist { padding: 10px 20px; background: #e91e63; color: #fff; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; }
table { width: 100%; border-collapse: collapse; background: #1a2736; border-radius: 10px; overflow: hidden; }
th { text-align: left; padding: 12px 14px; background: #243447; color: #8fa4b8; font-size: 12px; font-weight: 500; text-transform: uppercase; }
td { padding: 11px 14px; border-bottom: 1px solid #1e2d3d; font-size: 13px; color: #b0bec5; }
.img-cell { font-size: 18px; }
.tag { padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.tag-success { background: rgba(76,175,80,0.2); color: #4caf50; }
.tag-partial { background: rgba(255,152,0,0.2); color: #ff9800; }
.tag-failed { background: rgba(239,83,80,0.2); color: #ef5350; }
.pagination { display: flex; align-items: center; justify-content: center; gap: 16px; margin-top: 20px; }
.pagination button { padding: 8px 18px; background: #243447; border: 1px solid #2a3a4a; color: #e0e0e0; border-radius: 6px; cursor: pointer; font-size: 13px; }
.pagination button:disabled { opacity: 0.4; cursor: default; }
.pagination span { color: #8fa4b8; font-size: 13px; }
</style>