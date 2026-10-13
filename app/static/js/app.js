/**
 * Fieldnote — Shared UI Navigation & Accessibility Script
 * Milestone 7: UI Quality and Mobile Readiness (Phase 2A Foundation)
 */

(function () {
  "use strict";

  // Dynamic Copyright Year update (fallback if client cached)
  function initDynamicYear() {
    var yearEl = document.getElementById("current-year");
    if (yearEl) {
      yearEl.textContent = new Date().getFullYear();
    }
  }

  // Mobile Navigation Drawer Controller
  function initMobileNavigation() {
    var toggleBtn = document.getElementById("mobile-menu-toggle");
    var closeBtn = document.getElementById("mobile-menu-close");
    var drawer = document.getElementById("mobile-nav-drawer");
    var backdrop = document.getElementById("mobile-nav-backdrop");

    if (!toggleBtn || !drawer || !backdrop) {
      return;
    }

    var lastFocusedElement = null;

    function openMenu() {
      lastFocusedElement = document.activeElement;
      drawer.classList.add("is-open");
      backdrop.classList.add("is-open");
      toggleBtn.setAttribute("aria-expanded", "true");
      drawer.setAttribute("aria-hidden", "false");
      backdrop.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden"; // Prevent background body scroll when drawer is open

      // Move focus into the drawer close button or first link
      if (closeBtn) {
        closeBtn.focus();
      }
    }

    function closeMenu() {
      drawer.classList.remove("is-open");
      backdrop.classList.remove("is-open");
      toggleBtn.setAttribute("aria-expanded", "false");
      drawer.setAttribute("aria-hidden", "true");
      backdrop.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";

      // Restore focus to the toggle button
      if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
        lastFocusedElement.focus();
      } else {
        toggleBtn.focus();
      }
    }

    toggleBtn.addEventListener("click", function () {
      var isExpanded = toggleBtn.getAttribute("aria-expanded") === "true";
      if (isExpanded) {
        closeMenu();
      } else {
        openMenu();
      }
    });

    if (closeBtn) {
      closeBtn.addEventListener("click", closeMenu);
    }

    backdrop.addEventListener("click", closeMenu);

    // Close when navigating via mobile links
    var drawerLinks = drawer.querySelectorAll("a");
    drawerLinks.forEach(function (link) {
      link.addEventListener("click", closeMenu);
    });

    // Close on Escape key press
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" || event.key === "Esc") {
        if (toggleBtn.getAttribute("aria-expanded") === "true") {
          closeMenu();
        }
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    initDynamicYear();
    initMobileNavigation();
  });
})();
