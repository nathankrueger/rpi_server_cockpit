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

    // Use theme color if set, otherwise default to green
    ctx.fillStyle = window.matrixColor || '#0F0';
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

// Matrix animation interval - will be set in init()
let matrixInterval = null;


window.addEventListener('resize', () => {
    initMatrix();
});

// --- Retry / resilience constants ---
// When a fetch() call fails with a network error (e.g. stale keep-alive connection,
// momentary eventlet hiccup), we don't immediately show an error. Instead we wait
// briefly, then check the server's actual state before giving up. This eliminates
// false "CRITICAL ERROR: Load failed" popups on transient network failures while
// keeping the delay invisible to the user in the normal (successful) case.
const RUN_AUTOMATION_RETRY_DELAY_MS = 2000;   // Delay before status-check after a failed run request
const CANCEL_AUTOMATION_RETRY_DELAY_MS = 1000; // Delay before status-check after a failed cancel request

// --- Toast notification system ---
// Non-blocking replacement for alert(). Shows a temporary message that auto-dismisses,
// allowing WebSocket updates to continue processing in the background.
function showToast(message, type = 'error', durationMs = 4000) {
    // Create container on first use
    let container = document.getElementById('toast-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toast-container';
        document.body.appendChild(container);
    }

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    container.appendChild(toast);

    // Trigger entrance animation on next frame
    requestAnimationFrame(() => toast.classList.add('toast-visible'));

    setTimeout(() => {
        toast.classList.remove('toast-visible');
        toast.addEventListener('transitionend', () => toast.remove());
        // Fallback removal in case transitionend doesn't fire
        setTimeout(() => toast.remove(), 500);
    }, durationMs);
}

// Store automation configurations
let automationConfigs = {};

// Track client-side accumulated output for each automation
let automationClientOutput = {};

// Track if client has cleared output (to ignore subsequent updates until reset)
let automationClearedState = {};

// Track which automation is currently shown in the fullscreen modal
let currentExpandedAutomation = null;

// Command history for automation args inputs
// Each automation has its own history array
let automationCommandHistory = {};
// Track current position in history (-1 means at "new command" position)
let automationHistoryIndex = {};
// Store pending input when user navigates history
let automationPendingInput = {};

// Service status functions
let servicesConfig = [];

// Track pending service operations: { serviceId: 'start' | 'stop' }
let pendingServiceOps = {};

// Remote machine state
let remoteMachinesConfig = [];
let pendingRemoteMachineOps = {};

async function loadAndRenderServices() {
    try {
        const response = await fetch('/api/services');
        servicesConfig = await response.json();
        renderServices();
    } catch (error) {
        console.error('Error loading services configuration:', error);
    }
}

function renderServices() {
    const servicesSection = document.getElementById('services-section');
    servicesSection.innerHTML = '';

    // Group services by the 'group' field
    const grouped = {};
    const ungrouped = [];

    servicesConfig.forEach(service => {
        if (service.group) {
            if (!grouped[service.group]) {
                grouped[service.group] = [];
            }
            grouped[service.group].push(service);
        } else {
            ungrouped.push(service);
        }
    });

    // Render ungrouped services first
    ungrouped.forEach(service => {
        const card = createServiceCard(service);
        servicesSection.appendChild(card);
    });

    // Render grouped services
    Object.keys(grouped).forEach(groupName => {
        const groupContainer = createServiceGroup(groupName, grouped[groupName]);
        servicesSection.appendChild(groupContainer);
    });
}

function createServiceCard(service, opts) {
    const onToggle = (opts && opts.onToggle) || (() => toggleService(service.id));
    const onDetails = (opts && opts.onDetails) || (() => showServiceDetails(service.id));

    const serviceCard = document.createElement('div');
    serviceCard.className = 'service-card';

    // Create service header
    const serviceHeader = document.createElement('div');
    serviceHeader.className = 'service-header';

    const serviceName = document.createElement('span');
    serviceName.className = 'service-name';
    serviceName.textContent = service.display_name;

    const statusIndicator = document.createElement('div');
    statusIndicator.className = 'status-indicator';
    statusIndicator.id = `${service.id}-indicator`;

    serviceHeader.appendChild(serviceName);
    serviceHeader.appendChild(statusIndicator);

    // Create status text
    const statusText = document.createElement('div');
    statusText.className = 'status-text';
    statusText.id = `${service.id}-status`;
    statusText.textContent = 'INITIALIZING...';

    // Create toggle container
    const toggleContainer = document.createElement('div');
    toggleContainer.className = 'toggle-container';

    // Button group for DETAILS (and optional LINK)
    const btnGroup = document.createElement('div');
    btnGroup.className = 'service-btn-group';

    const detailsBtn = document.createElement('button');
    detailsBtn.className = 'details-btn';
    detailsBtn.textContent = 'DETAILS';
    detailsBtn.onclick = onDetails;
    btnGroup.appendChild(detailsBtn);

    if (service.link_url) {
        const link = document.createElement('a');
        link.id = `${service.id}-link`;
        link.href = '#';
        link.target = '_blank';
        link.className = 'details-btn link-btn';
        link.style.textDecoration = 'none';
        link.textContent = 'LINK';
        btnGroup.appendChild(link);
    }

    // Create control toggle
    const toggleLabel = document.createElement('span');
    toggleLabel.className = 'toggle-label';
    toggleLabel.textContent = 'CONTROL';

    const toggleSwitch = document.createElement('div');
    toggleSwitch.className = 'toggle-switch';
    toggleSwitch.id = `${service.id}-toggle`;
    toggleSwitch.onclick = onToggle;

    const toggleSlider = document.createElement('div');
    toggleSlider.className = 'toggle-slider';

    toggleSwitch.appendChild(toggleSlider);
    toggleContainer.appendChild(toggleLabel);
    toggleContainer.appendChild(toggleSwitch);
    toggleContainer.appendChild(btnGroup);

    // Assemble the card
    serviceCard.appendChild(serviceHeader);
    serviceCard.appendChild(statusText);
    serviceCard.appendChild(toggleContainer);

    return serviceCard;
}

function createServiceGroup(groupName, services, prebuiltCards) {
    const group = document.createElement('div');
    group.className = 'automation-group'; // Reuse automation-group styles

    // Create group header
    const header = document.createElement('div');
    header.className = 'automation-group-header';

    const title = document.createElement('div');
    title.className = 'automation-group-title';

    const arrow = document.createElement('span');
    arrow.className = 'automation-group-arrow';
    arrow.textContent = '▼';

    const titleText = document.createElement('span');
    titleText.textContent = groupName;

    title.appendChild(arrow);
    title.appendChild(titleText);
    header.appendChild(title);

    // Create content container
    const content = document.createElement('div');
    content.className = 'automation-group-content';
    content.id = `service-group-${groupName.replace(/\s+/g, '-').toLowerCase()}`;

    // Add cards — either pre-built or created from service configs
    if (prebuiltCards) {
        prebuiltCards.forEach(card => content.appendChild(card));
    } else if (services) {
        services.forEach(service => {
            const card = createServiceCard(service);
            content.appendChild(card);
        });
    }

    // Add click handler for collapse/expand
    header.addEventListener('click', () => {
        toggleServiceGroup(groupName);
    });

    group.appendChild(header);
    group.appendChild(content);

    // Restore collapsed state from localStorage
    const isCollapsed = localStorage.getItem(`service-group-${groupName}-collapsed`) === 'true';
    if (isCollapsed) {
        arrow.classList.add('collapsed');
        content.classList.add('collapsed');
    }

    return group;
}

// Remote machine loading and rendering
async function loadAndRenderRemoteMachines() {
    try {
        const response = await fetch('/api/remote_machines');
        remoteMachinesConfig = await response.json();
        renderRemoteMachines();
    } catch (error) {
        console.error('Error loading remote machines:', error);
    }
}

function renderRemoteMachines() {
    // Remote machines live under the Devices section (appended after device
    // tiles, which are rendered first and clear the section).
    const servicesSection = document.getElementById('devices-section');

    const grouped = {};
    const ungrouped = [];

    remoteMachinesConfig.forEach(machine => {
        if (machine.group) {
            if (!grouped[machine.group]) grouped[machine.group] = [];
            grouped[machine.group].push(machine);
        } else {
            ungrouped.push(machine);
        }
    });

    ungrouped.forEach(machine => {
        const card = createServiceCard(machine, {
            onToggle: () => toggleRemoteMachine(machine.id),
            onDetails: () => showRemoteMachineDetails(machine.id),
        });
        servicesSection.appendChild(card);
    });

    Object.keys(grouped).forEach(groupName => {
        const cards = grouped[groupName].map(machine =>
            createServiceCard(machine, {
                onToggle: () => toggleRemoteMachine(machine.id),
                onDetails: () => showRemoteMachineDetails(machine.id),
            })
        );
        const groupContainer = createServiceGroup(groupName, null, cards);
        groupContainer.classList.add('device-group');
        servicesSection.appendChild(groupContainer);
    });
}

async function toggleRemoteMachine(machineId) {
    const toggle = document.getElementById(`${machineId}-toggle`);
    if (toggle.classList.contains('disabled') || toggle.classList.contains('pending')) return;

    const isActive = toggle.classList.contains('active');
    const action = isActive ? 'stop' : 'start';

    toggle.classList.add('disabled', 'pending');
    pendingRemoteMachineOps[machineId] = action;

    try {
        const response = await fetch(`/api/remote_machine/control/${machineId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action }),
        });
        const result = await response.json();
        if (!result.success) {
            delete pendingRemoteMachineOps[machineId];
            toggle.classList.remove('disabled', 'pending');
            showToast(`Failed to ${action} ${machineId}: ${result.error}`, 'error');
        }
    } catch (error) {
        delete pendingRemoteMachineOps[machineId];
        toggle.classList.remove('disabled', 'pending');
        showToast(`Failed to ${action} ${machineId}.`, 'error');
    }
}

async function showRemoteMachineDetails(machineId) {
    const modal = document.getElementById('serviceModal');
    const title = document.getElementById('modal-title');
    const output = document.getElementById('modal-output');

    title.textContent = `${machineId.toUpperCase()} STATUS`;
    output.textContent = 'Loading...';
    modal.style.display = 'block';

    try {
        const response = await fetch(`/api/remote_machine/details/${machineId}`);
        const data = await response.json();
        if (data.success) {
            output.textContent = data.output;
        } else {
            output.textContent = `ERROR: ${data.error}`;
        }
    } catch (error) {
        output.textContent = `ERROR: Failed to fetch details\n${error.message}`;
    }
}

function updateRemoteMachineUI(machineId, statusData) {
    const indicator = document.getElementById(`${machineId}-indicator`);
    const statusText = document.getElementById(`${machineId}-status`);
    const toggle = document.getElementById(`${machineId}-toggle`);

    if (!indicator || !statusText || !toggle) return;

    const isRunning = typeof statusData === 'boolean' ? statusData : statusData.running;

    // Clear pending when state matches expectation
    if (pendingRemoteMachineOps[machineId]) {
        const expectedRunning = pendingRemoteMachineOps[machineId] === 'start';
        if (isRunning === expectedRunning) {
            delete pendingRemoteMachineOps[machineId];
            toggle.classList.remove('pending');
            setTimeout(() => toggle.classList.remove('disabled'), 1500);
        }
    } else {
        toggle.classList.remove('pending', 'disabled');
    }

    // Smart-plug wattage, when the machine has a plug and a reading has landed.
    // Polled on a slower cadence than online status, so it may lag by ~15s.
    const watts = (statusData && typeof statusData === 'object') ? statusData.watts : null;
    const wattsStr = (typeof watts === 'number') ? ` (${watts.toFixed(1)} W)` : '';

    if (isRunning) {
        indicator.className = 'status-indicator green';
        statusText.textContent = `ONLINE${wattsStr}`;
        toggle.classList.add('active');
    } else {
        indicator.className = 'status-indicator red';
        statusText.textContent = `OFFLINE${wattsStr}`;
        toggle.classList.remove('active');
    }
}

// Handle service status update (from WebSocket or initial fetch)
function handleServiceStatusUpdate(status) {
    // Dynamically update all configured services
    servicesConfig.forEach(service => {
        if (status.hasOwnProperty(service.id)) {
            updateServiceUI(service.id, status[service.id]);
        }
    });

    // Update remote machines (status keys are prefixed with rm_)
    remoteMachinesConfig.forEach(machine => {
        const key = `rm_${machine.id}`;
        if (status.hasOwnProperty(key)) {
            updateRemoteMachineUI(machine.id, status[key]);
        }
    });

    updateInternetUI(status.internet);
}

// Fetch initial status (used on page load before WebSocket is ready)
async function fetchInitialStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();
        handleServiceStatusUpdate(status);
    } catch (error) {
        console.error('Error fetching initial status:', error);
    }
}

// Handle system stats update (from WebSocket or initial fetch)
function handleSystemStatsUpdate(stats) {
    // Guard against empty stats (cache not yet populated)
    if (!stats || Object.keys(stats).length === 0) {
        return;
    }

    // Update page title with hostname
    if (stats.hostname) {
        document.getElementById('hostname-title').textContent = stats.hostname;
    }

    // Update service links dynamically (e.g., qBittorrent Web UI)
    servicesConfig.forEach(service => {
        if (service.link_url) {
            const linkElement = document.getElementById(`${service.id}-link`);
            if (linkElement && stats.hostname) {
                linkElement.href = service.link_url.replace('{hostname}', stats.hostname);
            }
        }
    });

    // Update CPU
    if (stats.cpu_percent !== undefined) {
        document.getElementById('cpu-value').textContent = stats.cpu_percent + '%';
    }

    // Update per-core CPU bars
    if (stats.cpu_per_core) {
        updateCpuCores(stats.cpu_per_core);
    }

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
    if (stats.ram_percent !== undefined) {
        document.getElementById('ram-value').textContent = stats.ram_percent + '%';
        document.getElementById('ram-detail').textContent =
            `${stats.ram_used_gb} / ${stats.ram_total_gb} GB`;
        updateProgressBar('ram-progress', stats.ram_percent);
    }

    // Update Disk
    if (stats.disk_percent !== undefined) {
        document.getElementById('disk-value').textContent = stats.disk_percent + '%';
        document.getElementById('disk-detail').textContent =
            `${stats.disk_free_gb} GB FREE / ${stats.disk_total_gb} GB TOTAL`;
        document.getElementById('disk-mount').textContent = `MOUNT: ${stats.disk_mount}`;
        updateProgressBar('disk-progress', stats.disk_percent);
    }

    // Update Network
    if (stats.network_interface) {
        document.getElementById('network-interface').textContent =
            `INTERFACE: ${stats.network_interface}`;
        document.getElementById('upload-value').textContent = stats.upload_mbps + ' Mbps';
        document.getElementById('download-value').textContent = stats.download_mbps + ' Mbps';
    }

    // Update Network Status (hostname and IP)
    if (stats.hostname) {
        document.getElementById('hostname-detail').textContent = `HOSTNAME: ${stats.hostname}`;
        document.getElementById('ip-detail').textContent = `IP ADDRESS: ${stats.ip_address}`;
    }

    // Update Uptime
    if (stats.uptime) {
        document.getElementById('uptime-value').textContent = `UPTIME: ${stats.uptime}`;
    }

    // Update Uname
    if (stats.uname) {
        document.getElementById('uname-value').textContent = `KERNEL: ${stats.uname}`;
    }

    // Update Top CPU Processes
    if (stats.top_cpu_processes) {
        updateTopCpuProcesses(stats.top_cpu_processes);
    }
}

// Fetch initial system stats (used on page load before WebSocket is ready)
async function fetchInitialSystemStats() {
    try {
        const response = await fetch('/api/system');
        const stats = await response.json();
        handleSystemStatsUpdate(stats);
    } catch (error) {
        console.error('Error fetching initial system stats:', error);
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

        // Group automations by the 'group' field
        const grouped = {};
        const ungrouped = [];

        automations.forEach(auto => {
            if (auto.group) {
                if (!grouped[auto.group]) {
                    grouped[auto.group] = [];
                }
                grouped[auto.group].push(auto);
            } else {
                ungrouped.push(auto);
            }
        });

        // Render ungrouped automations first
        ungrouped.forEach(auto => {
            const card = createAutomationCard(auto);
            container.appendChild(card);
        });

        // Render grouped automations
        Object.keys(grouped).forEach(groupName => {
            const groupContainer = createAutomationGroup(groupName, grouped[groupName]);
            container.appendChild(groupContainer);
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
            <div style="display: flex; align-items: center; gap: 8px;">
                <span class="status-inline" id="${automation.name}-status">READY</span>
                <div class="status-indicator yellow" id="${automation.name}-indicator"></div>
            </div>
        </div>
        <div class="automation-args-container">
            <div style="display: flex; gap: 8px; align-items: center;">
                <input type="text" class="automation-args-input" id="${automation.name}-args" placeholder="Arguments (optional)" autocorrect="off" spellcheck="false" style="flex: 1;" value="${automation.args ? automation.args.replace(/"/g, '&quot;') : ''}">
                <button class="details-btn icon-btn" onclick="runAutomation('${automation.name}')" id="${automation.name}-btn">&#9658;</button>
            </div>
        </div>
        <div class="automation-output" id="${automation.name}-output" style="display: none;">
            <div class="output-header">
                <span class="output-label">OUTPUT:</span>
                <button class="clear-btn-compact" onclick="clearAutomationOutput('${automation.name}')" id="${automation.name}-clear-btn" style="display: none;">CLEAR</button>
            </div>
            <div class="modal-output" style="max-height: 150px;" id="${automation.name}-output-text"></div>
        </div>
    `;

    // Add double-click event listener to the output textbox after DOM insertion
    setTimeout(() => {
        const outputText = document.getElementById(`${automation.name}-output-text`);
        if (outputText) {
            outputText.addEventListener('dblclick', () => {
                openAutomationOutputModal(automation.name);
            });
        }

        // Add keyboard listeners to arguments input
        const argsInput = document.getElementById(`${automation.name}-args`);
        if (argsInput) {
            argsInput.addEventListener('keydown', (e) => {
                const name = automation.name;

                if (e.key === 'Enter') {
                    e.preventDefault();
                    runAutomation(name);
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    navigateAutomationHistory(name, argsInput, -1);
                } else if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    navigateAutomationHistory(name, argsInput, 1);
                }
            });
        }
    }, 0);

    return card;
}

function createAutomationGroup(groupName, automations) {
    const group = document.createElement('div');
    group.className = 'automation-group';

    // Create group header
    const header = document.createElement('div');
    header.className = 'automation-group-header';

    const title = document.createElement('div');
    title.className = 'automation-group-title';

    const arrow = document.createElement('span');
    arrow.className = 'automation-group-arrow';
    arrow.textContent = '▼';

    const titleText = document.createElement('span');
    titleText.textContent = groupName;

    title.appendChild(arrow);
    title.appendChild(titleText);
    header.appendChild(title);

    // Create content container
    const content = document.createElement('div');
    content.className = 'automation-group-content';
    content.id = `group-${groupName.replace(/\s+/g, '-').toLowerCase()}`;

    // Add automation cards to the group
    automations.forEach(auto => {
        const card = createAutomationCard(auto);
        content.appendChild(card);
    });

    // Add click handler for collapse/expand
    header.addEventListener('click', () => {
        toggleAutomationGroup(groupName);
    });

    group.appendChild(header);
    group.appendChild(content);

    // Restore collapsed state from localStorage
    const isCollapsed = localStorage.getItem(`group-${groupName}-collapsed`) === 'true';
    if (isCollapsed) {
        arrow.classList.add('collapsed');
        content.classList.add('collapsed');
    }

    return group;
}

function toggleAutomationGroup(groupName) {
    const groupId = `group-${groupName.replace(/\s+/g, '-').toLowerCase()}`;
    const content = document.getElementById(groupId);
    const arrow = content.previousElementSibling.querySelector('.automation-group-arrow');

    if (!content || !arrow) {
        console.error(`Group not found: ${groupName}`);
        return;
    }

    const isCurrentlyCollapsed = content.classList.contains('collapsed');

    if (isCurrentlyCollapsed) {
        // Expanding: Remove collapsed class
        content.classList.remove('collapsed');
        arrow.classList.remove('collapsed');
        // Don't set max-height at all - let it expand naturally
    } else {
        // Collapsing: Just add the collapsed class
        content.classList.add('collapsed');
        arrow.classList.add('collapsed');
    }

    // Save state to localStorage
    localStorage.setItem(`group-${groupName}-collapsed`, !isCurrentlyCollapsed);
}

function toggleServiceGroup(groupName) {
    const groupId = `service-group-${groupName.replace(/\s+/g, '-').toLowerCase()}`;
    const content = document.getElementById(groupId);
    const arrow = content.previousElementSibling.querySelector('.automation-group-arrow');

    if (!content || !arrow) {
        console.error(`Service group not found: ${groupName}`);
        return;
    }

    const isCurrentlyCollapsed = content.classList.contains('collapsed');

    if (isCurrentlyCollapsed) {
        // Expanding: Remove collapsed class
        content.classList.remove('collapsed');
        arrow.classList.remove('collapsed');
        // Don't set max-height at all - let it expand naturally
    } else {
        // Collapsing: Just add the collapsed class
        content.classList.add('collapsed');
        arrow.classList.add('collapsed');
    }

    // Save state to localStorage
    localStorage.setItem(`service-group-${groupName}-collapsed`, !isCurrentlyCollapsed);
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

function closeSettingsModal() {
    document.getElementById('settingsModal').style.display = 'none';
}

function openAutomationOutputModal(automationName) {
    console.log('openAutomationOutputModal called for:', automationName);

    const modal = document.getElementById('automationOutputModal');
    const title = document.getElementById('automation-modal-title');
    const output = document.getElementById('automation-modal-output');

    // Store which automation we're viewing
    currentExpandedAutomation = automationName;

    // Get config for display name
    const config = automationConfigs[automationName];
    title.textContent = config ? `${config.display_name} OUTPUT` : `${automationName.toUpperCase()} OUTPUT`;

    // Set initial content
    const currentOutput = automationClientOutput[automationName] || '';
    output.textContent = currentOutput;

    // Show modal first so the element is rendered
    modal.style.display = 'block';

    // Use requestAnimationFrame to ensure the modal is rendered before scrolling
    // This guarantees we're at the bottom when new content arrives
    requestAnimationFrame(() => {
        output.scrollTop = output.scrollHeight;
    });
}

function closeAutomationOutputModal() {
    console.log('closeAutomationOutputModal called');

    const modal = document.getElementById('automationOutputModal');
    modal.style.display = 'none';

    // Clear the tracked automation
    currentExpandedAutomation = null;
}

function updateProgressBar(id, percent) {
    const progressBar = document.getElementById(id);
    progressBar.style.width = percent + '%';

    // Calculate gradient color from green (0%) -> yellow (50%) -> red (100%)
    let color1, color2;

    if (percent <= 50) {
        // Green to Yellow gradient
        const ratio = percent / 50;
        const r = Math.round(0 + (255 * ratio));
        const g = Math.round(170 + (85 * ratio));
        const b = 43;
        color1 = `rgb(${r}, ${g}, ${b})`;
        color2 = `rgb(${Math.round(r * 0.8)}, ${Math.round(g * 0.8)}, ${Math.round(b * 0.8)})`;
    } else {
        // Yellow to Red gradient
        const ratio = (percent - 50) / 50;
        const r = 255;
        const g = Math.round(255 * (1 - ratio));
        const b = 43 * (1 - ratio);
        color1 = `rgb(${r}, ${g}, ${Math.round(b)})`;
        color2 = `rgb(${Math.round(r * 0.8)}, ${Math.round(g * 0.8)}, ${Math.round(b * 0.8)})`;
    }

    progressBar.className = 'progress-fill';
    progressBar.style.background = `linear-gradient(90deg, ${color1}, ${color2})`;
    progressBar.style.boxShadow = `0 0 10px ${color1}`;
}

function updateCpuCores(corePercentages) {
    const container = document.getElementById('cpu-cores-container');

    // Create core bars if they don't exist yet
    if (container.children.length === 0) {
        corePercentages.forEach((percent, index) => {
            const coreDiv = document.createElement('div');
            coreDiv.style.display = 'flex';
            coreDiv.style.alignItems = 'center';
            coreDiv.style.marginBottom = '3px';

            const label = document.createElement('div');
            label.className = 'stat-detail';
            label.style.fontSize = '0.7em';
            label.style.minWidth = '80px';
            label.style.marginRight = '8px';
            label.innerHTML = `C${index}: <span id="cpu-core-${index}-value">--</span>`;

            const progressBar = document.createElement('div');
            progressBar.className = 'progress-bar';
            progressBar.style.height = '10px'; // Half the normal height
            progressBar.style.flex = '1';

            const progressFill = document.createElement('div');
            progressFill.className = 'progress-fill';
            progressFill.id = `cpu-core-${index}-progress`;

            progressBar.appendChild(progressFill);
            coreDiv.appendChild(label);
            coreDiv.appendChild(progressBar);
            container.appendChild(coreDiv);
        });
    }

    // Update each core's progress bar
    corePercentages.forEach((percent, index) => {
        const valueElement = document.getElementById(`cpu-core-${index}-value`);
        const progressElement = document.getElementById(`cpu-core-${index}-progress`);

        if (valueElement && progressElement) {
            valueElement.textContent = percent.toFixed(1) + '%';
            progressElement.style.width = percent + '%';

            // Calculate gradient color from green (0%) -> yellow (50%) -> red (100%)
            let color1, color2;

            if (percent <= 50) {
                // Green to Yellow gradient
                const ratio = percent / 50;
                const r = Math.round(0 + (255 * ratio));
                const g = Math.round(170 + (85 * ratio));
                const b = 43;
                color1 = `rgb(${r}, ${g}, ${b})`;
                color2 = `rgb(${Math.round(r * 0.8)}, ${Math.round(g * 0.8)}, ${Math.round(b * 0.8)})`;
            } else {
                // Yellow to Red gradient
                const ratio = (percent - 50) / 50;
                const r = 255;
                const g = Math.round(255 * (1 - ratio));
                const b = 43 * (1 - ratio);
                color1 = `rgb(${r}, ${g}, ${Math.round(b)})`;
                color2 = `rgb(${Math.round(r * 0.8)}, ${Math.round(g * 0.8)}, ${Math.round(b * 0.8)})`;
            }

            progressElement.className = 'progress-fill';
            progressElement.style.background = `linear-gradient(90deg, ${color1}, ${color2})`;
            progressElement.style.boxShadow = `0 0 10px ${color1}`;
        }
    });
}

function formatMemory(bytes) {
    if (!bytes) return '';
    const gb = bytes / (1024 * 1024 * 1024);
    if (gb >= 1) {
        return `${gb.toFixed(2)} GB`;
    } else {
        const mb = bytes / (1024 * 1024);
        return `${mb.toFixed(1)} MB`;
    }
}

function updateTopCpuProcesses(processes) {
    const container = document.getElementById('top-cpu-processes');
    if (!container) return;

    // Clear container
    container.innerHTML = '';

    // If no processes or empty array, show placeholder
    if (!processes || processes.length === 0) {
        const placeholder = document.createElement('div');
        placeholder.className = 'stat-detail';
        placeholder.textContent = '--';
        container.appendChild(placeholder);
        return;
    }

    // Create a row for each process
    processes.forEach(proc => {
        const row = document.createElement('div');
        row.className = 'stat-detail';
        row.style.display = 'flex';
        row.style.justifyContent = 'space-between';
        row.style.marginBottom = '3px';

        // Truncate process name if too long (max 20 chars)
        let displayName = proc.name;
        if (displayName.length > 20) {
            displayName = displayName.substring(0, 17) + '...';
        }

        const nameSpan = document.createElement('span');
        nameSpan.textContent = displayName;
        nameSpan.title = proc.name; // Full name on hover

        const cpuSpan = document.createElement('span');
        cpuSpan.textContent = proc.cpu_percent.toFixed(1) + '%';
        cpuSpan.style.marginLeft = '10px';

        row.appendChild(nameSpan);
        row.appendChild(cpuSpan);
        container.appendChild(row);
    });
}

function updateServiceUI(service, statusData) {
    const indicator = document.getElementById(`${service}-indicator`);
    const statusText = document.getElementById(`${service}-status`);
    const toggle = document.getElementById(`${service}-toggle`);

    // Handle both old format (boolean) and new format (object)
    const isRunning = typeof statusData === 'boolean' ? statusData : statusData.running;
    const memoryBytes = typeof statusData === 'object' ? statusData.memory_bytes : null;

    // Clear pending only when the state matches what was requested
    if (pendingServiceOps[service]) {
        const expectedRunning = pendingServiceOps[service] === 'start';
        if (isRunning === expectedRunning) {
            delete pendingServiceOps[service];
            toggle.classList.remove('pending');
            // Brief cooldown before re-enabling to prevent rapid toggling
            setTimeout(() => toggle.classList.remove('disabled'), 1500);
        }
        // Otherwise keep pulsing — state hasn't changed yet
    } else {
        toggle.classList.remove('pending', 'disabled');
    }

    if (isRunning) {
        indicator.className = 'status-indicator green';
        const memoryStr = formatMemory(memoryBytes);
        statusText.textContent = memoryStr ? `ONLINE - ${memoryStr}` : 'ONLINE';
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

    if (toggle.classList.contains('disabled') || toggle.classList.contains('pending')) return;

    const isActive = toggle.classList.contains('active');
    const action = isActive ? 'stop' : 'start';

    toggle.classList.add('disabled', 'pending');
    pendingServiceOps[service] = action;

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
            // Fetch updated status for faster feedback.
            // Pending state stays until updateServiceUI sees the expected state.
            fetchInitialStatus();
        } else {
            delete pendingServiceOps[service];
            toggle.classList.remove('disabled', 'pending');
            showToast(`Failed to ${action} ${service}: ${result.error}`, 'error');
        }
    } catch (error) {
        delete pendingServiceOps[service];
        toggle.classList.remove('disabled', 'pending');
        showToast(`Failed to ${action} ${service}. Please check your connection.`, 'error');
    }
}

// ============================================================
// Devices — external networked appliances (media players, cameras, ...).
// A thin pluggable framework: each device has a `type` that maps to a renderer
// and an updater. BluOS is the first type; add a type here + a backend handler
// to support a new kind of device.
// ============================================================
let devicesConfig = [];

// Transport icons with the U+FE0E text-presentation selector so iOS renders the
// monochrome/blocky glyphs (like desktop) instead of colorful emoji.
const ICON_PREV = '⏮︎';   // ⏮ + text selector
const ICON_NEXT = '⏭︎';   // ⏭ + text selector
const ICON_PLAY = '▶︎';   // ▶ + text selector
const ICON_PAUSE = '⏸︎';  // ⏸ + text selector

// Per-device volume slew state for the rate-limited ("lowpass") slider:
//   applied  = volume actually sent to / echoed from the device
//   intended = latest raw slider position from the user
//   dragging = true between drag-start and release
//   sending  = true while a volume POST is in flight (keeps steps in lockstep)
const deviceVolumeState = {};

function deviceById(id) {
    return devicesConfig.find(d => d.id === id);
}

function formatTime(totalSeconds) {
    const s = Math.max(0, Math.floor(totalSeconds || 0));
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, '0')}`;
}

async function loadAndRenderDevices() {
    try {
        const response = await fetch('/api/devices');
        devicesConfig = await response.json();
        renderDevices();
    } catch (error) {
        console.error('Error loading devices:', error);
    }
}

function renderDevices() {
    const section = document.getElementById('devices-section');
    if (!section) return;
    // Appends into #devices-section (cleared once by the caller). Devices are
    // grouped by their `group` field into named collapsible groups (e.g.
    // "Music Players"), each laying its tiles out in a grid via `.device-group`.
    const grouped = {};
    const ungrouped = [];
    devicesConfig.forEach(device => {
        if (device.group) (grouped[device.group] = grouped[device.group] || []).push(device);
        else ungrouped.push(device);
    });

    ungrouped.forEach(device => section.appendChild(buildDeviceTile(device)));

    Object.keys(grouped).forEach(groupName => {
        const cards = grouped[groupName].map(buildDeviceTile);
        const group = createServiceGroup(groupName, null, cards);
        group.classList.add('device-group');
        section.appendChild(group);
    });
}

// Hide the DEVICES separator + section entirely when nothing is registered
// (no media devices and no remote machines).
function updateDevicesSectionVisibility() {
    const hasAny = (devicesConfig && devicesConfig.length > 0) ||
                   (remoteMachinesConfig && remoteMachinesConfig.length > 0);
    const separator = document.querySelector('.separator-devices');
    const section = document.getElementById('devices-section');
    if (separator) separator.classList.toggle('empty-hidden', !hasAny);
    if (section) section.classList.toggle('empty-hidden', !hasAny);
}

// Renderer / updater registries — keyed by device `type`.
const DEVICE_RENDERERS = { bluos: renderBluosTile };
const DEVICE_UPDATERS = { bluos: updateBluosTile };

function buildDeviceTile(device) {
    const renderer = DEVICE_RENDERERS[device.type];
    if (renderer) return renderer(device);
    // Fallback for an unknown/unsupported device type
    const card = document.createElement('div');
    card.className = 'device-card';
    card.textContent = `${device.display_name} (unsupported type: ${device.type})`;
    return card;
}

function renderBluosTile(device) {
    const id = device.id;
    const card = document.createElement('div');
    card.className = 'device-card media-tile';
    card.id = `device-${id}`;

    // Header: name + status dot. Uses media-specific classes (NOT service-header
    // / service-name) so compact-mode's .service-header { flex:0 0 100% } rule —
    // which means full *height* in our column flex — can't break the layout.
    const header = document.createElement('div');
    header.className = 'media-header';
    const name = document.createElement('span');
    name.className = 'media-name';
    name.textContent = device.display_name;
    const indicator = document.createElement('div');
    indicator.className = 'status-indicator';
    indicator.id = `device-${id}-indicator`;
    header.appendChild(name);
    header.appendChild(indicator);

    // Album art
    const artWrap = document.createElement('div');
    artWrap.className = 'media-art';
    const art = document.createElement('img');
    art.id = `device-${id}-art`;
    art.alt = 'Album art';
    art.style.display = 'none';
    artWrap.appendChild(art);

    // Track info
    const title = document.createElement('div');
    title.className = 'media-title';
    title.id = `device-${id}-title`;
    title.textContent = '—';
    const artist = document.createElement('div');
    artist.className = 'media-artist';
    artist.id = `device-${id}-artist`;
    artist.textContent = '';

    // Seek bar
    const seekRow = document.createElement('div');
    seekRow.className = 'media-seek-row';
    const elapsed = document.createElement('span');
    elapsed.className = 'media-time';
    elapsed.id = `device-${id}-elapsed`;
    elapsed.textContent = '0:00';
    const seek = document.createElement('input');
    seek.type = 'range';
    seek.className = 'media-seek';
    seek.id = `device-${id}-seek`;
    seek.min = '0';
    seek.max = '100';
    seek.value = '0';
    const total = document.createElement('span');
    total.className = 'media-time';
    total.id = `device-${id}-total`;
    total.textContent = '0:00';
    seekRow.appendChild(elapsed);
    seekRow.appendChild(seek);
    seekRow.appendChild(total);

    // While the user drags the seek bar, suppress status overwrites; commit on release.
    const seekStart = () => { seek.dataset.seeking = '1'; };
    seek.addEventListener('pointerdown', seekStart);
    seek.addEventListener('touchstart', seekStart, { passive: true });
    seek.addEventListener('change', () => {
        seek.dataset.seeking = '';
        deviceCommand(id, 'seek', parseInt(seek.value, 10));
    });

    // Transport controls
    const controls = document.createElement('div');
    controls.className = 'media-controls';
    const prevBtn = document.createElement('button');
    prevBtn.className = 'media-btn';
    prevBtn.textContent = ICON_PREV;
    prevBtn.onclick = () => deviceCommand(id, 'prev');
    const playBtn = document.createElement('button');
    playBtn.className = 'media-btn media-play';
    playBtn.id = `device-${id}-play`;
    setPlayIcon(playBtn, false);
    playBtn.onclick = () => toggleBluosPlay(id);
    const nextBtn = document.createElement('button');
    nextBtn.className = 'media-btn';
    nextBtn.textContent = ICON_NEXT;
    nextBtn.onclick = () => deviceCommand(id, 'next');
    controls.appendChild(prevBtn);
    controls.appendChild(playBtn);
    controls.appendChild(nextBtn);

    // Volume (rate-limited / lowpass, capped at volume_max)
    const volRow = document.createElement('div');
    volRow.className = 'media-volume-row';
    const volIcon = document.createElement('span');
    volIcon.className = 'media-vol-icon';
    volIcon.textContent = '🔊';
    const volume = document.createElement('input');
    volume.type = 'range';
    volume.className = 'media-volume';
    volume.id = `device-${id}-volume`;
    volume.min = '0';
    volume.max = String(device.volume_max != null ? device.volume_max : 60);
    volume.value = '0';
    const volVal = document.createElement('span');
    volVal.className = 'media-vol-val';
    volVal.id = `device-${id}-vol-val`;
    volVal.textContent = '0';
    volRow.appendChild(volIcon);
    volRow.appendChild(volume);
    volRow.appendChild(volVal);

    setupVolumeSlew(device, volume, volVal);

    card.appendChild(header);
    card.appendChild(artWrap);
    card.appendChild(title);
    card.appendChild(artist);
    card.appendChild(seekRow);
    card.appendChild(controls);
    card.appendChild(volRow);
    return card;
}

// Rate-limited ("lowpass") volume — "release stops the climb".
// The thumb crawls under the finger at a capped step rate while dragging and
// freezes on release, so an errant fling can't blast the volume.
function setupVolumeSlew(device, slider, valLabel) {
    const id = device.id;
    const state = {
        applied: 0,
        intended: 0,
        dragging: false,
        sending: false,
        slider,
        valLabel,
        maxStep: device.volume_max_step || 2,
    };
    deviceVolumeState[id] = state;

    const startDrag = () => { state.dragging = true; };
    slider.addEventListener('pointerdown', startDrag);
    slider.addEventListener('touchstart', startDrag, { passive: true });

    slider.addEventListener('input', () => {
        // Capture the target only; the tick decides how fast `applied` follows.
        state.intended = parseInt(slider.value, 10);
    });

    const endDrag = () => {
        // Freeze the climb where it reached.
        state.intended = state.applied;
        state.dragging = false;
        slider.value = state.applied;
        valLabel.textContent = state.applied;
    };
    slider.addEventListener('pointerup', endDrag);
    slider.addEventListener('touchend', endDrag);
    slider.addEventListener('mouseup', endDrag);

    const tickMs = device.volume_tick_ms || 250;
    state.tick = setInterval(() => {
        if (!state.dragging || state.sending) return;
        if (state.applied === state.intended) return;
        const dir = state.intended > state.applied ? 1 : -1;
        const step = Math.min(state.maxStep, Math.abs(state.intended - state.applied));
        state.applied += dir * step;
        slider.value = state.applied;           // thumb crawls under the finger
        valLabel.textContent = state.applied;
        sendVolume(id);
    }, tickMs);
}

function sendVolume(id) {
    const state = deviceVolumeState[id];
    if (!state || state.sending) return;
    state.sending = true;
    const value = state.applied;
    fetch(`/api/device/${id}/command`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'volume', value }),
    }).catch(() => {}).finally(() => { state.sending = false; });
}

// Optimistic playback state so play/pause feels instant. We flip the icon
// immediately and ignore contradicting status polls for a short hold window
// (the device can take a moment to report its new state).
const devicePlayback = {}; // id -> { playing: bool, holdUntil: number }

// Set the play/pause glyph. The glyph lives in an inner span so the play
// triangle (visually weighted left) can be optically nudged down-right via the
// `.is-play` class without moving the circular button border.
function setPlayIcon(playBtn, playing) {
    if (!playBtn) return;
    let g = playBtn.querySelector('.media-glyph');
    if (!g) {
        playBtn.textContent = '';
        g = document.createElement('span');
        g.className = 'media-glyph';
        playBtn.appendChild(g);
    }
    g.textContent = playing ? ICON_PAUSE : ICON_PLAY;
    playBtn.classList.toggle('is-play', !playing);
}

function setBluosPlaying(id, playing) {
    setPlayIcon(document.getElementById(`device-${id}-play`), playing);
    const indicator = document.getElementById(`device-${id}-indicator`);
    if (indicator) indicator.className = 'status-indicator ' + (playing ? 'green' : 'yellow');
}

function toggleBluosPlay(id) {
    const st = devicePlayback[id] || (devicePlayback[id] = { playing: false, holdUntil: 0 });
    const desired = !st.playing;
    st.playing = desired;
    st.holdUntil = Date.now() + 4000;       // hold optimistic state briefly
    setBluosPlaying(id, desired);           // instant feedback, no server wait
    // Explicit play/pause (not toggle) so the device acts in a single round-trip.
    deviceCommand(id, desired ? 'play' : 'pause');
}

async function deviceCommand(id, action, value) {
    try {
        const body = { action };
        if (value !== undefined) body.value = value;
        const response = await fetch(`/api/device/${id}/command`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        const result = await response.json();
        if (result && result.success) {
            if (result.status) updateDeviceTile(id, result.status); // fast feedback
        } else {
            showToast(`Device ${id}: ${(result && result.error) || 'command failed'}`, 'error');
        }
    } catch (error) {
        showToast(`Device ${id}: command failed`, 'error');
    }
}

// Set text that gently scrolls back and forth (ping-pong marquee) when it's
// wider than its container; otherwise it stays centered. Re-runs only when the
// text actually changes, so status polls don't restart the animation.
function setScrollingText(el, text) {
    text = text || '';
    let inner = el.querySelector('.media-marquee');
    if (!inner) {
        el.textContent = '';
        inner = document.createElement('span');
        inner.className = 'media-marquee';
        el.appendChild(inner);
    }
    if (inner.dataset.text === text) return; // unchanged — keep current animation
    inner.dataset.text = text;
    inner.textContent = text;
    if (inner._anim) { inner._anim.cancel(); inner._anim = null; }
    inner.style.transform = 'none';
    requestAnimationFrame(() => {
        const overflow = inner.scrollWidth - el.clientWidth;
        if (overflow > 4 && typeof inner.animate === 'function') {
            el.style.textAlign = 'left';
            const pxPerSec = 28;                 // gentle speed
            const travel = Math.max(700, (overflow / pxPerSec) * 1000);
            const pause = 1400;                  // dwell at each end
            const total = (travel + pause) * 2;
            const at = (t) => t / total;
            inner._anim = inner.animate([
                { transform: 'translateX(0)', offset: 0 },
                { transform: 'translateX(0)', offset: at(pause) },
                { transform: `translateX(${-overflow}px)`, offset: at(pause + travel) },
                { transform: `translateX(${-overflow}px)`, offset: at(pause + travel + pause) },
                { transform: 'translateX(0)', offset: 1 },
            ], { duration: total, iterations: Infinity, easing: 'linear' });
        } else {
            el.style.textAlign = 'center';
        }
    });
}

function updateDeviceTile(id, status) {
    const device = deviceById(id);
    if (!device) return;
    const updater = DEVICE_UPDATERS[device.type];
    if (updater) updater(id, status, device);
}

function handleDeviceStatusUpdate(statusMap) {
    if (!statusMap) return;
    Object.keys(statusMap).forEach(id => updateDeviceTile(id, statusMap[id]));
}

function updateBluosTile(id, s) {
    const indicator = document.getElementById(`device-${id}-indicator`);
    if (!indicator) return; // tile not rendered yet
    const titleEl = document.getElementById(`device-${id}-title`);
    const artistEl = document.getElementById(`device-${id}-artist`);
    const playBtn = document.getElementById(`device-${id}-play`);
    const seek = document.getElementById(`device-${id}-seek`);
    const elapsed = document.getElementById(`device-${id}-elapsed`);
    const total = document.getElementById(`device-${id}-total`);
    const art = document.getElementById(`device-${id}-art`);
    const volume = document.getElementById(`device-${id}-volume`);
    const volVal = document.getElementById(`device-${id}-vol-val`);

    if (!s || s.online === false) {
        indicator.className = 'status-indicator red';
        if (titleEl) titleEl.textContent = 'OFFLINE';
        if (artistEl) artistEl.textContent = '';
        setPlayIcon(playBtn, false);
        return;
    }

    // Respect the optimistic play/pause hold so a stale poll can't revert the
    // icon right after a click; otherwise sync to the device's reported state.
    const pb = devicePlayback[id] || (devicePlayback[id] = { playing: s.playing, holdUntil: 0 });
    let playing = s.playing;
    if (Date.now() < pb.holdUntil) {
        playing = pb.playing;
    } else {
        pb.playing = s.playing;
    }

    indicator.className = 'status-indicator ' + (playing ? 'green' : 'yellow');
    if (titleEl) setScrollingText(titleEl, s.title || '—');
    if (artistEl) setScrollingText(artistEl, [s.artist, s.album].filter(Boolean).join(' — '));
    setPlayIcon(playBtn, playing);

    // Seek bar — don't fight an active drag. Disable when the source/track
    // doesn't support seeking (BluOS reports canSeek=0).
    if (seek) {
        const seekable = s.can_seek !== false;
        seek.disabled = !seekable;
        if (seek.dataset.seeking !== '1') {
            const totlen = s.totlen || 0;
            const secs = s.secs || 0;
            seek.max = String(totlen || 100);
            seek.value = String(totlen ? Math.min(secs, totlen) : secs);
            if (elapsed) elapsed.textContent = formatTime(secs);
            if (total) total.textContent = formatTime(totlen);
        }
    }

    // Album art — only swap when the track changes (avoids reload flicker)
    if (art) {
        const trackKey = `${s.title || ''}|${s.album || ''}|${s.image || ''}`;
        if (art.dataset.trackKey !== trackKey) {
            art.dataset.trackKey = trackKey;
            if (s.image) {
                art.src = `/api/device/${id}/art?ts=${encodeURIComponent(trackKey)}`;
                art.style.display = '';
            } else {
                art.removeAttribute('src');
                art.style.display = 'none';
            }
        }
    }

    // Volume — reflect the device value only when the user isn't controlling it
    const vstate = deviceVolumeState[id];
    if (volume && vstate && !vstate.dragging && !vstate.sending) {
        const v = s.volume != null ? s.volume : 0;
        vstate.applied = v;
        vstate.intended = v;
        volume.value = String(v);
        if (volVal) volVal.textContent = String(v);
    }
}

async function fetchInitialDeviceStatus() {
    try {
        const response = await fetch('/api/devices/status');
        const status = await response.json();
        handleDeviceStatusUpdate(status);
    } catch (error) {
        console.error('Error fetching device status:', error);
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

// The WebSocket can go zombie after sleep / NAT timeout / background-tab
// throttling — socket.io still reads `connected` but no messages flow.
// On tab focus, pull fresh state over HTTP (what a manual refresh does).
document.addEventListener('visibilitychange', () => {
    if (document.visibilityState !== 'visible') return;
    fetchInitialStatus();
    fetchInitialSystemStats();
    fetchInitialDeviceStatus();
    if (socket.disconnected) socket.connect();
});

socket.on('automation_update', (data) => {
    console.log('Received automation update:', data);
    updateAutomationUI(data.automation, data.state);
});

// Handle system stats pushed from server
socket.on('system_stats', (stats) => {
    handleSystemStatsUpdate(stats);
});

// Handle service status pushed from server
socket.on('service_status', (status) => {
    handleServiceStatusUpdate(status);
});

// Handle device status (media players, etc.) pushed from server
socket.on('device_status', (status) => {
    handleDeviceStatusUpdate(status);
});

socket.on('remote_machine_progress', (data) => {
    const statusText = document.getElementById(`${data.machine_id}-status`);
    if (statusText) {
        statusText.textContent = data.message;
    }
});

// Helper function to check if a scrollable element is at or near the bottom
function isScrolledToBottom(element, threshold = 5) {
    if (!element) return false;
    // Check if the element is scrolled to within 'threshold' pixels of the bottom
    return element.scrollHeight - element.scrollTop - element.clientHeight <= threshold;
}

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

                // Check if we should auto-scroll (before appending new content)
                const shouldScroll = isScrolledToBottom(outputText);

                // Append new output
                automationClientOutput[automationName] += state.output;

                // Update display
                outputDiv.style.display = 'block';
                outputText.textContent = automationClientOutput[automationName];

                // Only scroll to bottom if already at bottom
                // Use requestAnimationFrame to ensure content is rendered before scrolling (fixes mobile browsers)
                if (shouldScroll) {
                    requestAnimationFrame(() => {
                        outputText.scrollTop = outputText.scrollHeight;
                    });
                }

                // If this automation is currently shown in the fullscreen modal, update it too
                if (currentExpandedAutomation === automationName) {
                    const modalOutput = document.getElementById('automation-modal-output');
                    if (modalOutput) {
                        // Check if modal should auto-scroll (before appending)
                        const shouldScrollModal = isScrolledToBottom(modalOutput);

                        modalOutput.textContent = automationClientOutput[automationName];

                        // Only scroll modal to bottom if already at bottom
                        if (shouldScrollModal) {
                            requestAnimationFrame(() => {
                                modalOutput.scrollTop = modalOutput.scrollHeight;
                            });
                        }
                    }
                }
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

                // If this automation is currently shown in the fullscreen modal, update it too
                if (currentExpandedAutomation === automationName) {
                    const modalOutput = document.getElementById('automation-modal-output');
                    if (modalOutput) {
                        modalOutput.textContent = state.output;
                        modalOutput.scrollTop = modalOutput.scrollHeight;
                    }
                }
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
        btn.textContent = '\u25A0';
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
        btn.textContent = '\u25B6';
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
            statusText.textContent = state.completed_at ? `COMPLETED -- ${state.completed_at}` : 'COMPLETED';
        } else if (state.return_code === -999) {
            indicator.className = 'status-indicator yellow';
            statusText.textContent = state.completed_at ? `CANCELLED -- ${state.completed_at}` : 'CANCELLED';
        } else {
            indicator.className = 'status-indicator red';
            statusText.textContent = state.completed_at ? `FAILED -- ${state.completed_at}` : 'FAILED';
        }
    }
}

// Navigate through command history for automation args input
function navigateAutomationHistory(automationName, inputElement, direction) {
    // Initialize history for this automation if needed
    if (!automationCommandHistory[automationName]) {
        automationCommandHistory[automationName] = [];
    }

    const history = automationCommandHistory[automationName];
    if (history.length === 0) return;

    // Initialize index if needed (-1 means at "new command" position)
    if (automationHistoryIndex[automationName] === undefined) {
        automationHistoryIndex[automationName] = -1;
    }

    const currentIndex = automationHistoryIndex[automationName];

    // Going up (back in history)
    if (direction === -1) {
        // Save pending input when first entering history
        if (currentIndex === -1) {
            automationPendingInput[automationName] = inputElement.value;
        }

        // Move back in history (newer items are at end, older at start)
        const newIndex = currentIndex === -1 ? history.length - 1 : Math.max(0, currentIndex - 1);
        automationHistoryIndex[automationName] = newIndex;
        inputElement.value = history[newIndex];
    }
    // Going down (forward in history)
    else if (direction === 1) {
        if (currentIndex === -1) return; // Already at newest position

        const newIndex = currentIndex + 1;

        if (newIndex >= history.length) {
            // Back to "new command" position - restore pending input
            automationHistoryIndex[automationName] = -1;
            inputElement.value = automationPendingInput[automationName] || '';
        } else {
            automationHistoryIndex[automationName] = newIndex;
            inputElement.value = history[newIndex];
        }
    }

    // Move cursor to end of input
    inputElement.selectionStart = inputElement.selectionEnd = inputElement.value.length;
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

    // Get arguments from input field
    const argsInput = document.getElementById(`${automationName}-args`);
    const args = argsInput ? argsInput.value.trim() : '';

    // Save to command history if non-empty
    if (args) {
        if (!automationCommandHistory[automationName]) {
            automationCommandHistory[automationName] = [];
        }
        const history = automationCommandHistory[automationName];
        // Avoid duplicates at the end
        if (history.length === 0 || history[history.length - 1] !== args) {
            history.push(args);
        }
    }
    // Reset history navigation state
    automationHistoryIndex[automationName] = -1;
    automationPendingInput[automationName] = '';

    // Disable button temporarily
    btn.disabled = true;
    btn.textContent = '\u25B6';

    try {
        const response = await fetch(`/api/automation/${automationName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ args: args })
        });

        if (!response.ok) {
            // Server returned an error status (4xx/5xx). Try to parse the JSON body
            // for a meaningful error message; fall through to generic toast on failure.
            try {
                const result = await response.json();
                showToast(result.error || `Server error (${response.status})`, 'error');
            } catch {
                showToast(`Server error (${response.status})`, 'error');
            }
            btn.disabled = false;
            btn.textContent = '\u25B6';
            return;
        }

        const result = await response.json();

        if (!result.success) {
            showToast(result.error || 'Failed to start automation', 'error');
            btn.disabled = false;
            btn.textContent = '\u25B6';
        }
        // If successful, the WebSocket will handle updating the UI
    } catch (error) {
        // Network error — the server may have received the request but the response
        // was lost (stale keep-alive, eventlet hiccup, etc.). Wait briefly then check
        // the actual server state before showing an error to the user.
        // Button stays in "STARTING..." during this window — the WebSocket handler
        // will correct it once server state is confirmed either way.
        console.warn('Fetch failed for runAutomation, will verify server state:', error.message);

        await new Promise(resolve => setTimeout(resolve, RUN_AUTOMATION_RETRY_DELAY_MS));

        try {
            const statusResp = await fetch(`/api/automation/${automationName}/status`);
            const status = await statusResp.json();
            if (status.running) {
                // Automation IS running — the original POST succeeded, only the HTTP
                // response was lost. WebSocket will handle the UI from here.
                console.log('Automation started despite fetch error — server confirmed running');
                return;
            }
            if (status.return_code !== null) {
                // Automation is not running but has a return code. Two possibilities:
                //   (a) Our POST succeeded, the automation ran and already finished (<2s)
                //   (b) Stale return_code from a *previous* run; our POST never arrived
                // We can't distinguish these without tracking job_id, so reset the button
                // to a safe state and suppress the error toast. In case (b) the user will
                // simply click run again. In case (a) the WebSocket already updated the UI.
                console.log('Automation not running but has return_code=%s — resetting button', status.return_code);
                btn.disabled = false;
                btn.textContent = '\u25B6';
                return;
            }
        } catch (statusError) {
            // Status check also failed — genuine connectivity problem
            console.error('Status check also failed:', statusError.message);
        }

        // If we get here, the automation genuinely did not start (return_code is null,
        // meaning it was never run or was reset to initial state)
        showToast('Failed to start automation. Please check your connection and try again.', 'error');
        btn.disabled = false;
        btn.textContent = '\u25B6';
    }
}

async function cancelAutomation(automationName) {
    console.log('cancelAutomation called for:', automationName);
    const btn = document.getElementById(`${automationName}-btn`);

    btn.disabled = true;
    btn.textContent = '\u25A0';

    try {
        console.log('Sending cancel request to:', `/api/automation/${automationName}/cancel`);
        const response = await fetch(`/api/automation/${automationName}/cancel`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            }
        });

        console.log('Cancel response status:', response.status);

        if (!response.ok) {
            try {
                const result = await response.json();
                showToast(result.error || `Server error (${response.status})`, 'error');
            } catch {
                showToast(`Server error (${response.status})`, 'error');
            }
            // Re-enable the cancel button so user can retry — don't reset to play
            // state since the automation may still be running on the server.
            btn.disabled = false;
            btn.textContent = '\u25A0';
            return;
        }

        const result = await response.json();
        console.log('Cancel result:', result);

        if (!result.success) {
            console.error('Cancel failed:', result.error);
            showToast(result.error || 'Failed to cancel automation', 'error');
            // Re-enable the cancel button so user can retry
            btn.disabled = false;
            btn.textContent = '\u25A0';
        }
        // If successful, the WebSocket will handle updating the UI
    } catch (error) {
        // Network error — wait briefly then check if the automation actually stopped
        console.warn('Fetch failed for cancelAutomation, will verify server state:', error.message);

        await new Promise(resolve => setTimeout(resolve, CANCEL_AUTOMATION_RETRY_DELAY_MS));

        try {
            const statusResp = await fetch(`/api/automation/${automationName}/status`);
            const status = await statusResp.json();
            if (!status.running) {
                // Automation is NOT running — cancel effectively succeeded (or it
                // finished on its own). WebSocket will handle the UI from here.
                console.log('Automation stopped despite fetch error — server confirmed not running');
                return;
            }
        } catch (statusError) {
            console.error('Status check also failed:', statusError.message);
        }

        // Cancel failed — re-enable the button so user can retry. Keep it in
        // cancel state since the automation is likely still running.
        showToast('Failed to cancel automation. Please try again.', 'error');
        btn.disabled = false;
        btn.textContent = '\u25A0';
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
    const sections = ['services', 'devices', 'automations', 'stats'];

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

// Theme color functions
function hexToRgb(hex) {
    const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : null;
}

function applyColors(foregroundColor, backgroundColor, groupColor) {
    const fgRgb = hexToRgb(foregroundColor);
    const bgRgb = hexToRgb(backgroundColor);

    if (!fgRgb || !bgRgb) return;

    // Calculate darker shade for foreground (80% brightness for dimmed text like CPU temp)
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

    // Set background color for matrix animation
    document.documentElement.style.setProperty('--background-color', backgroundColor);

    // Set group color if provided
    if (groupColor) {
        const groupRgb = hexToRgb(groupColor);
        if (groupRgb) {
            document.documentElement.style.setProperty('--group-color', groupColor);
            document.documentElement.style.setProperty('--group-color-rgb', `${groupRgb.r}, ${groupRgb.g}, ${groupRgb.b}`);
        }
    }

    // Update matrix canvas color
    updateMatrixColor(backgroundColor);
}

function updateMatrixColor(color) {
    // The matrix drawing function will use this color
    window.matrixColor = color;
}

function enableMatrixEffect() {
    canvas.style.display = 'block';
    // Start matrix animation if not already running
    const matrixAnimationRate = parseInt(localStorage.getItem('matrixAnimationRate')) || 120;
    if (matrixInterval) {
        clearInterval(matrixInterval);
    }
    matrixInterval = setInterval(draw, matrixAnimationRate);
}

function disableMatrixEffect() {
    canvas.style.display = 'none';
    // Stop matrix animation
    if (matrixInterval) {
        clearInterval(matrixInterval);
        matrixInterval = null;
    }
}

// Settings modal functions
async function openSettingsModal() {
    const modal = document.getElementById('settingsModal');
    const statusUpdateRate = document.getElementById('status-update-rate');
    const systemStatsUpdateRate = document.getElementById('system-stats-update-rate');
    const matrixEffectEnabled = document.getElementById('matrix-effect-enabled');
    const matrixAnimationRate = document.getElementById('matrix-animation-rate');
    const backgroundColorPicker = document.getElementById('background-color');
    const backgroundColorText = document.getElementById('background-color-text');
    const foregroundColorPicker = document.getElementById('foreground-color');
    const foregroundColorText = document.getElementById('foreground-color-text');
    const automationOutputFontSize = document.getElementById('automation-output-font-size');

    // Fetch server config for update rates
    try {
        const response = await fetch('/api/server_config');
        const serverConfig = await response.json();
        // Server uses seconds, UI uses milliseconds
        statusUpdateRate.value = Math.round(serverConfig.service_status_interval * 1000);
        systemStatsUpdateRate.value = Math.round(serverConfig.system_stats_interval * 1000);
    } catch (error) {
        console.error('Error fetching server config:', error);
        // Fallback to defaults if fetch fails
        statusUpdateRate.value = 5000;
        systemStatsUpdateRate.value = 2000;
    }

    // Load client-side settings from localStorage
    matrixEffectEnabled.checked = localStorage.getItem('matrixEffectEnabled') !== 'false'; // Default to true
    matrixAnimationRate.value = localStorage.getItem('matrixAnimationRate') || 120;
    automationOutputFontSize.value = localStorage.getItem('automationOutputFontSize') || 12;

    const compactModeEnabled = document.getElementById('compact-mode-enabled');
    compactModeEnabled.checked = localStorage.getItem('compactModeEnabled') === 'true'; // Default to false

    const savedBackgroundColor = localStorage.getItem('backgroundColor') || '#00ff41';
    const savedForegroundColor = localStorage.getItem('foregroundColor') || '#00ff41';
    const savedGroupColor = localStorage.getItem('groupColor') || '#0080ff';

    backgroundColorPicker.value = savedBackgroundColor;
    backgroundColorText.value = savedBackgroundColor;
    foregroundColorPicker.value = savedForegroundColor;
    foregroundColorText.value = savedForegroundColor;

    const groupColorPicker = document.getElementById('group-color');
    const groupColorText = document.getElementById('group-color-text');
    groupColorPicker.value = savedGroupColor;
    groupColorText.value = savedGroupColor;

    // Sync background color picker and text input
    backgroundColorPicker.addEventListener('input', (e) => {
        backgroundColorText.value = e.target.value;
    });

    backgroundColorText.addEventListener('input', (e) => {
        const value = e.target.value;
        if (/^#[0-9A-F]{6}$/i.test(value)) {
            backgroundColorPicker.value = value;
        }
    });

    // Sync foreground color picker and text input
    foregroundColorPicker.addEventListener('input', (e) => {
        foregroundColorText.value = e.target.value;
    });

    foregroundColorText.addEventListener('input', (e) => {
        const value = e.target.value;
        if (/^#[0-9A-F]{6}$/i.test(value)) {
            foregroundColorPicker.value = value;
        }
    });

    // Sync group color picker and text input
    groupColorPicker.addEventListener('input', (e) => {
        groupColorText.value = e.target.value;
    });

    groupColorText.addEventListener('input', (e) => {
        const value = e.target.value;
        if (/^#[0-9A-F]{6}$/i.test(value)) {
            groupColorPicker.value = value;
        }
    });

    modal.style.display = 'block';
}

function closeSettingsModal() {
    document.getElementById('settingsModal').style.display = 'none';
}

async function saveSettings() {
    const statusUpdateRate = parseInt(document.getElementById('status-update-rate').value);
    const systemStatsUpdateRate = parseInt(document.getElementById('system-stats-update-rate').value);
    const matrixEffectEnabled = document.getElementById('matrix-effect-enabled').checked;
    const matrixAnimationRate = parseInt(document.getElementById('matrix-animation-rate').value);
    const backgroundColor = document.getElementById('background-color').value;
    const foregroundColor = document.getElementById('foreground-color').value;
    const groupColor = document.getElementById('group-color').value;
    const automationOutputFontSize = parseInt(document.getElementById('automation-output-font-size').value);
    const compactModeEnabled = document.getElementById('compact-mode-enabled').checked;

    // Validate inputs (UI uses milliseconds, server uses seconds)
    if (isNaN(statusUpdateRate) || statusUpdateRate < 1000 || statusUpdateRate > 300000) {
        alert('ERROR: Service status update rate must be between 1000 and 300000 ms');
        return;
    }

    if (isNaN(systemStatsUpdateRate) || systemStatsUpdateRate < 100 || systemStatsUpdateRate > 60000) {
        alert('ERROR: System statistics update rate must be between 100 and 60000 ms');
        return;
    }

    if (isNaN(matrixAnimationRate) || matrixAnimationRate < 10 || matrixAnimationRate > 1000) {
        alert('ERROR: Matrix animation rate must be between 10 and 1000 ms');
        return;
    }

    if (isNaN(automationOutputFontSize) || automationOutputFontSize < 8 || automationOutputFontSize > 24) {
        alert('ERROR: Automation output font size must be between 8 and 24 px');
        return;
    }

    if (!/^#[0-9A-F]{6}$/i.test(backgroundColor)) {
        alert('ERROR: Invalid background color format. Please use hex format like #00ff41');
        return;
    }

    if (!/^#[0-9A-F]{6}$/i.test(foregroundColor)) {
        alert('ERROR: Invalid foreground color format. Please use hex format like #00ff41');
        return;
    }

    if (!/^#[0-9A-F]{6}$/i.test(groupColor)) {
        alert('ERROR: Invalid group color format. Please use hex format like #0080ff');
        return;
    }

    // POST update rates to server (convert ms to seconds)
    try {
        const response = await fetch('/api/server_config', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                service_status_interval: statusUpdateRate / 1000,
                system_stats_interval: systemStatsUpdateRate / 1000
            })
        });
        const result = await response.json();
        if (!result.success) {
            alert(`ERROR: Failed to update server config: ${result.error}`);
            return;
        }
    } catch (error) {
        alert(`ERROR: Failed to update server config: ${error.message}`);
        return;
    }

    // Save client-side settings to localStorage
    localStorage.setItem('matrixEffectEnabled', matrixEffectEnabled);
    localStorage.setItem('matrixAnimationRate', matrixAnimationRate);
    localStorage.setItem('backgroundColor', backgroundColor);
    localStorage.setItem('foregroundColor', foregroundColor);
    localStorage.setItem('groupColor', groupColor);
    localStorage.setItem('automationOutputFontSize', automationOutputFontSize);
    localStorage.setItem('compactModeEnabled', compactModeEnabled);

    // Apply colors immediately
    applyColors(foregroundColor, backgroundColor, groupColor);

    // Apply font size immediately
    document.documentElement.style.setProperty('--automation-output-font-size', `${automationOutputFontSize}px`);

    // Apply matrix effect enabled/disabled immediately
    if (matrixEffectEnabled) {
        enableMatrixEffect();
    } else {
        disableMatrixEffect();
    }

    // Apply compact mode immediately
    if (compactModeEnabled) {
        document.body.classList.add('compact-mode');
    } else {
        document.body.classList.remove('compact-mode');
    }

    // Close modal
    closeSettingsModal();
}

// Initialize the page
async function init() {
    // Apply saved colors first
    const foregroundColor = localStorage.getItem('foregroundColor') || '#00ff41';
    const backgroundColor = localStorage.getItem('backgroundColor') || '#00ff41';
    const groupColor = localStorage.getItem('groupColor') || '#0080ff';
    applyColors(foregroundColor, backgroundColor, groupColor);

    // Apply saved font size
    const automationOutputFontSize = parseInt(localStorage.getItem('automationOutputFontSize')) || 12;
    document.documentElement.style.setProperty('--automation-output-font-size', `${automationOutputFontSize}px`);

    // Apply compact mode if enabled
    const compactModeEnabled = localStorage.getItem('compactModeEnabled') === 'true';
    if (compactModeEnabled) {
        document.body.classList.add('compact-mode');
    }

    restoreCollapsedStates();
    await loadAndRenderServices();
    // Devices section: clear once, then render groups top-to-bottom in this
    // order — Remote Machines first (top), then Music Players (device tiles).
    const devSection = document.getElementById('devices-section');
    if (devSection) devSection.innerHTML = '';
    await loadAndRenderRemoteMachines();
    await loadAndRenderDevices();
    updateDevicesSectionVisibility();
    await loadAutomations();

    // Now that automation cards exist in the DOM, request current states
    // from the server. The initial states sent on socket connect may have
    // arrived before the DOM was ready and were silently dropped.
    socket.emit('request_all_automation_states');

    // Load settings from localStorage or use defaults
    const matrixEffectEnabled = localStorage.getItem('matrixEffectEnabled') !== 'false'; // Default to true

    // Start or stop matrix animation based on user preference
    if (matrixEffectEnabled) {
        enableMatrixEffect();
    } else {
        disableMatrixEffect();
    }

    // Fetch initial data (will be updated via WebSocket after this)
    // These calls return cached data from the server, so they're fast
    fetchInitialStatus();
    fetchInitialSystemStats();
    fetchInitialDeviceStatus();
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}