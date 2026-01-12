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

// Interval IDs for status updates
let statusUpdateInterval = null;
let systemStatsUpdateInterval = null;

window.addEventListener('resize', () => {
    initMatrix();
});

// Store automation configurations
let automationConfigs = {};

// Track client-side accumulated output for each automation
let automationClientOutput = {};

// Track if client has cleared output (to ignore subsequent updates until reset)
let automationClearedState = {};

// Track which automation is currently shown in the fullscreen modal
let currentExpandedAutomation = null;

// Service status functions
let servicesConfig = [];

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

function createServiceCard(service) {
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

    // Create button (either details or link)
    if (service.button_type === 'link') {
        const link = document.createElement('a');
        link.id = `${service.id}-link`;
        link.href = '#';
        link.target = '_blank';
        link.className = 'details-btn';
        link.style.textDecoration = 'none';
        link.textContent = 'WEB UI';
        toggleContainer.appendChild(link);
    } else {
        const detailsBtn = document.createElement('button');
        detailsBtn.className = 'details-btn';
        detailsBtn.textContent = 'DETAILS';
        detailsBtn.onclick = () => showServiceDetails(service.id);
        toggleContainer.appendChild(detailsBtn);
    }

    // Create control toggle
    const toggleLabel = document.createElement('span');
    toggleLabel.className = 'toggle-label';
    toggleLabel.textContent = 'CONTROL';

    const toggleSwitch = document.createElement('div');
    toggleSwitch.className = 'toggle-switch';
    toggleSwitch.id = `${service.id}-toggle`;
    toggleSwitch.onclick = () => toggleService(service.id);

    const toggleSlider = document.createElement('div');
    toggleSlider.className = 'toggle-slider';

    toggleSwitch.appendChild(toggleSlider);
    toggleContainer.appendChild(toggleLabel);
    toggleContainer.appendChild(toggleSwitch);

    // Assemble the card
    serviceCard.appendChild(serviceHeader);
    serviceCard.appendChild(statusText);
    serviceCard.appendChild(toggleContainer);

    return serviceCard;
}

function createServiceGroup(groupName, services) {
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

    // Add service cards to the group
    services.forEach(service => {
        const card = createServiceCard(service);
        content.appendChild(card);
    });

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

async function updateStatus() {
    try {
        const response = await fetch('/api/status');
        const status = await response.json();

        // Dynamically update all configured services
        servicesConfig.forEach(service => {
            if (status.hasOwnProperty(service.id)) {
                updateServiceUI(service.id, status[service.id]);
            }
        });

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

        // Update service links dynamically (e.g., qBittorrent Web UI)
        servicesConfig.forEach(service => {
            if (service.button_type === 'link' && service.link_url) {
                const linkElement = document.getElementById(`${service.id}-link`);
                if (linkElement) {
                    linkElement.href = service.link_url.replace('{hostname}', stats.hostname);
                }
            }
        });

        // Update CPU
        document.getElementById('cpu-value').textContent = stats.cpu_percent + '%';

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
        document.getElementById('uptime-value').textContent = `UPTIME: ${stats.uptime}`;

        // Update Uname
        document.getElementById('uname-value').textContent = `KERNEL: ${stats.uname}`;

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
            <div class="status-indicator yellow" id="${automation.name}-indicator"></div>
        </div>
        <div class="status-text" id="${automation.name}-status">READY</div>
        <div class="automation-args-container">
            <input type="text" class="automation-args-input" id="${automation.name}-args" placeholder="Arguments (optional)" autocorrect="off" spellcheck="false">
        </div>
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

        // Add Enter key listener to arguments input
        const argsInput = document.getElementById(`${automation.name}-args`);
        if (argsInput) {
            argsInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    runAutomation(automation.name);
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

    // Disable button temporarily
    btn.disabled = true;
    btn.textContent = 'STARTING...';

    try {
        const response = await fetch(`/api/automation/${automationName}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ args: args })
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
function openSettingsModal() {
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

    // Load saved settings or use defaults
    statusUpdateRate.value = localStorage.getItem('statusUpdateRate') || 5000;
    systemStatsUpdateRate.value = localStorage.getItem('systemStatsUpdateRate') || 2000;
    matrixEffectEnabled.checked = localStorage.getItem('matrixEffectEnabled') !== 'false'; // Default to true
    matrixAnimationRate.value = localStorage.getItem('matrixAnimationRate') || 120;
    automationOutputFontSize.value = localStorage.getItem('automationOutputFontSize') || 12;

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

function saveSettings() {
    const statusUpdateRate = parseInt(document.getElementById('status-update-rate').value);
    const systemStatsUpdateRate = parseInt(document.getElementById('system-stats-update-rate').value);
    const matrixEffectEnabled = document.getElementById('matrix-effect-enabled').checked;
    const matrixAnimationRate = parseInt(document.getElementById('matrix-animation-rate').value);
    const backgroundColor = document.getElementById('background-color').value;
    const foregroundColor = document.getElementById('foreground-color').value;
    const groupColor = document.getElementById('group-color').value;
    const automationOutputFontSize = parseInt(document.getElementById('automation-output-font-size').value);

    // Validate inputs
    if (isNaN(statusUpdateRate) || statusUpdateRate < 1000 || statusUpdateRate > 60000) {
        alert('ERROR: Status update rate must be between 1000 and 60000 ms');
        return;
    }

    if (isNaN(systemStatsUpdateRate) || systemStatsUpdateRate < 100 || systemStatsUpdateRate > 60000) {
        alert('ERROR: System statistics update rate must be between 1000 and 60000 ms');
        return;
    }

    if (isNaN(matrixAnimationRate) || matrixAnimationRate < 10 || matrixAnimationRate > 1000) {
        alert('ERROR: Matrix animation rate must be between 50 and 1000 ms');
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

    // Save to localStorage
    localStorage.setItem('statusUpdateRate', statusUpdateRate);
    localStorage.setItem('systemStatsUpdateRate', systemStatsUpdateRate);
    localStorage.setItem('matrixEffectEnabled', matrixEffectEnabled);
    localStorage.setItem('matrixAnimationRate', matrixAnimationRate);
    localStorage.setItem('backgroundColor', backgroundColor);
    localStorage.setItem('foregroundColor', foregroundColor);
    localStorage.setItem('groupColor', groupColor);
    localStorage.setItem('automationOutputFontSize', automationOutputFontSize);

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

    // Apply status update rate immediately
    if (statusUpdateInterval) {
        clearInterval(statusUpdateInterval);
    }
    statusUpdateInterval = setInterval(updateStatus, statusUpdateRate);

    // Apply system stats update rate immediately
    if (systemStatsUpdateInterval) {
        clearInterval(systemStatsUpdateInterval);
    }
    systemStatsUpdateInterval = setInterval(updateSystemStats, systemStatsUpdateRate);

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

    restoreCollapsedStates();
    await loadAndRenderServices();
    await loadAutomations();

    // Load settings from localStorage or use defaults
    const statusUpdateRate = parseInt(localStorage.getItem('statusUpdateRate')) || 3000;
    const systemStatsUpdateRate = parseInt(localStorage.getItem('systemStatsUpdateRate')) || 1000;
    const matrixEffectEnabled = localStorage.getItem('matrixEffectEnabled') !== 'false'; // Default to true
    const matrixAnimationRate = parseInt(localStorage.getItem('matrixAnimationRate')) || 120;

    // Start or stop matrix animation based on user preference
    if (matrixEffectEnabled) {
        enableMatrixEffect();
    } else {
        disableMatrixEffect();
    }

    // Start status updates with configured rate
    updateStatus();
    updateSystemStats();
    statusUpdateInterval = setInterval(updateStatus, statusUpdateRate);
    systemStatsUpdateInterval = setInterval(updateSystemStats, systemStatsUpdateRate);
}

// Run initialization when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}