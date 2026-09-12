<template>
  <section class="scene-performance" aria-label="整场表演设计">
    <template v-if="plan">
      <header><strong>整场表演设计</strong><small>{{ cue ? '当前句沿用本场设计' : '随台本一起确认；可通过制作助手反馈修改' }}</small></header>
      <p><b>本场任务</b>{{ plan.purpose }}</p>
      <p><b>共同基调</b>{{ plan.baseline }}</p>
      <p><b>接话节奏</b>{{ plan.pace }}</p>
      <details><summary>人物意图与稳定声线</summary><div v-for="person in plan.characters || []" :key="person.speaker" class="person"><strong>{{ person.speaker }}</strong><span>{{ person.objective }}</span><small v-if="person.relationship">关系：{{ person.relationship }}</small><small>表达：{{ person.baseline }}</small></div></details>
      <details :open="!cue"><summary>表演推进</summary><ol><li v-for="beat in plan.beats || []" :key="beat.id" :class="{current: cue?.beatId === beat.id}"><strong>{{ beat.purpose }}</strong><span>{{ beat.delivery }}</span><small v-if="cue?.beatId === beat.id">当前阶段</small></li></ol></details>
      <div v-if="cue" class="current-cue"><strong>本句意图：{{ cue.intent }}</strong><p v-if="cue.delivery">局部表达：{{ cue.delivery }}</p><p v-if="cue.turningPoint">转折依据：{{ cue.evidence }}<span v-if="cue.turning_point_verified === false">（依据未通过核对，不放行情绪突增）</span></p></div>
    </template>
    <p v-else class="unavailable">{{ message || '此版本尚无整场表演设计，可继续按现有台本制作。' }}</p>
  </section>
</template>

<script setup>
defineProps({ plan: Object, cue: Object, message: String })
</script>

<style scoped>
.scene-performance{min-width:0;padding:14px;margin:8px 0 16px;border:1px solid var(--el-border-color);border-radius:9px;background:var(--el-fill-color-light);font-size:12px;line-height:1.7;overflow-wrap:anywhere}.scene-performance header{display:flex;flex-wrap:wrap;justify-content:space-between;gap:6px}.scene-performance header>strong{font-size:14px}.scene-performance small{color:var(--el-text-color-secondary)}.scene-performance p{margin:8px 0}.scene-performance b{display:inline-block;margin-right:10px}.scene-performance details{margin-top:10px}.scene-performance summary{cursor:pointer;font-weight:600}.person{display:grid;gap:3px;border-top:1px solid var(--el-border-color-lighter);padding:8px 0}.person>span,.person>small{display:block}.scene-performance ol{margin:8px 0;padding-left:22px}.scene-performance li{padding:5px 8px}.scene-performance li span,.scene-performance li small{display:block}.current{background:var(--el-color-primary-light-9);border-radius:6px}.current-cue{border-top:1px solid var(--el-border-color);padding-top:10px;margin-top:10px}.unavailable{color:var(--el-text-color-secondary)}
</style>
