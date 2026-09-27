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
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>事项编号</span>
        <input v-model="filters.keyword" placeholder="按事项编号检索" />
      </label>
      <label class="filter-item">
        <span>事项状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>超期状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>
            <span
              class="overdue-tag"
              :class="{ 'is-overdue': row.overdue }"
              :title="String(row['超期说明'] ?? '')"
            >
              {{ row['超期状态'] ?? '—' }}
            </span>
          </td>
          <td class="row-actions">
            <button
              v-for="action in rowActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!rowActions(row).length" class="muted-text">已办结归档</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">{{ emptyNote }}</td>
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
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | boolean | string[] | null>

const ENDPOINT = '/api/service'
const columns = ["事项编号", "服务对象", "服务类别", "响应时限", "受理人员", "完成时刻", "评价结果", "事项状态"]
const statuses = ["待受理", "办理中", "已办结", "已退回"]
const STAT_LABELS = ["待受理事项", "办理中事项", "超时未办结"]
const DEFAULT_EMPTY_NOTE = '暂无服务保障数据，可先登记服务事项'

const rows = ref<Row[]>([])
const total = ref(0)
const stats = ref(STAT_LABELS.map((label) => ({ label, value: 0 })))
const errorMessage = ref('')
const emptyNote = ref(DEFAULT_EMPTY_NOTE)
const filters = ref({ keyword: '', status: '' })

function rowActions(row: Row): string[] {
  const available = row['可执行动作']
  return Array.isArray(available) ? available : []
}

function resetFilters() {
  filters.value = { keyword: '', status: '' }
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
      body: JSON.stringify({ values: { action } }),
    })
    const payload = await response.json()
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message ?? '服务保障动作未生效，请稍后重试')
    }
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '服务保障操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.value.keyword) query.set('keyword', filters.value.keyword)
  if (filters.value.status) query.set('status', filters.value.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('服务事项列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
    // 统计汇总与列表同一次响应、同一份口径，超期条数与事项状态不会再对不上
    const summary = payload.summary ?? {}
    stats.value = STAT_LABELS.map((label) => ({ label, value: summary[label] ?? 0 }))
    emptyNote.value = payload.note ?? DEFAULT_EMPTY_NOTE
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '服务保障列表读取失败'
  }
}

onMounted(reload)
</script>
