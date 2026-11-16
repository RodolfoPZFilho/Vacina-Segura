<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { EChartsOption } from 'echarts'
import type { FaixaSegura } from '../types'

const props = defineProps<{
  temperatura: number | null
  faixa: FaixaSegura
}>()

const MIN = 0
const MAX = 16

const opcao = computed<EChartsOption>(() => {
  const { temp_min, temp_max } = props.faixa
  const frac = (v: number) => (v - MIN) / (MAX - MIN)
  return {
    series: [
      {
        type: 'gauge',
        min: MIN,
        max: MAX,
        startAngle: 210,
        endAngle: -30,
        splitNumber: 8,
        radius: '95%',
        center: ['50%', '58%'],
        axisLine: {
          lineStyle: {
            width: 16,
            color: [
              [frac(temp_min), '#1d4ed8'],
              [frac(temp_max), '#15803d'],
              [1, '#c2410c'],
            ],
          },
        },
        pointer: { length: '62%', width: 5, itemStyle: { color: '#14232e' } },
        anchor: { show: true, size: 12, itemStyle: { color: '#14232e' } },
        axisTick: { distance: -16, length: 5, lineStyle: { color: '#fff', width: 1 } },
        splitLine: { distance: -16, length: 16, lineStyle: { color: '#fff', width: 2 } },
        axisLabel: { distance: 22, color: '#5c6f7c', fontSize: 11 },
        title: { show: false },
        detail: {
          valueAnimation: true,
          offsetCenter: [0, '42%'],
          formatter: (v: number) => (props.temperatura === null ? '--' : `${v.toFixed(1).replace('.', ',')} °C`),
          fontSize: 30,
          fontWeight: 700,
          fontFamily: 'JetBrains Mono, monospace',
          color: '#14232e',
        },
        data: [{ value: props.temperatura ?? MIN }],
      },
    ],
  }
})
</script>

<template>
  <VChart class="indicador" :option="opcao" autoresize />
</template>

<style scoped>
.indicador {
  width: 100%;
  height: 260px;
}
</style>
