// Matrix rain effect
const canvas = document.getElementById('matrix-canvas');
const ctx = canvas.getContext('2d');

const katakana = 'アァカサタナハマヤャラワガザダバパイィキシチニヒミリヰギジヂビピウゥクスツヌフムユュルグズブヅプエェケセテネヘメレヱゲゼデベペオォコソトノホモヨョロヲゴゾドボポヴッン';
const latin = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ';
const nums = '0123456789';
const alphabet = katakana + latin + nums;

const fontSize = 16;
let columns = 0;
let rainDrops = [];

function initMatrix() {
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;
    columns = Math.floor(canvas.width / fontSize);
    rainDrops = [];

    // Initialize each column with a random starting position
    for (let x = 0; x < columns; x++) {
        rainDrops[x] = Math.floor(Math.random() * canvas.height / fontSize);
    }
}

// Initialize on load
initMatrix();

const draw = () => {
    ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.fillStyle = '#0F0';
    ctx.font = fontSize + 'px monospace';

    for (let i = 0; i < rainDrops.length; i++) {
        const text = alphabet.charAt(Math.floor(Math.random() * alphabet.length));
        ctx.fillText(text, i * fontSize, rainDrops[i] * fontSize);

        if (rainDrops[i] * fontSize > canvas.height && Math.random() > 0.975) {
            rainDrops[i] = 0;
        }
        rainDrops[i]++;
    }
};

setInterval(draw, 120);

window.addEventListener('resize', () => {
    initMatrix();
});

// Store automation configurations
let automationConfigs = {};

// Track client-side accumulated output for each automation
let automationClientOutput = {};

// Track if client has cleared output (to ignore subsequent updates until reset)
let automationClearedState = {};

// Service status functions
async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();

        updateServiceUI('tailscaled', status.tailscaled);
        updateServiceUI('minidlnad', status.minidlnad);
        updateServiceUI('smbd', status.smbd);
        updateServiceUI('qbittorrent', status.qbittorrent);
        updateInternetUI(status.internet);
    } catch (error) {
        console.error('Error fetching status:', error);
    }
}

async function updateSystemStats() {
    try {
        const response = await fetch('/api/system');
        const stats = await response.json();

        // Update page title with hostname
        document.getElementById('hostname-title').textContent = stats.hostname;

        // Update qBittorrent Web UI link
        document.getElementById('qbittorrent-link').href = `http://${stats.hostname}:8080`;

        // Update CPU
        document.getElementById('cpu-value').textContent = stats.cpu_percent + '%';
        updateProgressBar('cpu-progress', stats.cpu_percent);

        // Update CPU temperature
        if (stats.cpu_temp !== null && stats.cpu_temp !== undefined) {
            document.getElementById('cpu-temp').textContent = stats.cpu_temp + ' °F';
        } else {
            document.getElementById('cpu-temp').textContent = 'N/A';
        }

        // Update GPU temperature
        if (stats.gpu_temp !== null && stats.gpu_temp !== undefined) {
            document.getElementById('gpu-temp').textContent = stats.gpu_temp + ' °F';
        } else {
            document.getElementById('gpu-temp').textContent = 'N/A';
        }

        // Update RAM
        document.getElementById('ram-value').textContent = stats.ram_percent + '%';
        document.getElementById('ram-detail').textContent =
            `${stats.ram_used_gb} / ${stats.ram_total_gb} GB`;
        updateProgressBar('ram-progress', stats.ram_percent);

        // Update Disk
        document.getElementById('disk-value').textContent = stats.disk_percent + '%';
        document.getElementById('disk-detail').textContent =
            `${stats.disk_free_gb} GB FREE / ${stats.disk_total_gb} GB TOTAL`;
        document.getElementById('disk-mount').textContent = `MOUNT: ${stats.disk_mount}`;
        updateProgressBar('disk-progress', stats.disk_percent);

        // Update Network
        document.getElementById('network-interface').textContent =
            `INTERFACE: ${stats.network_interface}`;
        document.getElementById('upload-value').textContent = stats.upload_mbps + ' Mbps';
        document.getElementById('download-value').textContent = stats.download_mbps + ' Mbps';

        // Update Network Status (hostname and IP)
        document.getElementById('hostname-detail').textContent = `HOSTNAME: ${stats.hostname}`;
        document.getElementById('ip-detail').textContent = `IP ADDRESS: ${stats.ip_address}`;

        // Update Uptime
        document.getElementById('uptime-value').textContent = stats.uptime;
    } catch (error) {
        console.error('Error fetching system stats:', error);
    }
}

async function loadAutomations() {
    try {
        const response = await fetch('/api/automations');
        const data = await response.json();
        const automations = data.automations;

        // Store configs for later use
        automations.forEach(auto => {
            automationConfigs[auto.name] = auto;
        });

        // Get the container
        const container = document.getElementById('automations-container');
        container.innerHTML = '';

        // Create cards for each automation
        automations.forEach(auto => {
            const card = createAutomationCard(auto);
            container.appendChild(card);
        });
    } catch (error) {
        console.error('Error loading automations:', error);
    }
}

function createAutomationCard(automation) {
    const card = document.createElement('div');
    card.className = 'service-card';

    card.innerHTML = `
        <div class="service-header">
            <span class="service-name">${automation.display_name}</span>
            <div class="status-indicator yellow" id="${automation.name}-indicator"></div>
        </div>
        <div class="status-text" id="${automation.name}-status">READY</div>
        <div class="toggle-container">
            <button class="details-btn" onclick="runAutomation('${automation.name}')" id="${automation.name}-btn">
                ${automation.button_text}
            </button>
            <button class="details-btn clear-btn" onclick="clearAutomationOutput('${automation.name}')" id="${automation.name}-clear-btn" style="display: none;">
                CLEAR OUTPUT
            </button>
        </div>
        <div class="automation-output" id="${automation.name}-output" style="display: none;">
            <div style="font-size: 0.8em; color: #00ff41; margin-bottom: 5px; text-shadow: 0 0 3px #00ff41;">OUTPUT:</div>
            <div class="modal-output" style="max-height: 150px; font-size: 0.75em;" id="${automation.name}-output-text"></div>
        </div>
    `;

    return card;
}

async function showServiceDetails(service) {
    const modal = document.getElementById('serviceModal');
    const title = document.getElementById('modal-title');
    const output = document.getElementById('modal-output');

    title.textContent = `${service.toUpperCase()} STATUS`;
    output.textContent = 'Loading...';
    modal.style.display = 'block';

    try {
        const response = await fetch(`/api/service/details/${service}`);
        const data = await response.json();

        if (data.success) {
            output.textContent = data.output;
        } else {
            output.textContent = `ERROR: ${data.error}`;
        }
    } catch (error) {
        output.textContent = `ERROR: Failed to fetch service details\n${error.message}`;
    }
}

function closeModal() {
    document.getElementById('serviceModal').style.display = 'none';
}

// Close modal when clicking outside of it
window.onclick = function(event) {
    const modal = document.getElementById('serviceModal');
    if (event.target == modal) {
        closeModal();
    }
}

function updateProgressBar(id, percent) {
    const progressBar = document.getElementById(id);
    progressBar.style.width = percent + '%';

    // Change color based on usage
    progressBar.className = 'progress-fill';
    if (percent >= 90) {
        progressBar.classList.add('danger');
    } else if (percent >= 75) {
        progressBar.classList.add('warning');
    }
}

function updateServiceUI(service, isRunning) {
    const indicator = document.getElementById(`${service}-indicator`);
    const statusText = document.getElementById(`${service}-status`);
    const toggle = document.getElementById(`${service}-toggle`);

    if (isRunning) {
        indicator.className = 'status-indicator green';
        statusText.textContent = 'ONLINE';
        toggle.classList.add('active');
    } else {
        indicator.className = 'status-indicator red';
        statusText.textContent = 'OFFLINE';
        toggle.classList.remove('active');
    }
}

function updateInternetUI(isConnected) {
    // Update the internet status indicator in Network Status box
    const indicator = document.getElementById('internet-indicator-stat');
    const statusText = document.getElementById('internet-status-stat');

    if (isConnected) {
        indicator.className = 'status-indicator green';
        statusText.textContent = 'CONNECTED';
    } else {
        indicator.className = 'status-indicator red';
        statusText.textContent = 'DISCONNECTED';
    }
}

async function toggleService(service) {
    const toggle = document.getElementById(`${service}-toggle`);

    if (toggle.classList.contains('disabled')) return;

    const isActive = toggle.classList.contains('active');
    const action = isActive ? 'stop' : 'start';

    toggle.classList.add('disabled');

    try {
        const response = await fetch(`/api/control/${service}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ action: action })
        });

        const result = await response.json();

        if (result.success) {
            setTimeout(updateStatus, 1000);
        } else {
            alert(`SYSTEM ERROR: Failed to ${action} ${service}\n${result.error}`);
        }
    } catch (error) {
        alert(`CRITICAL ERROR: ${error.message}`);
    } finally {
        toggle.classList.remove('disabled');
    }
}

// Initialize WebSocket connection for real-time automation updates
const socket = io({
    transports: ['polling', 'websocket'],
    upgrade: true,
    reconnection: true,
    reconnectionDelay: 1000,
    reconnectionAttempts: 5
});

socket.on('connect', () => {
    console.log('WebSocket connected');
});

socket.on('disconnect', () => {
    console.log('WebSocket disconnected');
});

socket.on('connect_error', (error) => {
    console.error('WebSocket connection error:', error);
});

socket.on('automation_update', (data) => {
    console.log('Received automation update:', data);
    updateAutomationUI(data.automation, data.state);
});

function updateAutomationUI(automationName, state) {
    const btn = document.getElementById(`${automationName}-btn`);
    const indicator = document.getElementById(`${automationName}-indicator`);
    const statusText = document.getElementById(`${automationName}-status`);
    const outputDiv = document.getElementById(`${automationName}-output`);
    const outputText = document.getElementById(`${automationName}-output-text`);
    const clearBtn = document.getElementById(`${automationName}-clear-btn`);

    if (!btn || !indicator || !statusText || !outputDiv || !outputText || !clearBtn) {
        console.error('Missing elements for automation:', automationName);
        return;
    }

    // Handle output updates - either incremental or full
    if (state.output) {
        if (state.incremental) {
            // Incremental update - append to client's local buffer (unless cleared)
            if (!automationClearedState[automationName]) {
                // Initialize if needed
                if (!automationClientOutput[automationName]) {
                    automationClientOutput[automationName] = '';
                }
                // Append new output
                automationClientOutput[automationName] += state.output;

                // Update display
                outputDiv.style.display = 'block';
                outputText.textContent = automationClientOutput[automationName];
                outputText.scrollTop = outputText.scrollHeight;
            }
            // If cleared, ignore this incremental update (it's from before the clear)
        } else {
            // Full update (from initial connection or status request)
            // Only show output if automation is currently running (not for completed tasks)
            const shouldShowOutput = state.running;

            automationClientOutput[automationName] = state.output;
            if (!automationClearedState[automationName] && shouldShowOutput) {
                outputDiv.style.display = 'block';
                outputText.textContent = state.output;
                outputText.scrollTop = outputText.scrollHeight;
            }
        }

        // Show clear button when there's accumulated output and automation is running
        if (automationClientOutput[automationName] && automationClientOutput[automationName].length > 0 && state.running) {
            clearBtn.style.display = 'inline-block';
        }
    }

    // Update button and status based on state
    if (state.running) {
        btn.disabled = false;
        btn.textContent = 'CANCEL';
        btn.classList.add('cancel');
        indicator.className = 'status-indicator yellow';
        statusText.textContent = 'RUNNING...';
        btn.dataset.jobId = state.job_id;
        // Reset cleared state when automation starts running
        if (automationClearedState[automationName]) {
            delete automationClearedState[automationName];
            // Also reset the client output buffer for fresh start
            automationClientOutput[automationName] = '';
            outputText.textContent = '';
        }
    } else {
        btn.classList.remove('cancel');
        const config = automationConfigs[automationName];
        btn.textContent = config ? config.button_text : 'RUN';
        btn.disabled = false;
        delete btn.dataset.jobId;

        // Update indicator based on return code
        if (state.return_code === null) {
            indicator.className = 'status-indicator yellow';
            statusText.textContent = 'READY';
            if (!state.output && (!automationClientOutput[automationName] || automationClientOutput[automationName].length === 0)) {
                outputDiv.style.display = 'none';
                clearBtn.style.display = 'none';
            }
        } else if (state.return_code === 0) {
            indicator.className = 'status-indicator green';
            statusText.textContent = 'COMPLETED';
        } else if (state.return_code === -999) {
            indicator.className = 'status-indicator yellow';
            statusText.textContent = 'CANCELLED';
        } else {
            indicator.className = 'status-indicator red';
            statusText.textContent = 'FAILED';
        }
    }
}

async function runAutomation(automationName) {
    const btn = document.getElementById(`${automationName}-btn`);

    // Check if this is a cancel action
    if (btn.classList.contains('cancel')) {
        console.log('Cancel button clicked for:', automationName);
        await cancelAutomation(automationName);
        return;
    }

    console.log('Run button clicked for:', automationName);

    // Disable button temporarily
    btn.disabled = true;
    btn.textContent = 'STARTING...';

    try {
        const response = await fetch(`/api/automation/${automationName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        const result = await response.json();

        if (!result.success) {
            alert(`ERROR: ${result.error || 'Failed to start automation'}`);
            const config = automationConfigs[automationName];
            btn.disabled = false;
            btn.textContent = config ? config.button_text : 'RUN';
        }
        // If successful, the WebSocket will handle updating the UI
    } catch (error) {
        console.error('Error running automation:', error);
        alert(`CRITICAL ERROR: ${error.message}`);
        const config = automationConfigs[automationName];
        btn.disabled = false;
        btn.textContent = config ? config.button_text : 'RUN';
    }
}

async function cancelAutomation(automationName) {
    console.log('cancelAutomation called for:', automationName);
    const btn = document.getElementById(`${automationName}-btn`);

    btn.disabled = true;
    btn.textContent = 'CANCELLING...';

    try {
        console.log('Sending cancel request to:', `/api/automation/${automationName}/cancel`);
        const response = await fetch(`/api/automation/${automationName}/cancel`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        console.log('Cancel response status:', response.status);
        const result = await response.json();
        console.log('Cancel result:', result);

        if (!result.success) {
            console.error('Cancel failed:', result.error);
            alert(`ERROR: ${result.error || 'Failed to cancel automation'}`);
            btn.disabled = false;
            btn.classList.remove('cancel');
            const config = automationConfigs[automationName];
            btn.textContent = config ? config.button_text : 'RUN';
        }
        // If successful, the WebSocket will handle updating the UI
    } catch (error) {
        console.error('Error cancelling automation:', error);
        alert(`CRITICAL ERROR: ${error.message}`);
        btn.disabled = false;
        btn.classList.remove('cancel');
        const config = automationConfigs[automationName];
        btn.textContent = config ? config.button_text : 'RUN';
    }
}

function clearAutomationOutput(automationName) {
    console.log('clearAutomationOutput called for:', automationName);

    const outputDiv = document.getElementById(`${automationName}-output`);
    const outputText = document.getElementById(`${automationName}-output-text`);
    const clearBtn = document.getElementById(`${automationName}-clear-btn`);
    const btn = document.getElementById(`${automationName}-btn`);

    if (!outputDiv || !outputText || !clearBtn) {
        console.error('Missing elements for automation:', automationName);
        return;
    }

    // Clear the display
    outputText.textContent = '';

    // Check if automation is currently running
    const isRunning = btn && btn.classList.contains('cancel');

    if (isRunning) {
        // If running, keep the output visible but mark as cleared
        // Future incremental updates will be ignored until automation restarts
        automationClearedState[automationName] = true;
        outputDiv.style.display = 'block';
    } else {
        // If not running, hide the output div and clear button
        outputDiv.style.display = 'none';
        clearBtn.style.display = 'none';
        delete automationClearedState[automationName];
        // Also clear the client output buffer
        automationClientOutput[automationName] = '';
    }
}

// Toggle section collapse
function toggleSection(sectionName) {
    const section = document.getElementById(`${sectionName}-section`);
    const separator = document.querySelector(`.separator-${sectionName}`);

    if (!section || !separator) {
        console.error(`Section or separator not found for: ${sectionName}`);
        return;
    }

    // Toggle collapsed class
    const isCollapsed = section.classList.toggle('collapsed');
    separator.classList.toggle('collapsed', isCollapsed);

    // Save state to localStorage
    localStorage.setItem(`section-${sectionName}-collapsed`, isCollapsed);
}

// Restore collapsed states from localStorage
function restoreCollapsedStates() {
    const sections = ['services', 'automations', 'stats'];

    sections.forEach(sectionName => {
        const isCollapsed = localStorage.getItem(`section-${sectionName}-collapsed`) === 'true';

        if (isCollapsed) {
            const section = document.getElementById(`${sectionName}-section`);
            const separator = document.querySelector(`.separator-${sectionName}`);

            if (section && separator) {
                section.classList.add('collapsed');
                separator.classList.add('collapsed');
            }
        }
    });
}

// Initialize the page
async function init() {
    restoreCollapsedStates();
    await loadAutomations();
    updateStatus();
    updateSystemStats();
    setInterval(updateStatus, 5000);
    setInterval(updateSystemStats, 2000);
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}