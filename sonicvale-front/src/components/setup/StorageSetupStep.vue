<template>
  <div class="storage-step">
    <section class="storage-intro">
      <el-icon><FolderOpened /></el-icon>
      <div>
        <strong>素材和导出文件保存在哪里</strong>
        <p>这里会保存项目音频、字幕、导出文件和制作清单。默认可以使用 Auralis 本地目录，也可以改到外置硬盘或指定项目目录。</p>
      </div>
    </section>

    <el-form label-position="top" class="storage-form">
      <el-form-item label="默认项目保存位置">
        <el-input v-model="path" placeholder="留空则使用 Auralis 默认本地目录">
          <template #append>
            <el-button @click="pickDirectory">选择目录</el-button>
          </template>
        </el-input>
      </el-form-item>
    </el-form>

    <div class="storage-actions">
      <el-button @click="useDefault">使用默认位置</el-button>
      <el-button type="primary" @click="save">保存位置</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { FolderOpened } from '@element-plus/icons-vue'
import { getDefaultStoragePath, setDefaultStoragePath } from '../../api/setup'

const emit = defineEmits(['saved'])
const path = ref(getDefaultStoragePath())
const native = window.native

function useDefault() {
  path.value = ''
  setDefaultStoragePath('')
  ElMessage.success('已使用 Auralis 默认本地目录')
  emit('saved', '')
}

async function pickDirectory() {
  if (!native?.selectDir && !native?.pickDirectory) {
    ElMessage.info('当前环境不支持系统目录选择，请手动输入路径')
    return
  }
  const selected = native.selectDir ? await native.selectDir() : await native.pickDirectory({ title: '选择项目保存位置' })
  if (selected) path.value = selected
}

function save() {
  setDefaultStoragePath(path.value)
  ElMessage.success(path.value ? '默认保存位置已设置' : '已使用 Auralis 默认本地目录')
  emit('saved', path.value)
}
</script>

<style scoped>
.storage-step {
  display: grid;
  gap: 18px;
  max-width: 820px;
}

.storage-intro {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  background: var(--el-fill-color-lighter);
}

.storage-intro .el-icon {
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--el-color-primary) 12%, transparent);
  color: var(--el-color-primary);
}

.storage-intro strong,
.storage-intro p {
  display: block;
  margin: 0;
}

.storage-intro p {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  line-height: 1.65;
}

.storage-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
</style>
