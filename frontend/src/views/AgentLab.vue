<template>
  <div class="agent-lab">
    <h2>AI 实验室</h2>
    <p class="subtitle">基于 tRPC-Agent 的 6 节点识别流水线 + 多轮对话</p>

    <div class="lab-layout">
      <div class="left-panel">
        <h3>测试图片</h3>
        <div class="image-grid">
          <div v-for="img in testImages" :key="img"
            :class="['image-card', { active: selectedImage === img }]"
            @click="selectImage(img)">
            <img :src="'/test_images/' + img" :alt="img" />
            <span class="img-name">{{ img }}</span>
          </div>
        </div>
        <div class="custom-path">
          <input v-model="customPath" placeholder="或输入绝对路径..." />
        </div>
      </div>

      <div class="right-panel">
        <div class="tab-bar">
          <button :class="{ active: activeTab === 'pipeline' }"
            @click="activeTab = 'pipeline'">识别管线</button>
          <button :class="{ active: activeTab === 'chat' }"
            @click="activeTab = 'chat'">AI 对话</button>
        </div>

        <!-- 识别管线 -->
        <div v-if="activeTab === 'pipeline'" class="pipeline-view">
          <div class="preview-area">
            <img v-if="previewSrc" :src="previewSrc" alt="预览" class="preview-img" />
            <div v-else class="no-preview">选择图片开始识别</div>
          </div>
          <button class="btn-recognize" @click="startRecognize"
            :disabled="!selectedImage || recognizing">
            {{ recognizing ? '识别中...' : '开始识别' }}
          </button>

          <div v-if="pipelineSteps.length > 0" class="pipeline-progress">
            <h4>管线执行进度</h4>
            <div v-for="(step, i) in pipelineSteps" :key="i"
              :class="['step', 'step-' + step.type]">
              <span class="step-icon">{{ typeIcon(step.type) }}</span>
              <div class="step-body">
                <div class="step-header">
                  <strong>{{ step.label }}</strong>
                  <span class="step-time">{{ step.time }}</span>
                </div>
                <div v-if="step.detail" class="step-detail">{{ step.detail }}</div>
              </div>
            </div>
          </div>

          <div v-if="finalResult" class="result-card">
            <h4>识别结果</h4>
            <div class="result-grid">
              <div class="result-item">
                <span class="r-label">车牌号</span>
                <span class="r-value plate">{{ finalResult.plate_number || '-' }}</span>
              </div>
              <div class="result-item">
                <span class="r-label">黑名单</span>
                <span :class="['r-value', finalResult.blacklist_hit ? 'danger' : 'safe']">
                  {{ finalResult.blacklist_hit ? '命中' : '安全' }}
                </span>
              </div>
            </div>
            <div v-if="finalResult.full_response" class="full-response">
              {{ finalResult.full_response }}
            </div>
          </div>
        </div>

        <!-- AI 对话 -->
        <div v-if="activeTab === 'chat'" class="chat-view">
          <div class="chat-messages" ref="chatMsgs">
            <div v-for="(msg, i) in chatMessages" :key="i"
              :class="['chat-msg', msg.role]">
              <div class="msg-content" v-html="msg.html || msg.text"></div>
              <div v-if="msg.tools && msg.tools.length" class="msg-tools">
                <div v-for="(t, j) in msg.tools" :key="j" class="tool-badge">
                  {{ t.name }}{{ t.result ? ' done' : ' ...' }}
                </div>
              </div>
            </div>
          </div>
          <div class="chat-input">
            <input v-model="chatInput" placeholder="输入消息，如：识别这张车牌、查询黑名单..."
              @keyup.enter="sendChat" :disabled="chatting" />
            <button @click="sendChat" :disabled="chatting || !chatInput.trim()">发送</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'

const testImages = ref([])
onMounted(async () => {
  try {
    const r = await fetch('/test_images/')
    const text = await r.text()
    const parser = new DOMParser()
    const doc = parser.parseFromString(text, 'text/html')
    const links = [...doc.querySelectorAll('a')]
    testImages.value = links
      .map(l => l.getAttribute('href'))
      .filter(h => h && /\.(jpg|png|jpeg)$/i.test(h))
      .map(h => decodeURIComponent(h.replace(/^\//, '').replace('test_images/', '')))
  } catch {
    testImages.value = ['synth_plate.jpg', 'plate_001.jpg', 'plate_002.jpg']
  }
})

const selectedImage = ref('')
const customPath = ref('')
const previewSrc = computed(() => selectedImage.value ? '/test_images/' + selectedImage.value : '')

function selectImage(img) { selectedImage.value = img }

const activeTab = ref('pipeline')
const recognizing = ref(false)
const pipelineSteps = ref([])
const finalResult = ref(null)
const typeIcon = (t) => ({ tool_call: 'TOOL', tool_result: 'RESULT', text_delta: 'TEXT', final: 'DONE', error: 'ERR', done: 'END' }[t] || '-')

async function startRecognize() {
  if (!selectedImage.value) return
  recognizing.value = true
  pipelineSteps.value = []
  finalResult.value = null

  const imgPath = customPath.value || ('test_images/' + selectedImage.value)
  addStep('tool_call', '开始识别 pipeline', imgPath)

  try {
    const resp = await fetch('/agent-api/recognize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        image_path: imgPath,
        user_id: 'demo-user',
        session_id: 'sess-' + Date.now()
      })
    })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('event: ')) {
          currentEvent = trimmed.slice(7)
        } else if (trimmed.startsWith('data: ')) {
          try {
            const payload = JSON.parse(trimmed.slice(6))
            handleSSE(currentEvent, payload)
          } catch {}
        }
      }
    }
  } catch (e) {
    addStep('error', '请求失败', e.message)
  }
  recognizing.value = false
}

function handleSSE(eventType, payload) {
  if (eventType === 'text_delta') {
    addStep('text_delta', 'Agent 输出', (payload.content || '').slice(0, 200))
  } else if (eventType === 'tool_call') {
    addStep('tool_call', '调用: ' + (payload.name || '?'), JSON.stringify(payload.args || {}).slice(0, 200))
  } else if (eventType === 'tool_result') {
    addStep('tool_result', '返回: ' + (payload.name || '?'), (payload.result || '').slice(0, 200))
  } else if (eventType === 'final') {
    finalResult.value = payload
    addStep('final', '识别完成', payload.plate_number || '')
  } else if (eventType === 'error') {
    addStep('error', '错误', payload.message || '未知错误')
  } else if (eventType === 'done') {
    addStep('done', '流结束', payload.session_id || '')
  }
}

function addStep(type, label, detail) {
  pipelineSteps.value.push({ type, label, detail, time: new Date().toLocaleTimeString() })
}

// 对话
const chatting = ref(false)
const chatInput = ref('')
const chatMessages = ref([
  { role: 'agent', text: '你好，我是 PlateAgent。可以帮你识别车牌、查询黑名单、分析易混淆字符。试试上传一张车牌图片或直接提问。' }
])
const chatMsgs = ref(null)

async function sendChat() {
  const msg = chatInput.value.trim()
  if (!msg || chatting.value) return
  chatMessages.value.push({ role: 'user', text: msg })
  chatInput.value = ''
  chatting.value = true

  const agentMsg = { role: 'agent', text: '', html: '', tools: [] }
  chatMessages.value.push(agentMsg)
  await nextTick()
  scrollChat()

  try {
    const resp = await fetch('/agent-api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: msg,
        user_id: 'demo-user',
        session_id: 'chat-' + Date.now(),
        image_path: selectedImage.value ? ('test_images/' + selectedImage.value) : undefined
      })
    })
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''
      for (const line of lines) {
        const trimmed = line.trim()
        if (trimmed.startsWith('event: ')) {
          currentEvent = trimmed.slice(7)
        } else if (trimmed.startsWith('data: ')) {
          try {
            const payload = JSON.parse(trimmed.slice(6))
            if (currentEvent === 'text_delta') {
              agentMsg.text += (payload.content || '')
              agentMsg.html = agentMsg.text.replace(/\n/g, '<br>')
            } else if (currentEvent === 'tool_call') {
              agentMsg.tools.push({ name: payload.name || '?', result: null })
            } else if (currentEvent === 'tool_result') {
              const t = agentMsg.tools.find(t => t.name === payload.name && !t.result)
              if (t) t.result = 'done'
            }
            await nextTick()
            scrollChat()
          } catch {}
        }
      }
    }
  } catch (e) {
    agentMsg.text = '请求失败: ' + e.message
  }
  if (!agentMsg.text) agentMsg.text = '(无响应)'
  chatting.value = false
}

function scrollChat() {
  nextTick(() => {
    const el = chatMsgs.value
    if (el) el.scrollTop = el.scrollHeight
  })
}
</script>

<style scoped>
.agent-lab { max-width: 1500px; }
h2 { font-size: 22px; font-weight: 600; color: #e0e0e0; }
.subtitle { color: #8fa4b8; font-size: 13px; margin: 4px 0 20px; }
.lab-layout { display: grid; grid-template-columns: 320px 1fr; gap: 20px; }
.left-panel { background: #1a2736; border: 1px solid #2a3a4a; border-radius: 10px; padding: 16px; }
.left-panel h3 { font-size: 14px; color: #8fa4b8; margin-bottom: 12px; }
.image-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; max-height: 400px; overflow-y: auto; margin-bottom: 12px; }
.image-card { border: 2px solid transparent; border-radius: 8px; overflow: hidden; cursor: pointer; transition: all 0.2s; }
.image-card:hover { border-color: #4fc3f7; }
.image-card.active { border-color: #4fc3f7; box-shadow: 0 0 8px rgba(79,195,247,0.3); }
.image-card img { width: 100%; height: 80px; object-fit: cover; display: block; }
.img-name { font-size: 10px; color: #8fa4b8; padding: 4px 6px; display: block; text-align: center; background: #0f1923; }
.custom-path input { width: 100%; padding: 8px 10px; background: #0f1923; border: 1px solid #2a3a4a; border-radius: 6px; color: #e0e0e0; font-size: 12px; }
.right-panel { background: #1a2736; border: 1px solid #2a3a4a; border-radius: 10px; padding: 16px; display: flex; flex-direction: column; }
.tab-bar { display: flex; gap: 4px; margin-bottom: 16px; }
.tab-bar button { padding: 8px 20px; background: transparent; border: 1px solid #2a3a4a; color: #8fa4b8; border-radius: 6px; cursor: pointer; font-size: 13px; }
.tab-bar button.active { background: #243447; color: #4fc3f7; border-color: #4fc3f7; }
.preview-area { margin-bottom: 12px; min-height: 180px; background: #0f1923; border-radius: 8px; display: flex; align-items: center; justify-content: center; overflow: hidden; }
.preview-img { max-width: 100%; max-height: 260px; object-fit: contain; }
.no-preview { color: #5a6a7a; font-size: 14px; }
.btn-recognize { padding: 10px 24px; background: #4fc3f7; color: #0f1923; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; margin-bottom: 16px; }
.btn-recognize:disabled { opacity: 0.5; cursor: default; }
.pipeline-progress { margin-bottom: 16px; }
.pipeline-progress h4 { font-size: 13px; color: #8fa4b8; margin-bottom: 8px; }
.step { display: flex; gap: 8px; padding: 6px 0; border-bottom: 1px solid #1e2d3d; font-size: 12px; }
.step-icon { font-size: 11px; flex-shrink: 0; color: #5a6a7a; width: 50px; }
.step-body { flex: 1; min-width: 0; }
.step-header { display: flex; justify-content: space-between; }
.step-header strong { color: #b0bec5; }
.step-time { color: #5a6a7a; font-size: 11px; }
.step-detail { color: #7a8a9a; margin-top: 2px; word-break: break-all; font-size: 11px; }
.step-tool_call .step-icon { color: #ff9800; }
.step-tool_result .step-icon { color: #4caf50; }
.step-error .step-icon { color: #ef5350; }
.step-final .step-icon { color: #4fc3f7; }
.result-card { background: #0f1923; border: 1px solid #2a3a4a; border-radius: 8px; padding: 16px; }
.result-card h4 { font-size: 14px; color: #4fc3f7; margin-bottom: 10px; }
.result-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 10px; }
.result-item { text-align: center; }
.r-label { font-size: 11px; color: #5a6a7a; display: block; }
.r-value { font-size: 18px; font-weight: 600; color: #e0e0e0; }
.r-value.plate { font-size: 26px; letter-spacing: 3px; color: #4fc3f7; }
.r-value.danger { color: #ef5350; }
.r-value.safe { color: #4caf50; }
.full-response { font-size: 12px; color: #8fa4b8; border-top: 1px solid #1e2d3d; padding-top: 8px; white-space: pre-wrap; }
.chat-view { display: flex; flex-direction: column; flex: 1; min-height: 0; }
.chat-messages { flex: 1; overflow-y: auto; max-height: 450px; margin-bottom: 12px; }
.chat-msg { margin-bottom: 10px; padding: 8px 12px; border-radius: 8px; font-size: 13px; max-width: 85%; }
.chat-msg.user { background: #243447; color: #e0e0e0; margin-left: auto; }
.chat-msg.agent { background: #0f1923; color: #b0bec5; border: 1px solid #1e2d3d; }
.msg-tools { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 4px; }
.tool-badge { font-size: 10px; padding: 2px 6px; background: #1a3a2a; color: #4caf50; border-radius: 4px; }
.chat-input { display: flex; gap: 8px; }
.chat-input input { flex: 1; padding: 10px 14px; background: #0f1923; border: 1px solid #2a3a4a; border-radius: 8px; color: #e0e0e0; font-size: 13px; }
.chat-input input:focus { border-color: #4fc3f7; outline: none; }
.chat-input button { padding: 10px 20px; background: #4fc3f7; color: #0f1923; border: none; border-radius: 8px; font-weight: 600; cursor: pointer; }
</style>
