<script setup>
const props = defineProps({
  centerY: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <div class="page-toolbar" :class="{ 'page-toolbar-center': props.centerY }">
    <div>
      <slot name="left" />
    </div>
    <div class="page-toolbar-right">
      <slot name="right" />
    </div>
  </div>
</template>
