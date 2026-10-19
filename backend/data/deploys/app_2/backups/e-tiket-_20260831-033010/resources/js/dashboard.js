// ===== E-Tiket Report: Dashboard Charts (ECharts) =====

import * as echarts from 'echarts';

const dataEl = document.getElementById('dashboard-data');
if (dataEl) {
    const data = JSON.parse(dataEl.textContent);

    // Trend Chart (Line)
    const trendChart = echarts.init(document.getElementById('trendChart'));
    trendChart.setOption({
        tooltip: {
            trigger: 'axis',
            backgroundColor: 'rgba(255,255,255,0.95)',
            borderColor: '#e5e7eb',
            textStyle: { color: '#374151' },
            axisPointer: { lineStyle: { color: '#e5e7eb' } },
        },
        legend: { data: ['Tiket Masuk', 'Tiket Selesai'], bottom: 0, textStyle: { color: '#6b7280' } },
        grid: { left: '3%', right: '4%', bottom: '15%', top: '5%', containLabel: true },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: data.trendLabels,
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280' },
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: '#f3f4f6' } },
            axisLabel: { color: '#6b7280' },
        },
        series: [
            {
                name: 'Tiket Masuk',
                type: 'line',
                smooth: true,
                data: data.trendMasuk,
                itemStyle: { color: '#047857' },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 0,
                        y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(4,120,87,0.2)' },
                            { offset: 1, color: 'rgba(4,120,87,0.02)' },
                        ],
                    },
                },
                lineStyle: { width: 3 },
            },
            {
                name: 'Tiket Selesai',
                type: 'line',
                smooth: true,
                data: data.trendSelesai,
                itemStyle: { color: '#10b981' },
                areaStyle: {
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 0,
                        y2: 1,
                        colorStops: [
                            { offset: 0, color: 'rgba(16,185,129,0.2)' },
                            { offset: 1, color: 'rgba(16,185,129,0.02)' },
                        ],
                    },
                },
                lineStyle: { width: 3 },
            },
        ],
    });

    // Status Chart (Pie)
    const statusChart = echarts.init(document.getElementById('statusChart'));
    statusChart.setOption({
        tooltip: {
            trigger: 'item',
            formatter: '{b}: {c} ({d}%)',
            backgroundColor: 'rgba(255,255,255,0.95)',
            borderColor: '#e5e7eb',
            textStyle: { color: '#374151' },
        },
        series: [
            {
                type: 'pie',
                radius: ['45%', '70%'],
                avoidLabelOverlap: false,
                itemStyle: { borderRadius: 8, borderColor: '#fff', borderWidth: 2 },
                label: { show: false },
                emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
                data: data.statusDistribution,
            },
        ],
    });

    // Category Chart (Bar)
    const categoryChart = echarts.init(document.getElementById('categoryChart'));
    categoryChart.setOption({
        tooltip: {
            trigger: 'axis',
            axisPointer: { type: 'shadow' },
            backgroundColor: 'rgba(255,255,255,0.95)',
            borderColor: '#e5e7eb',
            textStyle: { color: '#374151' },
        },
        grid: { left: '3%', right: '8%', bottom: '3%', top: '3%', containLabel: true },
        xAxis: {
            type: 'value',
            minInterval: 1,
            axisLine: { show: false },
            axisTick: { show: false },
            splitLine: { lineStyle: { color: '#f3f4f6' } },
            axisLabel: { color: '#6b7280' },
        },
        yAxis: {
            type: 'category',
            data: data.categoryNames,
            axisLine: { lineStyle: { color: '#e5e7eb' } },
            axisLabel: { color: '#6b7280' },
        },
        series: [
            {
                type: 'bar',
                data: data.categoryCounts,
                itemStyle: {
                    color: {
                        type: 'linear',
                        x: 0,
                        y: 0,
                        x2: 1,
                        y2: 0,
                        colorStops: [
                            { offset: 0, color: '#34d399' },
                            { offset: 1, color: '#047857' },
                        ],
                    },
                    borderRadius: [0, 4, 4, 0],
                },
                barWidth: '60%',
                label: { show: true, position: 'right', color: '#6b7280', fontSize: 11 },
            },
        ],
    });

    // Responsive resize
    window.addEventListener('resize', () => {
        trendChart.resize();
        statusChart.resize();
        categoryChart.resize();
    });
}

// Animasi progress bar beban kerja teknisi
setTimeout(() => {
    document.querySelectorAll('[data-width]').forEach((bar) => {
        bar.style.width = bar.getAttribute('data-width');
    });
}, 500);
