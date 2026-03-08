// Autoflow Analytics Dashboard JavaScript
// Handles data fetching and chart rendering

// Chart instances
let velocityChart = null;
let qualityChart = null;
let roiChart = null;
let agentChart = null;

// API base URL
const API_BASE = '/api';

// Initialize dashboard
document.addEventListener('DOMContentLoaded', () => {
    initializeDashboard();
});

async function initializeDashboard() {
    try {
        await Promise.all([
            loadVelocityMetrics(),
            loadQualityMetrics(),
            loadROIMetrics(),
            loadAgentPerformance()
        ]);
    } catch (error) {
        showError('Failed to load dashboard data: ' + error.message);
    }
}

async function refreshDashboard() {
    const btn = document.querySelector('.refresh-btn');
    btn.disabled = true;
    btn.textContent = '⏳ Loading...';

    try {
        await initializeDashboard();
    } catch (error) {
        showError('Failed to refresh dashboard: ' + error.message);
    } finally {
        btn.disabled = false;
        btn.textContent = '🔄 Refresh';
    }
}

function getPeriodDays() {
    return parseInt(document.getElementById('period-select').value);
}

function getHourlyRate() {
    return parseFloat(document.getElementById('hourly-rate').value) || 100;
}

async function fetchAPI(endpoint, params = {}) {
    const url = new URL(API_BASE + endpoint, window.location.origin);
    Object.keys(params).forEach(key => url.searchParams.append(key, params[key]));

    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`API error: ${response.status} ${response.statusText}`);
    }
    return response.json();
}

async function loadVelocityMetrics() {
    try {
        const periodDays = getPeriodDays();
        const data = await fetchAPI('/velocity', { period_days: periodDays });

        // Update metrics
        document.getElementById('velocity-completed').textContent = data.tasks_completed || 0;
        document.getElementById('velocity-rate').textContent = formatPercentage(data.completion_rate);
        document.getElementById('velocity-cycle').textContent = formatDuration(data.avg_cycle_time_seconds);
        document.getElementById('velocity-throughput').textContent = (data.throughput || 0).toFixed(2);

        // Update trend indicator
        const trendIcon = data.trend === 'improving' ? '📈' : data.trend === 'declining' ? '📉' : '➡️';

        // Render velocity chart
        renderVelocityChart(data);
    } catch (error) {
        console.error('Error loading velocity metrics:', error);
        document.getElementById('velocity-completed').textContent = 'N/A';
        document.getElementById('velocity-rate').textContent = 'N/A';
        document.getElementById('velocity-cycle').textContent = 'N/A';
        document.getElementById('velocity-throughput').textContent = 'N/A';
    }
}

async function loadQualityMetrics() {
    try {
        const periodDays = getPeriodDays();
        const data = await fetchAPI('/quality', { period_days: periodDays });

        // Update metrics
        document.getElementById('quality-pass-rate').textContent = formatPercentage(data.avg_test_pass_rate);
        document.getElementById('quality-approval').textContent = formatPercentage(data.avg_review_approval_rate);
        document.getElementById('quality-first-try').textContent = formatPercentage(data.avg_first_try_rate);
        document.getElementById('quality-score').textContent = (data.quality_score || 0).toFixed(1);

        // Render quality chart
        renderQualityChart(data);
    } catch (error) {
        console.error('Error loading quality metrics:', error);
        document.getElementById('quality-pass-rate').textContent = 'N/A';
        document.getElementById('quality-approval').textContent = 'N/A';
        document.getElementById('quality-first-try').textContent = 'N/A';
        document.getElementById('quality-score').textContent = 'N/A';
    }
}

async function loadROIMetrics() {
    try {
        const periodDays = getPeriodDays();
        const hourlyRate = getHourlyRate();
        const data = await fetchAPI('/roi', {
            period_days: periodDays,
            hourly_rate_usd: hourlyRate
        });

        // Update metrics
        document.getElementById('roi-time-saved').textContent = formatDuration(data.total_time_saved_seconds);
        document.getElementById('roi-cost-savings').textContent = formatCurrency(data.cost_savings_usd);
        document.getElementById('roi-percentage').textContent = formatPercentage(data.roi_percentage / 100);
        document.getElementById('roi-tasks').textContent = data.tasks_automated || 0;

        // Render ROI chart
        renderROIChart(data);
    } catch (error) {
        console.error('Error loading ROI metrics:', error);
        document.getElementById('roi-time-saved').textContent = 'N/A';
        document.getElementById('roi-cost-savings').textContent = 'N/A';
        document.getElementById('roi-percentage').textContent = 'N/A';
        document.getElementById('roi-tasks').textContent = 'N/A';
    }
}

async function loadAgentPerformance() {
    try {
        const data = await fetchAPI('/agents', { limit: 10 });

        // Render agent chart
        renderAgentChart(data);
    } catch (error) {
        console.error('Error loading agent performance:', error);
    }
}

function renderVelocityChart(data) {
    const ctx = document.getElementById('velocity-chart').getContext('2d');

    if (velocityChart) {
        velocityChart.destroy();
    }

    velocityChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: ['Tasks Completed', 'Tasks Started', 'Forecasted'],
            datasets: [{
                label: 'Task Counts',
                data: [
                    data.tasks_completed || 0,
                    data.tasks_started || 0,
                    data.forecasted_completion || 0
                ],
                borderColor: '#667eea',
                backgroundColor: 'rgba(102, 126, 234, 0.1)',
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    }
                }
            }
        }
    });
}

function renderQualityChart(data) {
    const ctx = document.getElementById('quality-chart').getContext('2d');

    if (qualityChart) {
        qualityChart.destroy();
    }

    qualityChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Test Pass Rate', 'Review Approval', 'First Try Rate'],
            datasets: [{
                label: 'Quality Metrics',
                data: [
                    (data.avg_test_pass_rate || 0) * 100,
                    (data.avg_review_approval_rate || 0) * 100,
                    (data.avg_first_try_rate || 0) * 100
                ],
                backgroundColor: [
                    'rgba(72, 187, 120, 0.8)',
                    'rgba(102, 126, 234, 0.8)',
                    'rgba(237, 137, 54, 0.8)'
                ],
                borderColor: [
                    'rgba(72, 187, 120, 1)',
                    'rgba(102, 126, 234, 1)',
                    'rgba(237, 137, 54, 1)'
                ],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: false
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    max: 100,
                    ticks: {
                        callback: value => value + '%'
                    }
                }
            }
        }
    });
}

function renderROIChart(data) {
    const ctx = document.getElementById('roi-chart').getContext('2d');

    if (roiChart) {
        roiChart.destroy();
    }

    roiChart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: ['Time Saved', 'Time Spent'],
            datasets: [{
                data: [
                    data.total_time_saved_seconds || 0,
                    data.total_time_invested_seconds || 0
                ],
                backgroundColor: [
                    'rgba(72, 187, 120, 0.8)',
                    'rgba(203, 213, 224, 0.8)'
                ],
                borderColor: [
                    'rgba(72, 187, 120, 1)',
                    'rgba(203, 213, 224, 1)'
                ],
                borderWidth: 2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}

function renderAgentChart(data) {
    const ctx = document.getElementById('agent-chart').getContext('2d');

    if (agentChart) {
        agentChart.destroy();
    }

    // Group executions by agent
    const agentStats = {};
    data.recent_executions.forEach(exec => {
        if (!agentStats[exec.agent_name]) {
            agentStats[exec.agent_name] = {
                total: 0,
                successful: 0,
                failed: 0
            };
        }
        agentStats[exec.agent_name].total++;
        if (exec.status === 'completed') {
            agentStats[exec.agent_name].successful++;
        } else {
            agentStats[exec.agent_name].failed++;
        }
    });

    const labels = Object.keys(agentStats);
    const successData = labels.map(name => agentStats[name].successful);
    const failedData = labels.map(name => agentStats[name].failed);

    agentChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels.length > 0 ? labels : ['No Data'],
            datasets: [
                {
                    label: 'Successful',
                    data: successData.length > 0 ? successData : [0],
                    backgroundColor: 'rgba(72, 187, 120, 0.8)',
                    borderColor: 'rgba(72, 187, 120, 1)',
                    borderWidth: 2
                },
                {
                    label: 'Failed',
                    data: failedData.length > 0 ? failedData : [0],
                    backgroundColor: 'rgba(245, 101, 101, 0.8)',
                    borderColor: 'rgba(245, 101, 101, 1)',
                    borderWidth: 2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top'
                }
            },
            scales: {
                x: {
                    stacked: true,
                    ticks: {
                        maxRotation: 45,
                        minRotation: 45
                    }
                },
                y: {
                    stacked: true,
                    beginAtZero: true,
                    ticks: {
                        precision: 0
                    }
                }
            }
        }
    });
}

// Utility functions
function formatPercentage(value) {
    if (value === null || value === undefined || isNaN(value)) {
        return 'N/A';
    }
    return (value * 100).toFixed(1) + '%';
}

function formatDuration(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds)) {
        return 'N/A';
    }

    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);

    if (hours > 0) {
        return `${hours}h ${minutes}m`;
    } else if (minutes > 0) {
        return `${minutes}m`;
    } else {
        return `${Math.floor(seconds)}s`;
    }
}

function formatCurrency(value) {
    if (value === null || value === undefined || isNaN(value)) {
        return 'N/A';
    }
    return '$' + value.toFixed(2);
}

function showError(message) {
    const container = document.getElementById('error-container');
    container.innerHTML = `<div class="error">⚠️ ${message}</div>`;
    setTimeout(() => {
        container.innerHTML = '';
    }, 5000);
}

// Auto-refresh every 5 minutes
setInterval(refreshDashboard, 5 * 60 * 1000);
