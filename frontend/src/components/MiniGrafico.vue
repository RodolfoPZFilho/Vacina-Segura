<script setup lang="ts">
import { computed } from 'vue'
import VChart from '../echarts'

const props = withDefaults(
  defineProps<{ pontos: number[][]; cor?: string; altura?: number; min?: number; max?: number; faixa?: [number, number] }>(),
  { cor: '#0e7490', altura: 90 },
)

const opcao = computed(() => ({
  animation: false,
  grid: { left: 34, right: 8, top: 8, bottom: 18 },
  tooltip: { trigger: 'axis', valueFormatter: (v: number) => v?.toFixed?.(2) },
  xAxis: { type: 'time', axisLabel: { fontSize: 9, hideOverlap: true }, splitLine: { show: false } },
  yAxis: {
    type: 'value',
    scale: true,
    min: props.min,
    max: props.max,
    axisLabel: { fontSize: 9 },
    splitLine: { lineStyle: { color: '#eef2f5' } },
  },
  series: [
    {
      type: 'line',
      data: props.pontos,
      showSymbol: false,
      lineStyle: { width: 2, color: props.cor },
      areaStyle: { color: props.cor, opacity: 0.08 },
      markArea: props.faixa
        ? { silent: true, itemStyle: { color: 'rgba(22,163,74,0.07)' }, data: [[{ yAxis: props.faixa[0] }, { yAxis: props.faixa[1] }]] }
        : undefined,
    },
  ],
}))
</script>

<template>
  <VChart :option="opcao" autoresize :style="{ height: `${altura}px`, width: '100%' }" />
</template>
