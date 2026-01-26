/**
 * Monitor Page JavaScript
 *
 * Handles stock charts, weather data, clock, and status updates
 */

// Default stock symbols
const DEFAULT_STOCK_SYMBOLS = ['AMD', 'INTC', '^IXIC', '^DJI', '^GSPC'];
const DEFAULT_STOCK_NAMES = {
    'AMD': 'AMD',
    'INTC': 'INTC',
    '^IXIC': 'NASDAQ',
    '^DJI': 'Dow Jones',
    '^GSPC': 'S&P 500'
};

// Date range options (in days, 0 = all time)
const DATE_RANGE_OPTIONS = {
    '1w': { label: '1 Week', days: 7 },
    '1m': { label: '1 Month', days: 30 },
    '1y': { label: '1 Year', days: 365 },
    '5y': { label: '5 Years', days: 1825 },
    '10y': { label: '10 Years', days: 3650 },
    'all': { label: 'All Time', days: 0 }
};

// Default max data points for LTTB downsampling
const DEFAULT_MAX_DATA_POINTS = 10000;

// Load stock settings from localStorage
function loadStockSettings() {
    const savedSymbols = localStorage.getItem('stockSymbols');
    const savedNames = localStorage.getItem('stockNames');
    const savedRange = localStorage.getItem('stockDateRange');
    const savedMaxPoints = localStorage.getItem('stockMaxDataPoints');

    return {
        symbols: savedSymbols ? JSON.parse(savedSymbols) : DEFAULT_STOCK_SYMBOLS,
        names: savedNames ? JSON.parse(savedNames) : DEFAULT_STOCK_NAMES,
        dateRange: savedRange || '1m',
        maxDataPoints: savedMaxPoints ? parseInt(savedMaxPoints, 10) : DEFAULT_MAX_DATA_POINTS
    };
}

// Save stock settings to localStorage
function saveStockSettings(symbols, names, dateRange, maxDataPoints) {
    localStorage.setItem('stockSymbols', JSON.stringify(symbols));
    localStorage.setItem('stockNames', JSON.stringify(names));
    localStorage.setItem('stockDateRange', dateRange);
    if (maxDataPoints !== undefined) {
        localStorage.setItem('stockMaxDataPoints', maxDataPoints.toString());
    }
}

// Current stock settings
let stockSettings = loadStockSettings();

// Update intervals (in milliseconds)
const STOCK_UPDATE_INTERVAL = 5 * 60 * 1000; // 5 minutes
const WEATHER_UPDATE_INTERVAL = 10 * 60 * 1000; // 10 minutes
const STATUS_UPDATE_INTERVAL = 5000; // 5 seconds
const CLOCK_UPDATE_INTERVAL = 1000; // 1 second
const DEFAULT_SENSOR_UPDATE_INTERVAL = 5; // 5 seconds (in seconds, not milliseconds)

// Weather settings (persistent in localStorage)
let weatherLocation = localStorage.getItem('weatherLocation') || null;

// Sensor settings
let availableTimeseries = [];
let selectedSensorIds = new Set();
let sensorUpdateInterval = DEFAULT_SENSOR_UPDATE_INTERVAL; // in seconds
let sensorIntervalId = null;
let sensorUpdateInProgress = false; // Guard against concurrent requests

/**
 * Load sensor settings from localStorage
 */
function loadSensorSettings() {
    const saved = localStorage.getItem('selectedSensors');
    if (saved) {
        selectedSensorIds = new Set(JSON.parse(saved));
    }
    const savedInterval = localStorage.getItem('sensorUpdateInterval');
    if (savedInterval) {
        sensorUpdateInterval = parseInt(savedInterval, 10);
    }
    return selectedSensorIds;
}

/**
 * Save sensor settings to localStorage
 */
function saveSensorSettings() {
    localStorage.setItem('selectedSensors', JSON.stringify([...selectedSensorIds]));
    localStorage.setItem('sensorUpdateInterval', sensorUpdateInterval.toString());
}

/**
 * Start or restart the sensor update interval
 */
function startSensorUpdates() {
    // Clear any existing interval
    if (sensorIntervalId) {
        clearInterval(sensorIntervalId);
    }
    
    // Start new interval with current setting (convert seconds to milliseconds)
    sensorIntervalId = setInterval(updateSensorDisplay, sensorUpdateInterval * 1000);
}

/**
 * Initialize the monitor page
 */
async function initMonitor() {
    console.log('Initializing monitor page...');

    // Apply saved theme colors
    applyThemeColors();

    // Initialize inline date range selector
    initInlineDateRange();

    // Start clock
    updateClock();
    setInterval(updateClock, CLOCK_UPDATE_INTERVAL);

    // Initialize weather location if not set
    if (!weatherLocation) {
        await initializeWeatherLocation();
    }

    // Load sensor settings and available timeseries
    loadSensorSettings();
    await loadAvailableTimeseries();

    // Load initial data
    updateStockChart();
    updateWeather();
    updateStatus();
    updateSensorDisplay();

    // Set up periodic updates
    setInterval(updateStockChart, STOCK_UPDATE_INTERVAL);
    setInterval(updateWeather, WEATHER_UPDATE_INTERVAL);
    setInterval(updateStatus, STATUS_UPDATE_INTERVAL);
    startSensorUpdates();

    console.log('Monitor page initialized');
}

/**
 * Initialize the inline date range selector with saved value
 */
function initInlineDateRange() {
    const inlineSelect = document.getElementById('stock-date-range-inline');
    if (inlineSelect) {
        inlineSelect.value = stockSettings.dateRange;
    }
}

/**
 * Handle inline date range change
 */
function onDateRangeChange(value) {
    stockSettings.dateRange = value;
    saveStockSettings(stockSettings.symbols, stockSettings.names, value, stockSettings.maxDataPoints);
    updateStockChart();
}

/**
 * Apply theme colors from localStorage (synced with index.html settings)
 */
function applyThemeColors() {
    const foregroundColor = localStorage.getItem('foregroundColor');
    const backgroundColor = localStorage.getItem('backgroundColor');

    if (foregroundColor) {
        document.documentElement.style.setProperty('--theme-primary', foregroundColor);

        // Parse hex to RGB for rgba usage
        const r = parseInt(foregroundColor.slice(1, 3), 16);
        const g = parseInt(foregroundColor.slice(3, 5), 16);
        const b = parseInt(foregroundColor.slice(5, 7), 16);
        document.documentElement.style.setProperty('--theme-primary-rgb', `${r}, ${g}, ${b}`);

        // Calculate dimmed version (70% brightness) for --theme-primary-dim
        const dimR = Math.floor(r * 0.7);
        const dimG = Math.floor(g * 0.7);
        const dimB = Math.floor(b * 0.7);
        const dimHex = `#${dimR.toString(16).padStart(2, '0')}${dimG.toString(16).padStart(2, '0')}${dimB.toString(16).padStart(2, '0')}`;
        document.documentElement.style.setProperty('--theme-primary-dim', dimHex);
    }

    if (backgroundColor) {
        document.documentElement.style.setProperty('--background-color', backgroundColor);
    }

    // Apply clock tick colors
    const tickMinorColor = localStorage.getItem('clockTickMinorColor');
    const tickMajorColor = localStorage.getItem('clockTickMajorColor');
    const tickQuarterColor = localStorage.getItem('clockTickQuarterColor');

    if (tickMinorColor) {
        document.documentElement.style.setProperty('--clock-tick-minor-color', tickMinorColor);
    }
    if (tickMajorColor) {
        document.documentElement.style.setProperty('--clock-tick-major-color', tickMajorColor);
    }
    if (tickQuarterColor) {
        document.documentElement.style.setProperty('--clock-tick-quarter-color', tickQuarterColor);
    }
}

/**
 * Initialize weather location using IP geolocation
 */
async function initializeWeatherLocation() {
    console.log('No weather location set, using IP geolocation...');

    try {
        // Use ipapi.co for free IP geolocation
        const response = await fetch('https://ipapi.co/json/');
        const data = await response.json();

        if (data.city && data.region) {
            weatherLocation = `${data.city}, ${data.region}`;
            localStorage.setItem('weatherLocation', weatherLocation);
            console.log(`Set weather location to: ${weatherLocation}`);
        }
    } catch (error) {
        console.error('Error getting IP geolocation:', error);
        // Fallback to a default if geolocation fails
        weatherLocation = 'New York, NY';
        localStorage.setItem('weatherLocation', weatherLocation);
    }
}

/**
 * Update the analog and digital clock
 */
function updateClock() {
    const now = new Date();

    // Update digital time
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    document.getElementById('digital-time').textContent = `${hours}:${minutes}:${seconds}`;

    // Update date
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById('date-display').textContent = now.toLocaleDateString('en-US', options);

    // Update analog clock hands
    const secondsDegrees = (now.getSeconds() / 60) * 360;
    const minutesDegrees = (now.getMinutes() / 60) * 360 + (now.getSeconds() / 60) * 6;
    const hoursDegrees = ((now.getHours() % 12) / 12) * 360 + (now.getMinutes() / 60) * 30;

    document.getElementById('second-hand').style.transform = `rotate(${secondsDegrees}deg)`;
    document.getElementById('minute-hand').style.transform = `rotate(${minutesDegrees}deg)`;
    document.getElementById('hour-hand').style.transform = `rotate(${hoursDegrees}deg)`;
}

/**
 * Update stock chart with daily percentage changes
 */
async function updateStockChart() {
    console.log('Updating stock chart...');

    try {
        // Get current settings
        const { symbols, names, dateRange, maxDataPoints } = stockSettings;
        const rangeDays = DATE_RANGE_OPTIONS[dateRange]?.days || 30;

        // Fetch stock data from backend
        const response = await fetch('/api/stocks/daily-change', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                symbols: symbols,
                days: rangeDays,
                max_points: maxDataPoints
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch stock data');
        }

        // Prepare data for plotting
        const traces = [];
        const stockData = data.data;

        // Collect all date labels for X-axis tick labels
        // Use the first symbol's labels as reference for tick positions
        let tickvals = [];
        let ticktext = [];
        const firstSymbolData = stockData[symbols[0]];
        if (firstSymbolData && firstSymbolData.date_labels) {
            const labels = firstSymbolData.date_labels;
            const numTicks = Math.min(10, labels.length); // Show ~10 tick labels
            const step = Math.max(1, Math.floor(labels.length / numTicks));
            for (let i = 0; i < labels.length; i += step) {
                tickvals.push(i);
                ticktext.push(labels[i]);
            }
            // Always include the last label
            if (tickvals[tickvals.length - 1] !== labels.length - 1) {
                tickvals.push(labels.length - 1);
                ticktext.push(labels[labels.length - 1]);
            }
        }

        // Create a trace for each stock
        symbols.forEach(symbol => {
            const symData = stockData[symbol];
            if (symData && symData.cumulative_return) {
                // Use indices for X if available, otherwise fall back to date_labels
                const xData = symData.indices || symData.date_labels || [];
                traces.push({
                    x: xData,
                    y: symData.cumulative_return,
                    text: symData.date_labels,  // For hover text
                    type: 'scatter',
                    mode: 'lines',
                    name: names[symbol] || symbol,
                    line: { width: 2 },
                    hovertemplate: '%{text}<br>%{fullData.name}: %{y:.2f}%<extra></extra>'
                });
            }
        });

        // Get theme color for consistent styling
        const themeColor = getComputedStyle(document.documentElement).getPropertyValue('--theme-primary').trim();
        const themeRgb = getComputedStyle(document.documentElement).getPropertyValue('--theme-primary-rgb').trim();

        // Plot configuration
        const layout = {
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0.3)',
            font: {
                family: 'Courier New, monospace',
                color: themeColor,
                size: 10
            },
            xaxis: {
                gridcolor: `rgba(${themeRgb}, 0.1)`,
                showgrid: true,
                tickvals: tickvals.length > 0 ? tickvals : undefined,
                ticktext: ticktext.length > 0 ? ticktext : undefined,
                tickangle: 0,
                tickfont: { size: 9 }
            },
            yaxis: {
                title: 'Return %',
                gridcolor: `rgba(${themeRgb}, 0.1)`,
                showgrid: true,
                zeroline: true,
                zerolinecolor: 'rgba(255, 255, 255, 0.5)',
                zerolinewidth: 2
            },
            legend: {
                orientation: 'h',
                y: -0.15,
                x: 0.5,
                xanchor: 'center',
                bgcolor: 'rgba(40, 40, 50, 0.95)',
                bordercolor: themeColor,
                borderwidth: 1,
                font: {
                    color: themeColor,
                    size: 10
                }
            },
            margin: {
                l: 50,
                r: 20,
                t: 10,
                b: 70
            },
            hovermode: 'x unified'
        };

        const config = {
            responsive: true,
            displayModeBar: false
        };

        Plotly.newPlot('stock-chart', traces, layout, config);

        console.log('Stock chart updated successfully');
    } catch (error) {
        console.error('Error updating stock chart:', error);
        document.getElementById('stock-chart').innerHTML = `
            <div class="placeholder-text">
                ERROR LOADING STOCK DATA<br>
                <span style="font-size: 0.6em;">${error.message}</span>
            </div>
        `;
    }
}

/**
 * Update weather information
 */
async function updateWeather() {
    console.log('Updating weather...');

    if (!weatherLocation) {
        document.querySelector('.weather-temp').textContent = '--°F';
        document.querySelector('.weather-condition').textContent = 'No location set';
        document.querySelector('.weather-location').textContent = 'Click ⚙ to configure';
        return;
    }

    try {
        const response = await fetch('/api/weather', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ location: weatherLocation })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch weather data');
        }

        // Update UI with weather data
        document.querySelector('.weather-temp').textContent = `${Math.round(data.temperature)}°F`;
        document.querySelector('.weather-condition').textContent = data.condition;
        document.querySelector('.weather-location').textContent = data.location;

        console.log('Weather updated successfully');
    } catch (error) {
        console.error('Error updating weather:', error);
        document.querySelector('.weather-temp').textContent = '--°F';
        document.querySelector('.weather-condition').textContent = 'Error loading weather';
        document.querySelector('.weather-location').textContent = weatherLocation;
    }
}

/**
 * Update quick status information
 */
async function updateStatus() {
    try {
        // Fetch service statuses
        const statusResponse = await fetch('/api/status');
        const statusData = await statusResponse.json();

        // Fetch system stats
        const systemResponse = await fetch('/api/system');
        const systemData = await systemResponse.json();

        // Update service indicators - only show enabled services
        const servicesResponse = await fetch('/api/services');
        const servicesData = await servicesResponse.json();

        const indicatorsContainer = document.getElementById('service-indicators');
        indicatorsContainer.innerHTML = '';

        // Filter and display only enabled services
        const enabledServices = servicesData.filter(service => service.enabled !== false);

        if (enabledServices.length === 0) {
            indicatorsContainer.innerHTML = '<div style="color: var(--theme-primary-dim); font-size: 0.9em;">No services configured</div>';
        } else {
            enabledServices.forEach(service => {
                // Handle both old format (boolean) and new format (object)
                const serviceStatus = statusData[service.id];
                const isActive = typeof serviceStatus === 'boolean' ? serviceStatus : (serviceStatus?.running || false);
                const ledEl = document.createElement('div');
                ledEl.className = 'service-led';
                ledEl.innerHTML = `
                    <div class="service-led-indicator ${isActive ? 'green' : 'red'}"></div>
                    <div class="service-led-name">${service.display_name || service.name}</div>
                `;
                indicatorsContainer.appendChild(ledEl);
            });
        }

        // Update uptime
        document.getElementById('uptime-status').textContent = systemData.uptime || '--';

        // Update disk space
        const diskPercent = systemData.disk_percent || 0;
        const diskFree = systemData.disk_free_gb || 0;
        document.getElementById('disk-status').textContent = `${diskPercent}% used (${diskFree}GB free)`;

    } catch (error) {
        console.error('Error updating status:', error);
    }
}

/**
 * Load available timeseries from the API
 */
async function loadAvailableTimeseries() {
    try {
        const response = await fetch('/api/timeseries/list');
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        availableTimeseries = await response.json();
        console.log(`Loaded ${availableTimeseries.length} available timeseries`);
    } catch (error) {
        console.error('Error loading timeseries list:', error);
        availableTimeseries = [];
    }
}

/**
 * Update the sensor data display with latest values
 */
async function updateSensorDisplay() {
    const container = document.getElementById('sensor-data');

    if (selectedSensorIds.size === 0) {
        container.innerHTML = '<div class="sensor-data-empty">No sensors configured. Click ⚙ to add sensors.</div>';
        return;
    }

    // Skip if a request is already in progress (prevents overlapping requests on fast intervals)
    if (sensorUpdateInProgress) {
        console.log('Sensor update skipped - previous request still in progress');
        return;
    }

    sensorUpdateInProgress = true;

    try {
        // Calculate 24h time range
        const now = Date.now() / 1000;  // Current time in seconds
        const twentyFourHoursAgo = now - (24 * 60 * 60);

        // Fetch latest data and 24h min/max in parallel
        const [latestResponse, minmaxResponse] = await Promise.all([
            fetch('/api/timeseries/data/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    timeseries_ids: [...selectedSensorIds],
                    limit: 1  // Only need the latest value
                })
            }),
            fetch('/api/timeseries/minmax/batch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    timeseries_ids: [...selectedSensorIds],
                    start: twentyFourHoursAgo,
                    end: now
                })
            })
        ]);

        if (!latestResponse.ok) {
            throw new Error(`HTTP error! status: ${latestResponse.status}`);
        }

        const sensorData = await latestResponse.json();
        const minmaxData = minmaxResponse.ok ? await minmaxResponse.json() : {};

        // Build the sensor display HTML
        let html = '';
        for (const sensor of sensorData) {
            if (sensor.data && sensor.data.length > 0) {
                const latestValue = sensor.data[sensor.data.length - 1].value;
                const formattedValue = typeof latestValue === 'number' ? latestValue.toFixed(2) : latestValue;
                const minmax = minmaxData[sensor.id];
                const minmaxHtml = minmax
                    ? `<div class="sensor-minmax"><div>24H Min: ${minmax.min.toFixed(2)}</div><div>24H Max: ${minmax.max.toFixed(2)}</div></div>`
                    : '';
                html += `
                    <div class="sensor-item">
                        <span class="sensor-name">${sensor.name}:</span>
                        <div class="sensor-value-row">
                            <span class="sensor-value">${formattedValue} ${sensor.units || ''}</span>
                            ${minmaxHtml}
                        </div>
                    </div>
                `;
            } else {
                html += `
                    <div class="sensor-item sensor-no-data">
                        <span class="sensor-name">${sensor.name}:</span>
                        <span class="sensor-value">No data</span>
                    </div>
                `;
            }
        }

        container.innerHTML = html || '<div class="sensor-data-empty">No sensor data available</div>';

    } catch (error) {
        console.error('Error updating sensor display:', error);
        // Only show error message if container doesn't already have valid sensor data
        // This prevents flickering when a single request fails
        if (!container.querySelector('.sensor-item')) {
            container.innerHTML = '<div class="sensor-data-empty">Error loading sensor data</div>';
        }
    } finally {
        sensorUpdateInProgress = false;
    }
}

/**
 * Load sensor selection checkboxes in settings modal
 */
function loadSensorSelectionList() {
    const container = document.getElementById('sensor-selection-list');
    
    if (availableTimeseries.length === 0) {
        container.innerHTML = '<div class="loading-text">No timeseries available</div>';
        return;
    }

    // Group timeseries by category
    const byCategory = {};
    for (const ts of availableTimeseries) {
        const category = ts.category || 'Other';
        if (!byCategory[category]) {
            byCategory[category] = [];
        }
        byCategory[category].push(ts);
    }

    // Build checkbox list HTML
    let html = '';
    const categories = Object.keys(byCategory).sort();
    
    for (const category of categories) {
        html += `<div class="sensor-category-header">${category}</div>`;
        
        for (const ts of byCategory[category]) {
            const isChecked = selectedSensorIds.has(ts.id);
            html += `
                <label class="sensor-checkbox-item">
                    <input type="checkbox" 
                           class="sensor-checkbox" 
                           data-sensor-id="${ts.id}" 
                           ${isChecked ? 'checked' : ''}>
                    <span class="sensor-checkbox-label">${ts.name}</span>
                    ${ts.units ? `<span class="sensor-checkbox-units">(${ts.units})</span>` : ''}
                </label>
            `;
        }
    }

    container.innerHTML = html;
}

/**
 * Open unified settings modal
 */
function openSettingsModal() {
    // Populate clock tick colors
    const tickMinorInput = document.getElementById('clock-tick-minor-color');
    const tickMajorInput = document.getElementById('clock-tick-major-color');
    const tickQuarterInput = document.getElementById('clock-tick-quarter-color');
    const defaultColor = localStorage.getItem('foregroundColor') || '#00ff41';
    tickMinorInput.value = localStorage.getItem('clockTickMinorColor') || defaultColor;
    tickMajorInput.value = localStorage.getItem('clockTickMajorColor') || defaultColor;
    tickQuarterInput.value = localStorage.getItem('clockTickQuarterColor') || defaultColor;

    // Populate weather location
    document.getElementById('weather-address').value = weatherLocation || '';

    // Populate stock symbols
    const symbolsText = stockSettings.symbols.map(symbol => {
        const name = stockSettings.names[symbol] || symbol;
        return `${symbol}:${name}`;
    }).join('\n');
    document.getElementById('stock-symbols').value = symbolsText;

    // Populate max data points
    const maxPointsInput = document.getElementById('stock-max-points');
    if (maxPointsInput) {
        maxPointsInput.value = stockSettings.maxDataPoints;
    }

    // Populate sensor selection list
    loadSensorSelectionList();

    // Populate sensor update interval
    const sensorIntervalInput = document.getElementById('sensor-update-interval');
    if (sensorIntervalInput) {
        sensorIntervalInput.value = sensorUpdateInterval;
    }

    document.getElementById('settingsModal').style.display = 'block';
}

/**
 * Close settings modal
 */
function closeSettingsModal() {
    document.getElementById('settingsModal').style.display = 'none';
}

/**
 * Save all settings
 */
function saveSettings() {
    // Save clock tick colors
    const tickMinorColor = document.getElementById('clock-tick-minor-color').value;
    const tickMajorColor = document.getElementById('clock-tick-major-color').value;
    const tickQuarterColor = document.getElementById('clock-tick-quarter-color').value;
    localStorage.setItem('clockTickMinorColor', tickMinorColor);
    localStorage.setItem('clockTickMajorColor', tickMajorColor);
    localStorage.setItem('clockTickQuarterColor', tickQuarterColor);
    document.documentElement.style.setProperty('--clock-tick-minor-color', tickMinorColor);
    document.documentElement.style.setProperty('--clock-tick-major-color', tickMajorColor);
    document.documentElement.style.setProperty('--clock-tick-quarter-color', tickQuarterColor);

    // Save weather settings
    const address = document.getElementById('weather-address').value.trim();
    if (address) {
        weatherLocation = address;
        localStorage.setItem('weatherLocation', address);
    }

    // Save stock settings
    const symbolsText = document.getElementById('stock-symbols').value.trim();
    const dateRange = stockSettings.dateRange; // Use current date range (controlled by inline selector)

    if (symbolsText) {
        // Parse symbols and names
        const lines = symbolsText.split('\n').filter(line => line.trim());
        const symbols = [];
        const names = {};

        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed.includes(':')) {
                const [symbol, name] = trimmed.split(':').map(s => s.trim());
                if (symbol) {
                    symbols.push(symbol.toUpperCase());
                    names[symbol.toUpperCase()] = name || symbol.toUpperCase();
                }
            } else if (trimmed) {
                const symbol = trimmed.toUpperCase();
                symbols.push(symbol);
                names[symbol] = symbol;
            }
        }

        if (symbols.length > 0) {
            // Get max data points from the input
            const maxDataPointsInput = document.getElementById('stock-max-points');
            const maxDataPoints = maxDataPointsInput ? parseInt(maxDataPointsInput.value, 10) || DEFAULT_MAX_DATA_POINTS : stockSettings.maxDataPoints;

            // Save settings
            stockSettings = { symbols, names, dateRange, maxDataPoints };
            saveStockSettings(symbols, names, dateRange, maxDataPoints);
        }
    }

    // Save sensor settings
    const sensorCheckboxes = document.querySelectorAll('.sensor-checkbox');
    selectedSensorIds.clear();
    sensorCheckboxes.forEach(checkbox => {
        if (checkbox.checked) {
            selectedSensorIds.add(checkbox.dataset.sensorId);
        }
    });
    
    // Save sensor update interval
    const sensorIntervalInput = document.getElementById('sensor-update-interval');
    if (sensorIntervalInput) {
        const newInterval = parseInt(sensorIntervalInput.value, 10);
        if (newInterval >= 1 && newInterval <= 3600) {
            sensorUpdateInterval = newInterval;
        }
    }
    
    saveSensorSettings();

    closeSettingsModal();

    // Refresh data
    updateWeather();
    updateStockChart();
    updateSensorDisplay();
    
    // Restart sensor updates with new interval
    startSensorUpdates();
}

/**
 * Reset all settings to defaults
 */
function resetSettings() {
    // Reset clock tick colors (remove to use theme default)
    localStorage.removeItem('clockTickMinorColor');
    localStorage.removeItem('clockTickMajorColor');
    localStorage.removeItem('clockTickQuarterColor');
    document.documentElement.style.removeProperty('--clock-tick-minor-color');
    document.documentElement.style.removeProperty('--clock-tick-major-color');
    document.documentElement.style.removeProperty('--clock-tick-quarter-color');

    // Reset stock settings
    stockSettings = {
        symbols: [...DEFAULT_STOCK_SYMBOLS],
        names: { ...DEFAULT_STOCK_NAMES },
        dateRange: '1m',
        maxDataPoints: DEFAULT_MAX_DATA_POINTS
    };
    saveStockSettings(stockSettings.symbols, stockSettings.names, stockSettings.dateRange, stockSettings.maxDataPoints);

    // Sync the inline date range selector
    const inlineSelect = document.getElementById('stock-date-range-inline');
    if (inlineSelect) {
        inlineSelect.value = stockSettings.dateRange;
    }

    // Clear weather location (will prompt for new location)
    weatherLocation = null;
    localStorage.removeItem('weatherLocation');

    // Clear sensor settings
    selectedSensorIds.clear();
    sensorUpdateInterval = DEFAULT_SENSOR_UPDATE_INTERVAL;
    saveSensorSettings();

    // Re-populate the form with defaults
    openSettingsModal();
    
    // Refresh sensor display
    updateSensorDisplay();
    
    // Restart sensor updates with default interval
    startSensorUpdates();
}

// Close modals when clicking outside
window.onclick = function(event) {
    const settingsModal = document.getElementById('settingsModal');
    if (event.target === settingsModal) {
        closeSettingsModal();
    }
};

// Initialize when page loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMonitor);
} else {
    initMonitor();
}
