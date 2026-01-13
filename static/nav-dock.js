/**
 * Navigation Dock JavaScript
 *
 * Handles expandable navigation dock behavior
 */

(function() {
    'use strict';

    let dockExpanded = false;
    let hideTimeout = null;

    /**
     * Initialize navigation dock
     */
    function initNavDock() {
        const dock = document.querySelector('.nav-dock');
        if (!dock) return;

        const toggle = dock.querySelector('.nav-toggle');
        if (!toggle) return;

        // Desktop: Expand on hover
        if (window.matchMedia('(hover: hover) and (pointer: fine)').matches) {
            dock.addEventListener('mouseenter', expandDock);
            dock.addEventListener('mouseleave', collapseDock);
        } else {
            // Mobile: Expand on tap
            toggle.addEventListener('click', toggleDock);

            // Collapse when tapping outside
            document.addEventListener('click', function(e) {
                if (!dock.contains(e.target) && dockExpanded) {
                    collapseDock();
                }
            });
        }
    }

    /**
     * Expand the dock
     */
    function expandDock() {
        const dock = document.querySelector('.nav-dock');
        if (!dock) return;

        clearTimeout(hideTimeout);
        dock.classList.add('expanded');
        dockExpanded = true;
    }

    /**
     * Collapse the dock
     */
    function collapseDock() {
        const dock = document.querySelector('.nav-dock');
        if (!dock) return;

        // Add a small delay before collapsing
        hideTimeout = setTimeout(() => {
            dock.classList.remove('expanded');
            dockExpanded = false;
        }, 300);
    }

    /**
     * Toggle dock (for mobile)
     */
    function toggleDock(e) {
        e.stopPropagation();

        if (dockExpanded) {
            collapseDock();
        } else {
            expandDock();
        }
    }

    /**
     * Navigate to a page
     */
    function navigateTo(path) {
        window.location.href = path;
    }

    /**
     * Refresh current page
     */
    function refreshPage() {
        window.location.reload();
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initNavDock);
    } else {
        initNavDock();
    }

    // Expose functions globally for onclick handlers
    window.navigateTo = navigateTo;
    window.refreshPage = refreshPage;
})();
