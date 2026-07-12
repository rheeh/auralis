<template>
  <div class="board-page">
    <header class="board-header">
      <div>
        <p class="eyebrow">角色</p>
        <h1>角色声线板</h1>
      </div>
      <el-select v-model="projectId" filterable placeholder="选择项目" class="project-select" @change="loadRoles">
        <el-option v-for="project in projects" :key="project.id" :label="project.name" :value="project.id" />
      </el-select>
    </header>

    <section v-if="voiceFilter === 'missing_voice'" class="filter-strip">
      <span>正在筛选未绑定音色的角色</span>
      <el-button size="small" @click="clearFilter">查看全部</el-button>
    </section>

    <el-table :data="displayedRoles" border height="calc(100vh - 232px)">
      <el-table-column prop="name" label="角色" min-width="160" />
      <el-table-column prop="default_voice_id" label="绑定音色" min-width="120">
        <template #default="{ row }">
          <el-tag :type="row.default_voice_id ? 'success' : 'info'" effect="plain">
            {{ row.default_voice_id || '未绑定' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="角色级别" min-width="150">
        <template #default="{ row }">
          <el-select v-model="row.role_importance" size="small" @change="saveRoleTTS(row)">
            <el-option label="主角" value="lead" />
            <el-option label="关键角色" value="key" />
            <el-option label="普通配角" value="supporting" />
            <el-option label="不重要角色" value="background" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="TTS 路由" min-width="150">
        <template #default="{ row }">
          <el-select v-model="row.tts_route" size="small" @change="saveRoleTTS(row)">
            <el-option label="自动" value="auto" />
            <el-option label="Edge 免费" value="edge" />
            <el-option label="云端/克隆" value="cloud" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="Edge 音色" min-width="220">
        <template #default="{ row }">
          <el-input
            v-model="row.edge_voice"
            size="small"
            placeholder="zh-CN-XiaoxiaoNeural"
            @change="saveRoleTTS(row)"
          />
        </template>
      </el-table-column>
      <el-table-column prop="created_at" label="创建时间" min-width="180" />
      <el-table-column label="操作" width="130" fixed="right">
        <template #default="{ row }">
          <el-button text type="primary" @click="$router.push(`/projects/${projectId}/dubbing`)">编辑台词</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { fetchProjects } from '../api/project'
import { getRolesByProject, updateRole } from '../api/role'

const projects = ref([])
const roles = ref([])
const projectId = ref(null)
const route = useRoute()
const router = useRouter()
const voiceFilter = ref('')

const displayedRoles = computed(() => {
  if (voiceFilter.value === 'missing_voice') {
    return roles.value.filter((role) => !role.default_voice_id)
  }
  return roles.value
})

onMounted(async () => {
  projects.value = await fetchProjects()
  if (projects.value.length) {
    projectId.value = selectProjectFromQuery() || projects.value[0].id
    await loadRoles()
  }
})

watch(
  () => route.query.project_id,
  async () => {
    const selected = selectProjectFromQuery()
    if (selected && selected !== projectId.value) {
      projectId.value = selected
      await loadRoles()
    }
    voiceFilter.value = String(route.query.filter || '')
  }
)

watch(
  () => route.query.filter,
  (value) => {
    voiceFilter.value = String(value || '')
  },
  { immediate: true }
)

function selectProjectFromQuery() {
  const id = Number(route.query.project_id)
  if (!id) return null
  return projects.value.some((project) => project.id === id) ? id : null
}

async function loadRoles() {
  if (!projectId.value) return
  const response = await getRolesByProject(projectId.value)
  roles.value = response.code === 200
    ? response.data.map(role => ({
      role_importance: 'supporting',
      tts_route: 'auto',
      edge_voice: '',
      ...role
    }))
    : []
}

function clearFilter() {
  router.push(projectId.value ? `/roles?project_id=${projectId.value}` : '/roles')
}

async function saveRoleTTS(row) {
  try {
    await updateRole(row.id, {
      name: row.name,
      project_id: row.project_id,
      default_voice_id: row.default_voice_id,
      role_importance: row.role_importance || 'supporting',
      tts_route: row.tts_route || 'auto',
      edge_voice: row.edge_voice || null
    })
    ElMessage.success('角色 TTS 策略已更新')
  } catch (e) {
    ElMessage.error('角色 TTS 策略更新失败')
  }
}
</script>

<style scoped>
.board-page {
  min-height: 100%;
}

.board-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.board-header h1 {
  margin: 0;
  font-size: 24px;
  letter-spacing: 0;
}

.eyebrow {
  margin: 0 0 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
  text-transform: uppercase;
}

.project-select {
  width: 280px;
}

.filter-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid color-mix(in srgb, var(--el-color-warning) 30%, var(--el-border-color-light));
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-color-warning) 9%, var(--el-bg-color));
}

.filter-strip span {
  color: var(--el-text-color-regular);
  font-size: 14px;
}
</style>
