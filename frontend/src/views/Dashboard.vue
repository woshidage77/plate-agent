 <template>
  <div class="dashboard">
    <h2>识别监控大屏</h2>
    <p class="subtitle">{{ today }}</p>

    <!-- 统计卡片 -->
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-value">{{ stats.totalRecognitions }}</div>
        <div class="stat-label">总识别次数</div>
      </div>
      <div class="stat-card success">
        <div class="stat-value">{{ stats.successCount }}</div>
        <div class="stat-label">成功</div>
      </div>
      <div class="stat-card warn">
        <div class="stat-value">{{ stats.partialCount }}</div>
        <div class="stat-label">部分成功</div>
      </div>
      <div class="stat-card danger">
        <div class="stat-value">{{ stats.failedCount }}</div>
        <div class="stat-label">失败</div>
      </div>
      <div class="stat-card alert">
        <div class="stat-value">{{ stats.blacklistHits }}</div>
        <div class="stat-label">黑名单命中</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">{{ (stats.avgConfidence * 100).toFixed(1) }}%</div>
        <div class="stat-label">平均置信度</div>
      </div>
    </div>

    <!-- 图表行 -->
    <div class="chart-row">
      <div class="chart-panel">
        <h3>今日识别趋势</h3>
        <v-chart :option="hourlyOption" autoresize style="height:320px" />
      </div>
      <div class="chart-panel">
        <h3>识别状态分布</h3>
        <v-chart :option="pieOption" autoresize style="height:320px" />
      </div>
    </div>

    <!-- 最近记录 -->
    <div class="recent-section">
      <h3>最近识别记录</h3>
      <table>
        <thead>
          <tr>
            <th>车牌号</th><th>状态</th><th>置信度</th><th>识别方式</th><th>黑名单</th><th>耗时</th><th>时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in recentRecords" :key="r.id">
            <td><strong>{{ r.plateNumber }}</strong></td>
            <td><span :class="'tag tag-' + r.status">{{ statusMap[r.status] || r.status }}</span></td>
            <td>{{ r.avgConfidence ? (r.avgConfidence * 100).toFixed(1) + '%' : '-' }}</td>
            <td>{{ r.recognizeMethod || '-' }}</td>
            <td>{{ r.blacklistHit ? '⚠ ' + (r.blacklistType || '是') : '否' }}</td>
            <td>{{ r.processTimeMs ? r.processTimeMs + 'ms' : '-' }}</td>
            <td>{{ formatTime(r.createdAt) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { BarChart, PieChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, GridComponent, LegendComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import api from '../api'

use([BarChart, PieChart, TitleComponent, TooltipComponent, GridComponent, LegendComponent, CanvasRenderer])

const today = new Date().toLocaleDateString('zh-CN', { year:'numeric', month:'long', day:'numeric', weekday:'long' })

const statusMap = { success: '成功', partial: '部分', failed: '失败' }

const stats = reactive({
  totalRecognitions: 0, successCount: 0, partialCount: 0, failedCount: 0,
  blacklistHits: 0, avgConfidence: 0, avgProcessTimeMs: 0,
})

const recentRecords = ref([])

const hourlyOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 40, right: 20, top: 20, bottom: 30 },
  xAxis: { type: 'category', data: Array.from({length:24}, (_,i) => i+'h'), axisLabel: { color: '#8fa4b8', fontSize: 11 } },
  yAxis: { type: 'value', axisLabel: { color: '#8fa4b8' } },
  series: [{
    type: 'bar', data: hourlyData.value, itemStyle: { color: '#4fc3f7', borderRadius: [3,3,0,0] },
    barWidth: '70%',
  }],
}))

const hourlyData = ref(new Array(24).fill(0))

const pieOption = computed(() => ({
  tooltip: { trigger: 'item' },
  legend: { bottom: 10, textStyle: { color: '#8fa4b8', fontSize: 12 } },
  series: [{
    type: 'pie', radius: ['50%', '75%'], center: ['50%', '45%'],
    label: { color: '#8fa4b8' },
    data: [
      { value: stats.successCount, name: '成功', itemStyle: { color: '#4caf50' } },
      { value: stats.partialCount, name: '部分成功', itemStyle: { color: '#ff9800' } },
      { value: stats.failedCount, name: '失败', itemStyle: { color: '#ef5350' } },
    ],
  }],
}))

function formatTime(t) {
  if (!t) return '-'
  return new Date(t).toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit', second:'2-digit' })
}

async function loadData() {
  try {
    const [sRes, hRes, rRes] = await Promise.all([
      api.getTodayStats(), api.getHourlyStats(), api.getRecords({ page: 0, size: 5 })
    ])
    Object.assign(stats, sRes.data)
    const hArr = new Array(24).fill(0)
    hRes.data.forEach(h => { hArr[h.hour] = h.count })
    hourlyData.value = hArr
    recentRecords.value = rRes.data.content || []
  } catch (e) { console.error(e) }
}

onMounted(() => {
  loadData()
  setInterval(loadData, 10000) // 10s 自动刷新
})
</script>

<style scoped>
.dashboard { max-width: 1400px; }
h2 { font-size: 22px; font-weight: 600; color: #e0e0e0; }
.subtitle { color: #8fa4b8; font-size: 13px; margin: 4px 0 20px; }
.stat-cards { display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; margin-bottom: 24px; }
.stat-card { background: #1a2736; border: 1px solid #2a3a4a; border-radius: 10px; padding: 18px 16px; text-align: center; }
.stat-card.success { border-left: 3px solid #4caf50; }
.stat-card.warn { border-left: 3px solid #ff9800; }
.stat-card.danger { border-left: 3px solid #ef5350; }
.stat-card.alert { border-left: 3px solid #e91e63; }
.stat-value { font-size: 28px; font-weight: 700; color: #e0e0e0; }
.stat-label { font-size: 12px; color: #8fa4b8; margin-top: 4px; }
.chart-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-bottom: 24px; }
.chart-panel { background: #1a2736; border: 1px solid #2a3a4a; border-radius: 10px; padding: 18px; }
.chart-panel h3 { font-size: 14px; color: #8fa4b8; margin-bottom: 10px; }
.recent-section { background: #1a2736; border: 1px solid #2a3a4a; border-radius: 10px; padding: 18px; }
.recent-section h3 { font-size: 14px; color: #8fa4b8; margin-bottom: 12px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { text-align: left; padding: 10px 12px; color: #8fa4b8; border-bottom: 1px solid #2a3a4a; font-weight: 500; }
td { padding: 10px 12px; border-bottom: 1px solid #1e2d3d; color: #b0bec5; }
.tag { padding: 2px 8px; border-radius: 4px; font-size: 11px; }
.tag-success { background: rgba(76,175,80,0.2); color: #4caf50; }
.tag-partial { background: rgba(255,152,0,0.2); color: #ff9800; }
.tag-failed { background: rgba(239,83,80,0.2); color: #ef5350; }
</style>