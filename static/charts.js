/**
 * Timeseries Charts JavaScript
 *
 * Handles chart rendering, data fetching, and user interactions for the
 * timeseries charting page.
 */

// State management
let availableTimeseries = [];
let selectedTimeseries = new Set();
let autoRefreshEnabled = false;
let autoRefreshInterval = null;
let autoRefreshRate = 30000; // milliseconds
let smoothingEnabled = false;
let maxDatapoints = 10000; // maximum datapoints per chart

// Color management (shared with dashboard.js via localStorage)
function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : null;
}

function applyColors(foregroundColor, backgroundColor) {
    const fgRgb = hexToRgb(foregroundColor);
    const bgRgb = hexToRgb(backgroundColor);

    if (!fgRgb || !bgRgb) return;

    // Calculate darker shade for foreground (80% brightness for dimmed text)
    const dimR = Math.floor(fgRgb.r * 0.8);
    const dimG = Math.floor(fgRgb.g * 0.8);
    const dimB = Math.floor(fgRgb.b * 0.8);

    // Calculate darker shade for backgrounds (reduce brightness by ~92%)
    const darkR = Math.floor(fgRgb.r * 0.08);
    const darkG = Math.floor(fgRgb.g * 0.08);
    const darkB = Math.floor(fgRgb.b * 0.08);

    // Set CSS custom properties for foreground
    document.documentElement.style.setProperty('--theme-primary', foregroundColor);
    document.documentElement.style.setProperty('--theme-primary-rgb', `${fgRgb.r}, ${fgRgb.g}, ${fgRgb.b}`);
    document.documentElement.style.setProperty('--theme-primary-dim', `rgb(${dimR}, ${dimG}, ${dimB})`);
    document.documentElement.style.setProperty('--theme-bg-dark', `rgba(${darkR}, ${darkG}, ${darkB}, 0.9)`);
    document.documentElement.style.setProperty('--theme-bg-medium', `rgba(${darkR}, ${darkG}, ${darkB}, 0.5)`);

    // Set foreground color for charts
    document.documentElement.style.setProperty('--foreground-color', foregroundColor);
    document.documentElement.style.setProperty('--foreground-color-rgb', `${fgRgb.r}, ${fgRgb.g}, ${fgRgb.b}`);

    // Set background color for matrix animation
    document.documentElement.style.setProperty('--background-color', backgroundColor);

    // Update matrix canvas color (function from dashboard.js)
    if (typeof updateMatrixColor === 'function') {
        updateMatrixColor(backgroundColor);
    } else {
        // Fallback if updateMatrixColor not available
        window.matrixColor = backgroundColor;
    }
}

// Initialize the charts page
async function initCharts() {
    // Apply saved colors first (same as dashboard)
    const foregroundColor = localStorage.getItem('foregroundColor') || '#00ff41';
    const backgroundColor = localStorage.getItem('backgroundColor') || '#00ff41';
    applyColors(foregroundColor, backgroundColor);

    // Start matrix animation (from dashboard.js)
    // The matrix drawing code is in dashboard.js, we just need to start the interval
    const matrixAnimationRate = parseInt(localStorage.getItem('matrixAnimationRate')) || 120;
    if (typeof draw === 'function') {
        // Clear any existing interval
        if (window.matrixInterval) {
            clearInterval(window.matrixInterval);
        }
        window.matrixInterval = setInterval(draw, matrixAnimationRate);
    }

    // Load available timeseries
    await loadAvailableTimeseries();

    // Set default time range (last 24 hours)
    setQuickRange(3600);

    // Load settings
    loadChartSettings();

    // Load smoothing preference
    const savedSmoothing = localStorage.getItem('smoothingEnabled');
    if (savedSmoothing !== null) {
        smoothingEnabled = savedSmoothing === 'true';
        const toggleSwitch = document.getElementById('smoothing-toggle');
        if (smoothingEnabled) {
            toggleSwitch.classList.add('active');
        }
    }

    // Enable auto-refresh by default (only on first visit)
    const savedAutoRefresh = localStorage.getItem('autoRefreshEnabled');
    if (savedAutoRefresh === null) {
        // First visit - enable auto-refresh by default
        autoRefreshEnabled = true;
        localStorage.setItem('autoRefreshEnabled', 'true');
    } else {
        autoRefreshEnabled = savedAutoRefresh === 'true';
    }

    // Update button state
    const autoRefreshButton = document.getElementById('auto-refresh-toggle');
    if (autoRefreshEnabled) {
        autoRefreshButton.textContent = 'AUTO-REFRESH: ON';
        autoRefreshButton.classList.add('active');
        autoRefreshInterval = setInterval(() => updateCharts(true), autoRefreshRate);
    }

    // Initial chart update
    await updateCharts();
}

// Load list of available timeseries
async function loadAvailableTimeseries() {
    try {
        const response = await fetch('/api/timeseries/list');
        availableTimeseries = await response.json();

        // Set up search input event listeners
        const searchInput = document.getElementById('timeseries-search');
        const searchResults = document.getElementById('search-results');

        searchInput.addEventListener('input', handleSearch);
        searchInput.addEventListener('focus', handleSearch);

        // Close search results when clicking outside
        document.addEventListener('click', (e) => {
            if (!e.target.closest('.search-container')) {
                searchResults.style.display = 'none';
            }
        });

        // Load saved selection from localStorage or select defaults
        const saved = localStorage.getItem('selectedTimeseries');
        if (saved) {
            selectedTimeseries = new Set(JSON.parse(saved));
        } else {
            // Select first series from each category by default
            const byCategory = {};
            availableTimeseries.forEach(ts => {
                if (!byCategory[ts.category]) {
                    byCategory[ts.category] = ts;
                }
            });
            Object.values(byCategory).forEach(ts => {
                selectedTimeseries.add(ts.id);
            });
        }

        // Render selected series pills
        renderSelectedSeries();

    } catch (error) {
        console.error('Error loading timeseries list:', error);
    }
}

// Handle search input
function handleSearch(e) {
    const query = e.target.value.toLowerCase().trim();
    const searchResults = document.getElementById('search-results');

    // Show all if empty query
    if (query === '') {
        renderSearchResults(availableTimeseries);
        return;
    }

    // Filter timeseries based on query
    const filtered = availableTimeseries.filter(ts => {
        // Search in name, category, tags, and description
        const searchText = [
            ts.name,
            ts.category,
            ...ts.tags,
            ts.description
        ].join(' ').toLowerCase();

        return searchText.includes(query);
    });

    renderSearchResults(filtered);
}

// Render search results dropdown
function renderSearchResults(results) {
    const searchResults = document.getElementById('search-results');
    searchResults.innerHTML = '';

    if (results.length === 0) {
        searchResults.innerHTML = '<div class="no-results">No timeseries found</div>';
        searchResults.style.display = 'block';
        return;
    }

    // Sort results by category for better organization
    results.sort((a, b) => {
        if (a.category !== b.category) {
            return a.category.localeCompare(b.category);
        }
        return a.name.localeCompare(b.name);
    });

    results.forEach(ts => {
        const item = document.createElement('div');
        item.className = 'search-result-item';

        // Disable if already selected
        const isSelected = selectedTimeseries.has(ts.id);
        if (isSelected) {
            item.classList.add('disabled');
        }

        item.innerHTML = `
            <div class="result-name">${ts.name}</div>
            <div class="result-meta">
                <span class="result-category">${ts.category}</span>
                <span class="result-unit">${ts.units}</span>
                ${ts.tags.length > 0 ? `<span class="result-tags">${ts.tags.join(', ')}</span>` : ''}
            </div>
            ${ts.description ? `<div class="result-description">${ts.description}</div>` : ''}
        `;

        if (!isSelected) {
            item.addEventListener('click', () => addTimeseries(ts.id));
        }

        searchResults.appendChild(item);
    });

    searchResults.style.display = 'block';
}

// Add timeseries to selection
function addTimeseries(timeseriesId) {
    selectedTimeseries.add(timeseriesId);
    saveSelection();
    renderSelectedSeries();

    // Clear search and close dropdown
    const searchInput = document.getElementById('timeseries-search');
    const searchResults = document.getElementById('search-results');
    searchInput.value = '';
    searchResults.style.display = 'none';

    // Auto-update charts
    updateCharts();
}

// Remove timeseries from selection
function removeTimeseries(timeseriesId) {
    selectedTimeseries.delete(timeseriesId);
    saveSelection();
    renderSelectedSeries();

    // Auto-update charts
    updateCharts();
}

// Render selected series as pills
function renderSelectedSeries() {
    const container = document.getElementById('selected-series');
    container.innerHTML = '';

    if (selectedTimeseries.size === 0) {
        container.innerHTML = '<div class="no-series-selected" style="color: rgba(0, 255, 65, 0.5); font-style: italic;">No series selected. Use the search above to add series.</div>';
        return;
    }

    // Get selected timeseries objects
    const selected = availableTimeseries.filter(ts => selectedTimeseries.has(ts.id));

    // Sort by category and name
    selected.sort((a, b) => {
        if (a.category !== b.category) {
            return a.category.localeCompare(b.category);
        }
        return a.name.localeCompare(b.name);
    });

    selected.forEach(ts => {
        const pill = document.createElement('div');
        pill.className = 'series-pill';
        pill.innerHTML = `
            <span class="series-pill-name">${ts.name}</span>
            <span class="series-pill-unit">(${ts.units})</span>
            <span class="series-pill-remove" data-id="${ts.id}">&times;</span>
        `;

        pill.querySelector('.series-pill-remove').addEventListener('click', () => {
            removeTimeseries(ts.id);
        });

        container.appendChild(pill);
    });
}

// Save selection to localStorage
function saveSelection() {
    localStorage.setItem('selectedTimeseries', JSON.stringify([...selectedTimeseries]));
}

// Set quick time range
function setQuickRange(seconds) {
    const now = new Date();
    const start = new Date(now.getTime() - seconds * 1000);

    document.getElementById('end-time').value = formatDatetimeLocal(now);
    document.getElementById('start-time').value = formatDatetimeLocal(start);

    // Auto-update charts when quick range is selected
    updateCharts(true); // Pass true to indicate this is from a quick range/auto-refresh
}

// Format date for datetime-local input
function formatDatetimeLocal(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const hours = String(date.getHours()).padStart(2, '0');
    const minutes = String(date.getMinutes()).padStart(2, '0');
    return `${year}-${month}-${day}T${hours}:${minutes}`;
}

// Parse datetime-local input to Unix timestamp
function parseDatetimeLocal(datetimeString) {
    return new Date(datetimeString).getTime() / 1000;
}

// Update all charts
async function updateCharts(autoUpdate = false) {
    console.log('updateCharts called with autoUpdate =', autoUpdate);

    if (selectedTimeseries.size === 0) {
        document.getElementById('charts-container').innerHTML =
            '<div class="no-data-message">Please select at least one timeseries to display.</div>';
        return;
    }

    try {
        console.log('Updating charts...');

        // Get current time range from UI
        const startTime = parseDatetimeLocal(document.getElementById('start-time').value);
        let endTime = parseDatetimeLocal(document.getElementById('end-time').value);

        // If this is an auto-update (from auto-refresh or quick range), update end time to now
        if (autoUpdate) {
            console.log('Auto-update mode: setting end time to now');
            const now = new Date();
            document.getElementById('end-time').value = formatDatetimeLocal(now);
            endTime = Date.now() / 1000;
        }

        console.log('Fetching chart data from', new Date(startTime * 1000), 'to', new Date(endTime * 1000));

        // Fetch data for all selected timeseries
        const response = await fetch('/api/timeseries/data/batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                timeseries_ids: Array.from(selectedTimeseries),
                start: startTime,
                end: endTime,
                max_datapoints: maxDatapoints
            })
        });

        const timeseriesData = await response.json();
        console.log('Received timeseries data:', timeseriesData.map(ts => ({
            id: ts.id,
            dataPoints: ts.data.length
        })));

        // Group by units
        const groupedByUnits = {};
        timeseriesData.forEach(ts => {
            if (!groupedByUnits[ts.units]) {
                groupedByUnits[ts.units] = [];
            }
            groupedByUnits[ts.units].push(ts);
        });

        // Render charts
        renderCharts(groupedByUnits);
        console.log('Charts rendered');

    } catch (error) {
        console.error('Error fetching timeseries data:', error);
        document.getElementById('charts-container').innerHTML =
            '<div class="error-message">Error loading chart data. Please try again.</div>';
    }
}

// Render charts grouped by units
function renderCharts(groupedByUnits) {
    const container = document.getElementById('charts-container');

    // Save current scroll position
    const scrollY = window.scrollY;

    container.innerHTML = '';

    Object.entries(groupedByUnits).forEach(([units, seriesList], index) => {
        // Create chart container
        const chartDiv = document.createElement('div');
        chartDiv.className = 'chart-wrapper';
        chartDiv.id = `chart-${index}`;

        container.appendChild(chartDiv);

        // Prepare traces for Plotly
        const traces = seriesList.map((ts, traceIndex) => {
            // Convert timestamps to Date objects
            const x = ts.data.map(point => new Date(point.timestamp * 1000));
            const y = ts.data.map(point => point.value);

            return {
                x: x,
                y: y,
                mode: 'lines',
                name: ts.name,
                line: {
                    width: 2,
                    color: getColorForTrace(traceIndex),
                    shape: smoothingEnabled ? 'spline' : 'linear'
                }
            };
        });

        // Determine if we need to show the legend (only if multiple series)
        const showLegend = seriesList.length > 1;
        const rightMargin = showLegend ? 150 : 20;

        // Chart layout
        const layout = {
            title: {
                text: `${units} Timeseries`,
                font: { color: getComputedStyle(document.body).getPropertyValue('--foreground-color') || '#00ff41' }
            },
            paper_bgcolor: 'rgba(0, 0, 0, 0)',
            plot_bgcolor: 'rgba(0, 0, 0, 0.5)',
            xaxis: {
                title: 'Time',
                color: getComputedStyle(document.body).getPropertyValue('--foreground-color') || '#00ff41',
                gridcolor: 'rgba(0, 255, 65, 0.1)',
                fixedrange: false
            },
            yaxis: {
                title: units,
                color: getComputedStyle(document.body).getPropertyValue('--foreground-color') || '#00ff41',
                gridcolor: 'rgba(0, 255, 65, 0.1)',
                fixedrange: false
            },
            showlegend: showLegend,
            legend: {
                font: {
                    color: getComputedStyle(document.body).getPropertyValue('--foreground-color') || '#00ff41',
                    size: 10
                },
                bgcolor: 'rgba(0, 0, 0, 0.7)',
                bordercolor: getComputedStyle(document.body).getPropertyValue('--foreground-color') || '#00ff41',
                borderwidth: 1,
                x: 1.01,
                y: 1,
                xanchor: 'left',
                yanchor: 'top',
                orientation: 'v',
                tracegroupgap: 2
            },
            margin: { l: 60, r: rightMargin, t: 50, b: 50 },
            autosize: true
        };

        // Render chart
        Plotly.newPlot(chartDiv.id, traces, layout, {
            responsive: true,
            displayModeBar: true,
            modeBarButtonsToRemove: ['lasso2d', 'select2d'],
            displaylogo: false
        });

        // Add double-tap to fullscreen functionality
        addFullscreenToggle(chartDiv);
    });

    // Show message if no data
    if (Object.keys(groupedByUnits).length === 0) {
        container.innerHTML = '<div class="no-data-message">No data available for the selected time range.</div>';
    }

    // Restore scroll position after rendering
    requestAnimationFrame(() => {
        window.scrollTo(0, scrollY);
    });
}

// Get color for trace (cycle through colors)
function getColorForTrace(index) {
    const colors = [
        '#00ff41', // Matrix green
        '#ff6b6b', // Red
        '#4ecdc4', // Cyan
        '#ffe66d', // Yellow
        '#a8dadc', // Light blue
        '#f1c40f', // Gold
        '#e74c3c', // Bright red
        '#3498db', // Blue
        '#9b59b6', // Purple
        '#1abc9c'  // Turquoise
    ];
    return colors[index % colors.length];
}

// Toggle auto-refresh
function toggleAutoRefresh() {
    autoRefreshEnabled = !autoRefreshEnabled;

    const button = document.getElementById('auto-refresh-toggle');
    button.textContent = `AUTO-REFRESH: ${autoRefreshEnabled ? 'ON' : 'OFF'}`;
    button.classList.toggle('active', autoRefreshEnabled);

    // Save preference
    localStorage.setItem('autoRefreshEnabled', autoRefreshEnabled);

    if (autoRefreshEnabled) {
        // Start auto-refresh with auto-update flag
        autoRefreshInterval = setInterval(() => updateCharts(true), autoRefreshRate);
    } else {
        // Stop auto-refresh
        if (autoRefreshInterval) {
            clearInterval(autoRefreshInterval);
            autoRefreshInterval = null;
        }
    }
}

// Settings modal functions
function openSettingsModal() {
    document.getElementById('settings-modal').style.display = 'flex';

    // Load current settings from server
    fetch('/api/timeseries/settings')
        .then(response => response.json())
        .then(settings => {
            document.getElementById('sampling-rate').value = settings.sampling_rate_ms;
            document.getElementById('sampling-rate-input').value = settings.sampling_rate_ms;
        })
        .catch(error => console.error('Error loading settings:', error));

    // Load auto-refresh rate from localStorage
    const savedAutoRefreshRate = localStorage.getItem('autoRefreshRate') || '30';
    document.getElementById('auto-refresh-rate').value = savedAutoRefreshRate;
    document.getElementById('auto-refresh-rate-input').value = savedAutoRefreshRate;

    // Load max datapoints from localStorage
    const savedMaxDatapoints = localStorage.getItem('maxDatapoints') || '10000';
    document.getElementById('max-datapoints').value = savedMaxDatapoints;
    document.getElementById('max-datapoints-input').value = savedMaxDatapoints;
}

function closeSettingsModal() {
    document.getElementById('settings-modal').style.display = 'none';
}

async function saveSettings() {
    const samplingRate = parseInt(document.getElementById('sampling-rate-input').value);
    const autoRefreshRateSeconds = parseInt(document.getElementById('auto-refresh-rate-input').value);
    const maxDatapointsValue = parseInt(document.getElementById('max-datapoints-input').value);

    // Save sampling rate to server
    try {
        await fetch('/api/timeseries/settings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                sampling_rate_ms: samplingRate
            })
        });
    } catch (error) {
        console.error('Error saving settings:', error);
    }

    // Save auto-refresh rate to localStorage
    localStorage.setItem('autoRefreshRate', autoRefreshRateSeconds);
    autoRefreshRate = autoRefreshRateSeconds * 1000;

    // Save max datapoints to localStorage
    localStorage.setItem('maxDatapoints', maxDatapointsValue);
    maxDatapoints = maxDatapointsValue;

    // Update auto-refresh interval if it's running
    if (autoRefreshEnabled) {
        clearInterval(autoRefreshInterval);
        autoRefreshInterval = setInterval(() => updateCharts(true), autoRefreshRate);
    }

    closeSettingsModal();

    // Refresh charts to apply new max datapoints setting
    updateCharts();
}

function loadChartSettings() {
    const savedAutoRefreshRate = localStorage.getItem('autoRefreshRate') || '30';
    autoRefreshRate = parseInt(savedAutoRefreshRate) * 1000;

    const savedMaxDatapoints = localStorage.getItem('maxDatapoints') || '10000';
    maxDatapoints = parseInt(savedMaxDatapoints);
}

// Toggle smoothing
function toggleSmoothing() {
    const toggleSwitch = document.getElementById('smoothing-toggle');
    smoothingEnabled = !smoothingEnabled;

    if (smoothingEnabled) {
        toggleSwitch.classList.add('active');
    } else {
        toggleSwitch.classList.remove('active');
    }

    localStorage.setItem('smoothingEnabled', smoothingEnabled);
    updateCharts();
}

// Sync slider and text input values
function syncSliderAndInput(sliderId, inputId) {
    const slider = document.getElementById(sliderId);
    const input = document.getElementById(inputId);

    if (!slider || !input) return;

    // Sync slider to input
    slider.oninput = function() {
        input.value = this.value;
    };

    // Sync input to slider (with validation)
    input.oninput = function() {
        const min = parseInt(this.min);
        const max = parseInt(this.max);
        let val = parseInt(this.value);

        // Clamp value to min/max range
        if (!isNaN(val)) {
            if (val < min) val = min;
            if (val > max) val = max;
            this.value = val;
            slider.value = val;
        }
    };

    // Also handle blur event to ensure valid value on focus loss
    input.onblur = function() {
        const min = parseInt(this.min);
        const max = parseInt(this.max);
        let val = parseInt(this.value);

        if (isNaN(val) || val < min) {
            val = min;
        } else if (val > max) {
            val = max;
        }

        this.value = val;
        slider.value = val;
    };
}

// Update slider and input synchronization
document.addEventListener('DOMContentLoaded', () => {
    syncSliderAndInput('sampling-rate', 'sampling-rate-input');
    syncSliderAndInput('auto-refresh-rate', 'auto-refresh-rate-input');
    syncSliderAndInput('max-datapoints', 'max-datapoints-input');

    // Add event listeners to datetime inputs to auto-update charts when changed
    const startTimeInput = document.getElementById('start-time');
    const endTimeInput = document.getElementById('end-time');

    if (startTimeInput) {
        startTimeInput.addEventListener('change', () => {
            updateCharts();
        });
    }

    if (endTimeInput) {
        endTimeInput.addEventListener('change', () => {
            updateCharts();
        });
    }
});

// Add double-tap to fullscreen functionality for a chart
function addFullscreenToggle(chartDiv) {
    let lastTap = 0;

    // Handle double-tap for both mouse and touch
    const handleDoubleTap = (event) => {
        const currentTime = new Date().getTime();
        const tapLength = currentTime - lastTap;

        if (tapLength < 300 && tapLength > 0) {
            // Double tap detected
            event.preventDefault();
            toggleFullscreen(chartDiv);
            lastTap = 0;
        } else {
            lastTap = currentTime;
        }
    };

    // Add mouse double-click listener
    chartDiv.addEventListener('dblclick', () => {
        toggleFullscreen(chartDiv);
    });

    // Add touch double-tap listener for mobile
    chartDiv.addEventListener('touchend', handleDoubleTap);
}

// Toggle fullscreen mode for a chart
function toggleFullscreen(chartDiv) {
    if (chartDiv.classList.contains('chart-fullscreen')) {
        // Exit fullscreen
        chartDiv.classList.remove('chart-fullscreen');
        document.body.classList.remove('chart-fullscreen-active');

        // Resize chart immediately and after animation
        Plotly.Plots.resize(chartDiv);
        setTimeout(() => {
            Plotly.Plots.resize(chartDiv);
        }, 350);
    } else {
        // Enter fullscreen
        chartDiv.classList.add('chart-fullscreen');
        document.body.classList.add('chart-fullscreen-active');

        // Resize chart immediately and after animation
        Plotly.Plots.resize(chartDiv);
        setTimeout(() => {
            Plotly.Plots.resize(chartDiv);
        }, 350);
    }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCharts);
} else {
    initCharts();
}
