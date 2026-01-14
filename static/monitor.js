/**
 * Monitor Page JavaScript
 *
 * Handles stock charts, weather data, clock, and status updates
 */

// Stock symbols to track
const STOCK_SYMBOLS = ['AMD', 'INTC', '^IXIC', '^DJI', '^GSPC']; // NASDAQ, DOW JONES, S&P 500
const STOCK_NAMES = {
    'AMD': 'AMD',
    'INTC': 'Intel',
    '^IXIC': 'NASDAQ',
    '^DJI': 'Dow Jones',
    '^GSPC': 'S&P 500'
};

// Update intervals (in milliseconds)
const STOCK_UPDATE_INTERVAL = 5 * 60 * 1000; // 5 minutes
const WEATHER_UPDATE_INTERVAL = 10 * 60 * 1000; // 10 minutes
const STATUS_UPDATE_INTERVAL = 5000; // 5 seconds
const CLOCK_UPDATE_INTERVAL = 1000; // 1 second

// Weather settings (persistent in localStorage)
let weatherLocation = localStorage.getItem('weatherLocation') || null;

/**
 * Initialize the monitor page
 */
async function initMonitor() {
    console.log('Initializing monitor page...');

    // Apply saved theme colors
    applyThemeColors();

    // Start clock
    updateClock();
    setInterval(updateClock, CLOCK_UPDATE_INTERVAL);

    // Initialize weather location if not set
    if (!weatherLocation) {
        await initializeWeatherLocation();
    }

    // Load initial data
    updateStockChart();
    updateWeather();
    updateStatus();

    // Set up periodic updates
    setInterval(updateStockChart, STOCK_UPDATE_INTERVAL);
    setInterval(updateWeather, WEATHER_UPDATE_INTERVAL);
    setInterval(updateStatus, STATUS_UPDATE_INTERVAL);

    console.log('Monitor page initialized');
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
    const secondsDegrees = ((now.getSeconds() / 60) * 360) + 90;
    const minutesDegrees = ((now.getMinutes() / 60) * 360) + ((now.getSeconds() / 60) * 6) + 90;
    const hoursDegrees = ((now.getHours() % 12 / 12) * 360) + ((now.getMinutes() / 60) * 30) + 90;

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
        // Fetch stock data from backend
        const response = await fetch('/api/stocks/daily-change', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ symbols: STOCK_SYMBOLS })
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

        // Get date range (last 30 days of trading)
        const dates = stockData[STOCK_SYMBOLS[0]]?.dates || [];

        // Create a trace for each stock
        STOCK_SYMBOLS.forEach(symbol => {
            if (stockData[symbol]) {
                traces.push({
                    x: stockData[symbol].dates,
                    y: stockData[symbol].percent_changes,
                    type: 'scatter',
                    mode: 'lines',
                    name: STOCK_NAMES[symbol],
                    line: { width: 2 }
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
                color: themeColor
            },
            xaxis: {
                title: 'Date',
                gridcolor: `rgba(${themeRgb}, 0.1)`,
                showgrid: true
            },
            yaxis: {
                title: 'Daily % Change',
                gridcolor: `rgba(${themeRgb}, 0.1)`,
                showgrid: true,
                zeroline: true,
                zerolinecolor: 'rgba(255, 255, 255, 0.5)',
                zerolinewidth: 2
            },
            legend: {
                orientation: 'h',
                y: -0.2,
                bgcolor: 'rgba(0, 0, 0, 0.9)',
                bordercolor: themeColor,
                borderwidth: 1,
                font: {
                    color: themeColor
                }
            },
            margin: {
                l: 50,
                r: 20,
                t: 20,
                b: 80
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
 * Open weather settings modal
 */
function openWeatherSettings() {
    document.getElementById('weather-address').value = weatherLocation;
    document.getElementById('weatherModal').style.display = 'block';
}

/**
 * Close weather settings modal
 */
function closeWeatherSettings() {
    document.getElementById('weatherModal').style.display = 'none';
}

/**
 * Save weather settings
 */
function saveWeatherSettings() {
    const address = document.getElementById('weather-address').value.trim();

    if (address) {
        weatherLocation = address;
        localStorage.setItem('weatherLocation', address);
        closeWeatherSettings();
        updateWeather();
    } else {
        alert('Please enter a valid address or location');
    }
}

// Close modals when clicking outside
window.onclick = function(event) {
    const weatherModal = document.getElementById('weatherModal');
    if (event.target === weatherModal) {
        closeWeatherSettings();
    }
};

// Initialize when page loads
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMonitor);
} else {
    initMonitor();
}
