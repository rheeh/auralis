<template>
  <nav class="production-steps" aria-label="制作步骤">
    <button v-for="(step,index) in steps" :key="step.id" :disabled="step.disabled" :aria-current="modelValue===step.id?'step':undefined" :aria-pressed="modelValue===step.id" :class="{active:modelValue===step.id}" @click="$emit('update:modelValue',step.id)"><span>{{ String(index+1).padStart(2,'0') }}</span>{{ step.label }}</button>
  </nav>
</template>
<script setup>
defineProps({steps:{type:Array,required:true},modelValue:String})
defineEmits(['update:modelValue'])
</script>
<style scoped>
.production-steps{display:flex;gap:4px;overflow-x:auto;border-bottom:1px solid var(--el-border-color,#dedbd3);padding:4px}.production-steps button{display:flex;align-items:center;justify-content:center;gap:8px;flex:1;min-width:max-content;background:transparent;border:0;border-radius:8px;padding:12px 16px;font:inherit;color:inherit;cursor:pointer}.production-steps button span{font-size:10px;opacity:.65}.production-steps button.active{background:var(--el-fill-color,#eeeae2);color:var(--el-color-primary,#a56337);font-weight:600}.production-steps button:disabled{opacity:.4;cursor:default}.production-steps button:focus-visible{outline:2px solid var(--el-color-primary,#a56337);outline-offset:-2px}
</style>
