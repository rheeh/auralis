<template><select :value="modelValue" :aria-label="label" @change="$emit('update:modelValue',$event.target.value)"><option value="before">台词前</option><option value="with">与台词同时</option><option value="after">台词后</option><option v-if="allowSceneStart" value="scene_start">本场景开头</option></select></template>
<script setup>
defineProps({modelValue:String,label:{type:String,default:'音效进入位置'},allowSceneStart:Boolean})
defineEmits(['update:modelValue'])
</script>
<style scoped>select{font:inherit;color:inherit;background:var(--el-bg-color,transparent);border:1px solid var(--el-border-color,#dcdfe6);border-radius:6px;padding:7px 10px;min-width:0;width:100%}</style>
