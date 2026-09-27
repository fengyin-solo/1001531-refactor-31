<template>
  <section class="page" data-module="service">
    <header class="page-head">
      <div>
        <h2>服务保障管理</h2>
        <p class="page-desc">维护服务事项，围绕事项编号、服务对象、服务类别、响应时限做登记、筛选与状态流转。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记服务事项</button>
        <button class="btn" type="button" @click="exportRows">导出服务保障清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value" :class="{ 'stat-alert': item.label === '超时未办结' && item.value > 0 }">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>超期</th>
          <th>时限说明</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" :class="{ 'row-overdue': row.超期 }">
          <td v-for="column in columns" :key="column">{{ row[column] === '' || row[column] == null ? '—' : row[column] }}</td>
          <td>
            <span :class="row.超期 ? 'tag-overdue' : 'tag-ok'">{{ row.超期 ? '超期' : '正常' }}</span>
          </td>
          <td class="limit-note">{{ row.时限说明 }}</td>
          <td class="row-actions">
            <button
              v-for="action in actions"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 3" class="empty-state">{{ emptyHint }}</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条服务保障记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | null>
type Stat = { label: string; value: number }

const ENDPOINT = '/api/service'
const columns = ["事项编号", "服务对象", "服务类别", "响应时限", "受理人员", "完成时刻", "评价结果", "事项状态"]
const actions = ["受理事项", "确认办结", "退回事项"]

const rows = ref<Row[]>([])
const total = ref(0)
// 统计值只来自后端 /stats，页面不再自行按日期计算，保证与列表、动作拦截同一口径。
const stats = ref<Stat[]>([
  { label: '待受理事项', value: 0 },
  { label: '办理中事项', value: 0 },
  { label: '超时未办结', value: 0 },
])
const emptyNote = ref('')
const errorMessage = ref('')
const filters = ref<Record<string, string>>({})
const filterFields = columns.slice(0, 3)

const hasFilter = computed(() => Object.values(filters.value).some((value) => value.trim() !== ''))
// 空结果说明与后端用同一把尺子：区分“没有任何数据”和“筛选无命中”。
const emptyHint = computed(() => {
  if (emptyNote.value) return emptyNote.value
  return hasFilter.value ? '当前筛选条件下没有匹配的服务事项，可重置条件后再看' : '暂无服务保障数据，可先登记服务事项'
})

function resetFilters() {
  filters.value = {}
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  errorMessage.value = '服务事项登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = await response.json().catch(() => null) as { ok?: boolean; message?: string } | null
    // 业务拦截（如超期不许受理）由后端按统一口径给出说明，页面原样展示即可。
    if (!response.ok || payload?.ok === false) {
      errorMessage.value = payload?.message || '服务保障动作未生效，请稍后重试'
      return
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '服务保障操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams(filters.value as Record<string, string>).toString()
  const suffix = query ? `?${query}` : ''
  try {
    const [listResponse, statsResponse] = await Promise.all([
      request(`${ENDPOINT}${suffix}`),
      request(`${ENDPOINT}/stats${suffix}`),
    ])
    if (!listResponse.ok) {
      throw new Error('服务事项列表读取失败')
    }
    const payload = await listResponse.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    if (statsResponse.ok) {
      const statsPayload = await statsResponse.json()
      if (Array.isArray(statsPayload.stats)) {
        stats.value = statsPayload.stats
      }
      emptyNote.value = statsPayload.note ?? ''
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '服务保障列表读取失败'
  }
}

onMounted(reload)
</script>

<style scoped>
.row-overdue {
  background: #fef3f2;
}

.tag-overdue {
  color: #b42318;
  font-weight: 600;
}

.tag-ok {
  color: #067647;
}

.limit-note {
  color: var(--muted);
}

.stat-alert {
  color: #b42318;
}
</style>
