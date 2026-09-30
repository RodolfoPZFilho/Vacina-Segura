<script setup lang="ts">
import { computed } from 'vue'
import VChart from 'vue-echarts'
import type { EChartsOption } from 'echarts'
import type { FaixaSegura, PontoHistorico } from '../types'

const props = defineProps<{
  pontos: PontoHistorico[]
  faixa: FaixaSegura
}>()

const opcao = computed<EChartsOption>(() => {
  const { temp_min, temp_max } = props.faixa
  const temperaturas = props.pontos.map((p) => [p.horario, p.temperatura])
  const umidades = props.pontos.map((p) => [p.horario, p.umidade])

  return {
    animation: false,
    grid: { left: 48, right: 52, top: 40, bottom: 36 },
    legend: { top: 0, left: 'center', itemWidth: 14, textStyle: { color: '#5c6f7c' } },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (v) => (typeof v === 'number' ? v.toFixed(1) : '--'),
    },
    xAxis: {
      type: 'time',
      axisLabel: { color: '#5c6f7c', hideOverlap: true },
      axisLine: { lineStyle: { color: '#dde5ea' } },
    },
    yAxis: [
      {
        type: 'value',
        name: '°C',
        min: (v) => Math.min(Math.floor(v.min) - 1, temp_min - 1),
        max: (v) => Math.max(Math.ceil(v.max) + 1, temp_max + 1),
        axisLabel: { color: '#5c6f7c' },
        splitLine: { lineStyle: { color: '#eef2f5' } },
      },
      {
        type: 'value',
        name: '%',
        min: 0,
        max: 100,
        axisLabel: { color: '#9aabb6' },
        splitLine: { show: false },
      },
    ],
    series: [
      {
        name: 'Temperatura',
        type: 'line',
        data: temperaturas,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 2.5, color: '#0e7490' },
        itemStyle: { color: '#0e7490' },
        markArea: {
          silent: true,
          itemStyle: { color: 'rgba(21, 128, 61, 0.08)' },
          data: [[{ yAxis: temp_min, name: 'Faixa segura' }, { yAxis: temp_max }]],
          label: { position: 'insideTopLeft', color: '#15803d', fontSize: 11 },
        },
        markLine: {
          silent: true,
          symbol: 'none',
          lineStyle: { type: 'dashed', color: '#15803d' },
          label: { formatter: '{c} °C', color: '#15803d', fontSize: 11 },
          data: [{ yAxis: temp_min }, { yAxis: temp_max }],
        },
      },
      {
        name: 'Umidade',
        type: 'line',
        yAxisIndex: 1,
        data: umidades,
        showSymbol: false,
        smooth: true,
        lineStyle: { width: 1.5, type: 'dashed', color: '#9aabb6' },
        itemStyle: { color: '#9aabb6' },
      },
    ],
  }
})
</script>

<template>
  <div class="grafico-wrap">
    <VChart v-if="pontos.length" class="grafico" :option="opcao" autoresize />
    <p v-else class="vazio">Nenhuma leitura neste período.</p>
  </div>
</template>

<style scoped>
.grafico-wrap {
  width: 100%;
  min-height: 320px;
}
.grafico {
  width: 100%;
  height: 320px;
}
.vazio {
  display: grid;
  place-items: center;
  height: 320px;
  margin: 0;
  color: var(--texto-suave);
}
</style>
