/**
 * Fieldnote — Research Notes & Evidence Management UI Script
 * Milestone 7: UI Quality and Mobile Readiness (Phase 2A Foundation & Phase 2B Dashboard)
 */

(function () {
  "use strict";

  /* ==========================================================================
     1. Toast Notification System
     ========================================================================== */
  function showToast(message, type) {
    type = type || "info";
    var container = document.getElementById("toast-container");
    if (!container) return;

    var toast = document.createElement("div");
    toast.className = "toast toast-" + type;
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");

    var iconSpan = document.createElement("span");
    iconSpan.style.fontWeight = "bold";
    if (type === "success") iconSpan.textContent = "✓";
    else if (type === "error") iconSpan.textContent = "!";
    else iconSpan.textContent = "ℹ";

    var textSpan = document.createElement("span");
    textSpan.textContent = message;

    toast.appendChild(iconSpan);
    toast.appendChild(textSpan);
    container.appendChild(toast);

    setTimeout(function () {
      toast.style.opacity = "0";
      toast.style.transform = "translateY(-8px)";
      setTimeout(function () {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 200);
    }, 4000);
  }

  /* ==========================================================================
     2. Dynamic Copyright Year
     ========================================================================== */
  function initDynamicYear() {
    var yearEl = document.getElementById("current-year");
    if (yearEl) {
      yearEl.textContent = new Date().getFullYear();
    }
  }

  /* ==========================================================================
     3. Accessible Mobile Navigation Drawer
     ========================================================================== */
  function initMobileNavigation() {
    var toggleBtn = document.getElementById("mobile-menu-toggle");
    var closeBtn = document.getElementById("mobile-menu-close");
    var drawer = document.getElementById("mobile-nav-drawer");
    var backdrop = document.getElementById("mobile-nav-backdrop");

    if (!toggleBtn || !drawer || !backdrop) return;

    var lastFocusedElement = null;

    function openMenu() {
      lastFocusedElement = document.activeElement;
      drawer.classList.add("is-open");
      backdrop.classList.add("is-open");
      toggleBtn.setAttribute("aria-expanded", "true");
      drawer.setAttribute("aria-hidden", "false");
      backdrop.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";

      if (closeBtn) closeBtn.focus();
    }

    function closeMenu() {
      drawer.classList.remove("is-open");
      backdrop.classList.remove("is-open");
      toggleBtn.setAttribute("aria-expanded", "false");
      drawer.setAttribute("aria-hidden", "true");
      backdrop.setAttribute("aria-hidden", "true");
      document.body.style.overflow = "";

      if (lastFocusedElement && typeof lastFocusedElement.focus === "function") {
        lastFocusedElement.focus();
      } else {
        toggleBtn.focus();
      }
    }

    toggleBtn.addEventListener("click", function () {
      var isExpanded = toggleBtn.getAttribute("aria-expanded") === "true";
      if (isExpanded) closeMenu();
      else openMenu();
    });

    if (closeBtn) closeBtn.addEventListener("click", closeMenu);
    backdrop.addEventListener("click", closeMenu);

    var drawerLinks = drawer.querySelectorAll("a");
    drawerLinks.forEach(function (link) {
      link.addEventListener("click", closeMenu);
    });

    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" || event.key === "Esc") {
        if (toggleBtn.getAttribute("aria-expanded") === "true") {
          closeMenu();
        }
      }
    });
  }

  /* ==========================================================================
     4. Research Observations Dashboard Controller (Phase 2B)
     ========================================================================== */
  function initDashboard() {
    var notesGrid = document.getElementById("notes-grid");
    if (!notesGrid) return; // Not on the dashboard page

    // State Variables
    var state = {
      searchMode: "text", // 'text' | 'semantic'
      searchQuery: "",
      tagFilter: "",
      skip: 0,
      limit: 20,
      notes: [],
      noteToDelete: null,
      lastModalFocus: null,
      activeRequestId: 0,
      activeEvidenceRequestId: 0,
      activeEvidenceNote: null,
      evidenceList: [],
      attachmentToDelete: null,
      activeLightboxTrigger: null,
    };

    // DOM Elements
    var modeTextBtn = document.getElementById("mode-text-btn");
    var modeSemanticBtn = document.getElementById("mode-semantic-btn");
    var searchForm = document.getElementById("search-form");
    var searchInput = document.getElementById("search-input");
    var btnSearchClear = document.getElementById("btn-search-clear");
    var tagFilterSection = document.getElementById("tag-filter-section");
    var tagFilterInput = document.getElementById("tag-filter-input");
    var btnApplyTags = document.getElementById("btn-apply-tags");
    var btnClearTags = document.getElementById("btn-clear-tags");
    var activeFiltersBar = document.getElementById("active-filters-bar");
    var activeFilterChips = document.getElementById("active-filter-chips");
    var btnClearAllFilters = document.getElementById("btn-clear-all-filters");

    var notesLoading = document.getElementById("notes-loading");
    var notesError = document.getElementById("notes-error");
    var notesErrorDesc = document.getElementById("notes-error-desc");
    var btnRetryNotes = document.getElementById("btn-retry-notes");
    var notesEmpty = document.getElementById("notes-empty");
    var notesEmptyDesc = document.getElementById("notes-empty-desc");
    var btnEmptyCreate = document.getElementById("btn-empty-create");

    var paginationControls = document.getElementById("pagination-controls");
    var btnPrevPage = document.getElementById("btn-prev-page");
    var btnNextPage = document.getElementById("btn-next-page");
    var pageIndicator = document.getElementById("page-indicator");
    var limitSelect = document.getElementById("limit-select");

    // Modal Elements: Note Create / Edit
    var btnOpenCreate = document.getElementById("btn-open-create-modal");
    var noteModal = document.getElementById("note-modal");
    var noteModalBackdrop = document.getElementById("note-modal-backdrop");
    var noteModalTitle = document.getElementById("note-modal-title");
    var btnCloseNoteModal = document.getElementById("btn-close-note-modal");
    var btnCancelNote = document.getElementById("btn-cancel-note");
    var noteForm = document.getElementById("note-form");
    var noteEditId = document.getElementById("note-edit-id");
    var noteTitleInput = document.getElementById("note-title-input");
    var noteContentInput = document.getElementById("note-content-input");
    var noteTagsInput = document.getElementById("note-tags-input");
    var modalErrorAlert = document.getElementById("modal-error-alert");

    // Modal Elements: Note Delete
    var deleteModal = document.getElementById("delete-modal");
    var deleteModalBackdrop = document.getElementById("delete-modal-backdrop");
    var deleteNoteTargetTitle = document.getElementById("delete-note-target-title");
    var btnCloseDeleteModal = document.getElementById("btn-close-delete-modal");
    var btnCancelDelete = document.getElementById("btn-cancel-delete");
    var btnConfirmDelete = document.getElementById("btn-confirm-delete");

    // Modal Elements: Evidence Gallery & Upload
    var evidenceModal = document.getElementById("evidence-modal");
    var evidenceModalBackdrop = document.getElementById("evidence-modal-backdrop");
    var evidenceModalNoteTitle = document.getElementById("evidence-modal-note-title");
    var btnCloseEvidenceModal = document.getElementById("btn-close-evidence-modal");
    var btnDoneEvidence = document.getElementById("btn-done-evidence");
    var evidenceUploadForm = document.getElementById("evidence-upload-form");
    var evidenceUploadError = document.getElementById("evidence-upload-error");
    var evidenceFileInput = document.getElementById("evidence-file-input");
    var evidenceCaptionInput = document.getElementById("evidence-caption-input");
    var evidenceDescInput = document.getElementById("evidence-desc-input");
    var btnUploadEvidence = document.getElementById("btn-upload-evidence");
    var evidenceLoading = document.getElementById("evidence-loading");
    var evidenceError = document.getElementById("evidence-error");
    var evidenceErrorDesc = document.getElementById("evidence-error-desc");
    var btnRetryEvidence = document.getElementById("btn-retry-evidence");
    var evidenceEmpty = document.getElementById("evidence-empty");
    var evidenceGrid = document.getElementById("evidence-grid");

    // Modal Elements: Full-Size Lightbox
    var lightboxModal = document.getElementById("lightbox-modal");
    var lightboxModalBackdrop = document.getElementById("lightbox-modal-backdrop");
    var btnCloseLightboxModal = document.getElementById("btn-close-lightbox-modal");
    var btnCloseLightbox = document.getElementById("btn-close-lightbox");
    var lightboxImg = document.getElementById("lightbox-img");
    var lightboxCaption = document.getElementById("lightbox-caption");
    var lightboxDesc = document.getElementById("lightbox-desc");
    var lightboxMeta = document.getElementById("lightbox-meta");

    // Modal Elements: Delete Attachment
    var deleteAttachmentModal = document.getElementById("delete-attachment-modal");
    var deleteAttachmentModalBackdrop = document.getElementById("delete-attachment-modal-backdrop");
    var deleteAttachmentTargetName = document.getElementById("delete-attachment-target-name");
    var btnCloseDeleteAttachmentModal = document.getElementById("btn-close-delete-attachment-modal");
    var btnCancelDeleteAttachment = document.getElementById("btn-cancel-delete-attachment");
    var btnConfirmDeleteAttachment = document.getElementById("btn-confirm-delete-attachment");

    // Format Date Helper
    function formatUtcDate(isoString) {
      if (!isoString) return "";
      try {
        var d = new Date(isoString);
        return d.toISOString().replace("T", " ").substring(0, 16) + " UTC";
      } catch (e) {
        return isoString;
      }
    }

    // Format File Size Helper
    function formatFileSize(bytes) {
      if (typeof bytes !== "number" || isNaN(bytes)) return "";
      if (bytes < 1024) return bytes + " B";
      var kb = bytes / 1024;
      if (kb < 1024) return kb.toFixed(1) + " KB";
      var mb = kb / 1024;
      return mb.toFixed(2) + " MB";
    }

    // Modal Show/Hide Helpers
    function openDialog(modal, backdrop, focusTarget) {
      modal._previousFocus = document.activeElement;
      state.lastModalFocus = document.activeElement;
      modal.classList.add("is-open");
      backdrop.classList.add("is-open");
      modal.setAttribute("aria-hidden", "false");
      backdrop.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
      if (focusTarget && typeof focusTarget.focus === "function") {
        setTimeout(function () { focusTarget.focus(); }, 50);
      }
    }

    function closeDialog(modal, backdrop) {
      modal.classList.remove("is-open");
      backdrop.classList.remove("is-open");
      modal.setAttribute("aria-hidden", "true");
      backdrop.setAttribute("aria-hidden", "true");
      var anyOtherOpen = document.querySelector(".modal-dialog.is-open");
      if (!anyOtherOpen) {
        document.body.style.overflow = "";
      }
      var target = modal._previousFocus || state.lastModalFocus;
      modal._previousFocus = null;
      if (target && typeof target.focus === "function") {
        target.focus();
      }
    }

    // Modal Focus Trap Helper
    var FOCUSABLE_SELECTORS = [
      'a[href]',
      'button:not([disabled])',
      'input:not([disabled]):not([type="hidden"])',
      'select:not([disabled])',
      'textarea:not([disabled])',
      '[tabindex]:not([tabindex="-1"])',
    ].join(", ");

    function getModalFocusableElements(modal) {
      return Array.prototype.slice.call(
        modal.querySelectorAll(FOCUSABLE_SELECTORS)
      ).filter(function (el) {
        return el.offsetParent !== null || el.offsetWidth > 0 || el.offsetHeight > 0;
      });
    }

    function trapModalFocus(modal, event) {
      if (event.key !== "Tab") return;

      var focusable = getModalFocusableElements(modal);
      if (focusable.length === 0) {
        event.preventDefault();
        return;
      }

      if (focusable.length === 1) {
        event.preventDefault();
        focusable[0].focus();
        return;
      }

      var firstEl = focusable[0];
      var lastEl = focusable[focusable.length - 1];

      if (event.shiftKey) {
        if (document.activeElement === firstEl || !modal.contains(document.activeElement)) {
          event.preventDefault();
          lastEl.focus();
        }
      } else {
        if (document.activeElement === lastEl || !modal.contains(document.activeElement)) {
          event.preventDefault();
          firstEl.focus();
        }
      }
    }

    // Tag Normalization Helper: trim tokens, drop empties, deduplicate
    function normalizeTags(rawString) {
      if (!rawString) return "";
      var tokens = rawString.split(",");
      var cleaned = [];
      tokens.forEach(function (t) {
        var trimmed = t.trim();
        if (trimmed.length > 0 && cleaned.indexOf(trimmed) === -1) {
          cleaned.push(trimmed);
        }
      });
      return cleaned.join(",");
    }

    // Render Filter Indicators
    function updateActiveFilterIndicators() {
      if (!activeFiltersBar || !activeFilterChips) return;
      activeFilterChips.innerHTML = "";
      var hasFilters = false;

      if (state.searchQuery.trim()) {
        hasFilters = true;
        var modeLabel = state.searchMode === "semantic" ? "Semantic Search" : "Text Search";
        var chip = document.createElement("span");
        chip.className = "filter-chip";
        chip.textContent = modeLabel + ': "' + state.searchQuery + '"';
        var removeBtn = document.createElement("button");
        removeBtn.type = "button";
        removeBtn.className = "filter-chip-remove";
        removeBtn.setAttribute("aria-label", "Remove search query filter");
        removeBtn.textContent = "×";
        removeBtn.addEventListener("click", function () {
          state.searchQuery = "";
          searchInput.value = "";
          btnSearchClear.style.display = "none";
          state.skip = 0;
          loadNotes();
        });
        chip.appendChild(removeBtn);
        activeFilterChips.appendChild(chip);
      }

      if (state.tagFilter.trim() && state.searchMode === "text") {
        hasFilters = true;
        var tagChip = document.createElement("span");
        tagChip.className = "filter-chip";
        tagChip.textContent = 'Tags: "' + state.tagFilter + '"';
        var removeTagBtn = document.createElement("button");
        removeTagBtn.type = "button";
        removeTagBtn.className = "filter-chip-remove";
        removeTagBtn.setAttribute("aria-label", "Remove tag filter");
        removeTagBtn.textContent = "×";
        removeTagBtn.addEventListener("click", function () {
          state.tagFilter = "";
          tagFilterInput.value = "";
          btnClearTags.style.display = "none";
          state.skip = 0;
          loadNotes();
        });
        tagChip.appendChild(removeTagBtn);
        activeFilterChips.appendChild(tagChip);
      }

      activeFiltersBar.style.display = hasFilters ? "flex" : "none";
    }

    // Render Notes in Grid
    function getDayHeaderString(isoString) {
      if (!isoString) return "";
      try {
        var d = new Date(isoString);
        var now = new Date();
        var isToday = d.getUTCFullYear() === now.getUTCFullYear() &&
                      d.getUTCMonth() === now.getUTCMonth() &&
                      d.getUTCDate() === now.getUTCDate();
        if (isToday) return "Today";
        var yesterday = new Date(now.getTime() - 86400000);
        var isYesterday = d.getUTCFullYear() === yesterday.getUTCFullYear() &&
                          d.getUTCMonth() === yesterday.getUTCMonth() &&
                          d.getUTCDate() === yesterday.getUTCDate();
        if (isYesterday) return "Yesterday";
        var options = { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" };
        return d.toLocaleDateString("en-US", options);
      } catch (e) {
        return "";
      }
    }

    function renderNotesGrid(notes, isSemantic) {
      notesGrid.innerHTML = "";
      var lastDayHeader = null;

      notes.forEach(function (note) {
        var currentDay = getDayHeaderString(note.created_at);
        if (currentDay && currentDay !== lastDayHeader && !isSemantic) {
          lastDayHeader = currentDay;
          var dayDivider = document.createElement("div");
          dayDivider.className = "timeline-day-divider";
          var dayText = document.createElement("span");
          dayText.className = "timeline-day-title";
          dayText.textContent = currentDay;
          dayDivider.appendChild(dayText);
          notesGrid.appendChild(dayDivider);
        }

        var card = document.createElement("article");
        card.className = "note-card";
        card.setAttribute("tabindex", "0");

        // Header: Title + Optional Type Badge + Optional Semantic Score Badge
        var header = document.createElement("div");
        header.className = "note-card-header";

        var title = document.createElement("h2");
        title.className = "note-card-title";
        title.textContent = note.title;
        header.appendChild(title);

        var badgesWrap = document.createElement("div");
        badgesWrap.className = "note-card-badges";

        var entryType = (note.type || "memory").toLowerCase();
        var typeBadge = document.createElement("span");
        typeBadge.className = "type-badge type-badge-" + entryType;
        typeBadge.textContent = entryType.charAt(0).toUpperCase() + entryType.slice(1);
        badgesWrap.appendChild(typeBadge);

        if (isSemantic && typeof note.score === "number") {
          var scoreBadge = document.createElement("span");
          scoreBadge.className = "score-badge";
          scoreBadge.textContent = "Score: " + note.score.toFixed(4);
          badgesWrap.appendChild(scoreBadge);
        }
        header.appendChild(badgesWrap);
        card.appendChild(header);

        // Body: Content (Safe textContent rendering)
        var body = document.createElement("div");
        body.className = "note-card-body";
        body.textContent = note.content;
        card.appendChild(body);

        // Tags List
        if (Array.isArray(note.tags) && note.tags.length > 0) {
          var tagsContainer = document.createElement("div");
          tagsContainer.className = "note-card-tags";
          note.tags.forEach(function (tagText) {
            var tagBtn = document.createElement("button");
            tagBtn.type = "button";
            tagBtn.className = "tag-btn";
            tagBtn.textContent = "#" + tagText;
            tagBtn.setAttribute("aria-label", "Filter by tag " + tagText);
            tagBtn.addEventListener("click", function () {
              if (state.searchMode !== "text") {
                setSearchMode("text");
              }
              state.tagFilter = tagText;
              tagFilterInput.value = tagText;
              btnClearTags.style.display = "inline-flex";
              state.skip = 0;
              loadNotes();
            });
            tagsContainer.appendChild(tagBtn);
          });
          card.appendChild(tagsContainer);
        }

        // Footer: Meta (Timestamps) & Action Buttons
        var footer = document.createElement("div");
        footer.className = "note-card-footer";

        var meta = document.createElement("div");
        meta.className = "note-card-meta";
        meta.textContent = formatUtcDate(note.created_at);
        footer.appendChild(meta);

        var actions = document.createElement("div");
        actions.className = "note-card-actions";

        var evidenceBtn = document.createElement("button");
        evidenceBtn.type = "button";
        evidenceBtn.className = "action-btn action-btn-accent";
        evidenceBtn.textContent = "📷 Evidence";
        evidenceBtn.setAttribute("aria-label", "View and manage evidence attachments for note: " + note.title);
        evidenceBtn.addEventListener("click", function () {
          openEvidenceModal(note.id, note.title, evidenceBtn);
        });
        actions.appendChild(evidenceBtn);

        var editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "action-btn";
        editBtn.textContent = "Edit";
        editBtn.setAttribute("aria-label", "Edit note: " + note.title);
        editBtn.addEventListener("click", function () {
          openEditModal(note.id);
        });
        actions.appendChild(editBtn);

        var deleteBtn = document.createElement("button");
        deleteBtn.type = "button";
        deleteBtn.className = "action-btn action-btn-danger";
        deleteBtn.textContent = "Delete";
        deleteBtn.setAttribute("aria-label", "Delete note: " + note.title);
        deleteBtn.addEventListener("click", function () {
          openDeleteModal(note.id, note.title);
        });
        actions.appendChild(deleteBtn);

        footer.appendChild(actions);
        card.appendChild(footer);

        notesGrid.appendChild(card);
      });
    }

    // Update Pagination UI
    function updatePagination(returnedCount, isSemantic) {
      if (isSemantic) {
        // Semantic search is ranking-based top-N; hide skip/offset pagination controls
        paginationControls.style.display = "none";
        return;
      }

      if (state.skip === 0 && returnedCount < state.limit && returnedCount === 0) {
        paginationControls.style.display = "none";
        return;
      }

      paginationControls.style.display = "flex";
      var currentPage = Math.floor(state.skip / state.limit) + 1;
      pageIndicator.textContent = "Page " + currentPage;

      btnPrevPage.disabled = state.skip === 0;
      // Disable next if we received fewer notes than requested limit
      btnNextPage.disabled = returnedCount < state.limit;
    }

    // Primary Data Fetcher
    function loadNotes() {
      var currentRequestId = ++state.activeRequestId;

      notesLoading.style.display = "flex";
      notesError.style.display = "none";
      notesEmpty.style.display = "none";
      notesGrid.style.display = "none";
      paginationControls.style.display = "none";

      updateActiveFilterIndicators();

      // Branch: Semantic Vector Search
      if (state.searchMode === "semantic") {
        var trimmedQuery = state.searchQuery.trim();
        if (!trimmedQuery) {
          notesLoading.style.display = "none";
          notesEmpty.style.display = "flex";
          notesEmptyDesc.textContent = "Enter a search query above to query notes using Atlas Vector Search ($vectorSearch).";
          btnEmptyCreate.style.display = "none";
          return;
        }

        var semanticUrl = "/api/search/semantic?q=" + encodeURIComponent(trimmedQuery) + "&limit=" + encodeURIComponent(state.limit);
        fetch(semanticUrl)
          .then(function (res) {
            if (currentRequestId !== state.activeRequestId) return null;
            if (!res.ok) {
              return res.json().then(function (errData) {
                var msg = (errData && errData.detail) || ("Semantic search failed with HTTP " + res.status);
                throw new Error(msg);
              }).catch(function (parseErr) {
                if (parseErr.message && parseErr.message.indexOf("Semantic search failed") !== -1) throw parseErr;
                throw new Error("Semantic search failed with HTTP " + res.status);
              });
            }
            return res.json();
          })
          .then(function (data) {
            if (currentRequestId !== state.activeRequestId || data === null) return;
            notesLoading.style.display = "none";
            state.notes = data;
            if (!Array.isArray(data) || data.length === 0) {
              notesEmpty.style.display = "flex";
              notesEmptyDesc.textContent = 'No semantically matching notes found for "' + trimmedQuery + '".';
              btnEmptyCreate.style.display = "inline-flex";
            } else {
              notesGrid.style.display = "grid";
              renderNotesGrid(data, true);
              updatePagination(data.length, true);
            }
          })
          .catch(function (err) {
            if (currentRequestId !== state.activeRequestId) return;
            notesLoading.style.display = "none";
            notesError.style.display = "flex";
            notesErrorDesc.textContent = err.message || "Failed to execute semantic vector search.";
            showToast(err.message, "error");
          });
        return;
      }

      // Branch: Standard / MongoDB Text Search
      var params = [];
      params.push("skip=" + encodeURIComponent(state.skip));
      params.push("limit=" + encodeURIComponent(state.limit));

      if (state.searchQuery.trim()) {
        params.push("q=" + encodeURIComponent(state.searchQuery.trim()));
      }
      if (state.tagFilter.trim()) {
        params.push("tags=" + encodeURIComponent(state.tagFilter.trim()));
      }

      var notesUrl = "/api/notes?" + params.join("&");
      fetch(notesUrl)
        .then(function (res) {
          if (currentRequestId !== state.activeRequestId) return null;
          if (!res.ok) {
            return res.json().then(function (errData) {
              var msg = (errData && errData.detail) || ("API request failed with HTTP " + res.status);
              throw new Error(msg);
            }).catch(function (parseErr) {
              if (parseErr.message && parseErr.message.indexOf("API request failed") !== -1) throw parseErr;
              throw new Error("API request failed with HTTP " + res.status);
            });
          }
          return res.json();
        })
        .then(function (data) {
          if (currentRequestId !== state.activeRequestId || data === null) return;
          notesLoading.style.display = "none";
          state.notes = data;
          if (!Array.isArray(data) || data.length === 0) {
            if (state.skip > 0) {
              // Pagination beyond available results: preserve accessible previous navigation
              notesEmpty.style.display = "flex";
              var currentPageNum = Math.floor(state.skip / state.limit) + 1;
              notesEmptyDesc.textContent = "No research observations found on Page " + currentPageNum + ". You have navigated past the last available note.";
              btnEmptyCreate.style.display = "none";
              paginationControls.style.display = "flex";
              pageIndicator.textContent = "Page " + currentPageNum;
              btnPrevPage.disabled = false;
              btnNextPage.disabled = true;
            } else {
              notesEmpty.style.display = "flex";
              if (state.searchQuery.trim() || state.tagFilter.trim()) {
                notesEmptyDesc.textContent = "No research notes match the active filter or search criteria.";
              } else {
                notesEmptyDesc.textContent = "The notes repository is currently empty. Create your first field observation below.";
              }
              btnEmptyCreate.style.display = "inline-flex";
              paginationControls.style.display = "none";
            }
          } else {
            notesGrid.style.display = "grid";
            renderNotesGrid(data, false);
            updatePagination(data.length, false);
          }
        })
        .catch(function (err) {
          if (currentRequestId !== state.activeRequestId) return;
          notesLoading.style.display = "none";
          notesError.style.display = "flex";
          notesErrorDesc.textContent = err.message || "Failed to load notes from Fieldnote API.";
          showToast(err.message, "error");
        });
    }

    // Switch Search Mode
    function setSearchMode(newMode) {
      if (state.searchMode === newMode) return;
      state.searchMode = newMode;
      state.skip = 0;

      if (newMode === "semantic") {
        modeSemanticBtn.classList.add("active");
        modeSemanticBtn.setAttribute("aria-selected", "true");
        modeTextBtn.classList.remove("active");
        modeTextBtn.setAttribute("aria-selected", "false");
        tagFilterSection.style.display = "none"; // Semantic search does not use tag query params
        searchInput.placeholder = "Enter natural language query for Atlas Vector Search...";
      } else {
        modeTextBtn.classList.add("active");
        modeTextBtn.setAttribute("aria-selected", "true");
        modeSemanticBtn.classList.remove("active");
        modeSemanticBtn.setAttribute("aria-selected", "false");
        tagFilterSection.style.display = "block";
        searchInput.placeholder = "Search research notes (e.g., 'soil moisture', 'satellite trajectory')...";
      }

      loadNotes();
    }

    modeTextBtn.addEventListener("click", function () { setSearchMode("text"); });
    modeSemanticBtn.addEventListener("click", function () { setSearchMode("semantic"); });

    // Search Form Submit
    searchForm.addEventListener("submit", function (e) {
      e.preventDefault();
      var q = searchInput.value.trim();
      state.searchQuery = q;
      state.skip = 0;
      btnSearchClear.style.display = q ? "inline-flex" : "none";
      loadNotes();
    });

    btnSearchClear.addEventListener("click", function () {
      searchInput.value = "";
      state.searchQuery = "";
      btnSearchClear.style.display = "none";
      state.skip = 0;
      loadNotes();
    });

    // Synchronize native search clear (browser clear 'x' button)
    searchInput.addEventListener("search", function () {
      if (!searchInput.value.trim() && state.searchQuery) {
        state.searchQuery = "";
        btnSearchClear.style.display = "none";
        state.skip = 0;
        loadNotes();
      }
    });

    // Tag Filter Submit: normalize tokens (trim, drop empty/duplicate)
    btnApplyTags.addEventListener("click", function () {
      var normalized = normalizeTags(tagFilterInput.value);
      state.tagFilter = normalized;
      tagFilterInput.value = normalized;
      state.skip = 0;
      btnClearTags.style.display = normalized ? "inline-flex" : "none";
      loadNotes();
    });

    btnClearTags.addEventListener("click", function () {
      tagFilterInput.value = "";
      state.tagFilter = "";
      btnClearTags.style.display = "none";
      state.skip = 0;
      loadNotes();
    });

    btnClearAllFilters.addEventListener("click", function () {
      searchInput.value = "";
      tagFilterInput.value = "";
      state.searchQuery = "";
      state.tagFilter = "";
      btnSearchClear.style.display = "none";
      btnClearTags.style.display = "none";
      state.skip = 0;
      loadNotes();
    });

    btnRetryNotes.addEventListener("click", function () { loadNotes(); });

    // Pagination Click Handlers
    btnPrevPage.addEventListener("click", function () {
      if (state.skip > 0) {
        state.skip = Math.max(0, state.skip - state.limit);
        loadNotes();
      }
    });

    btnNextPage.addEventListener("click", function () {
      state.skip += state.limit;
      loadNotes();
    });

    limitSelect.addEventListener("change", function () {
      state.limit = parseInt(limitSelect.value, 10) || 20;
      state.skip = 0;
      loadNotes();
    });

    // Note Create / Edit Modal Logic
    function openCreateModal() {
      noteForm.reset();
      noteEditId.value = "";
      noteModalTitle.textContent = "Capture Memory";
      var noteTypeSelect = document.getElementById("note-type-select");
      if (noteTypeSelect) noteTypeSelect.value = "memory";
      modalErrorAlert.style.display = "none";
      modalErrorAlert.textContent = "";
      openDialog(noteModal, noteModalBackdrop, noteTitleInput);
    }

    function openEditModal(noteId) {
      modalErrorAlert.style.display = "none";
      modalErrorAlert.textContent = "";
      fetch("/api/notes/" + encodeURIComponent(noteId))
        .then(function (res) {
          if (!res.ok) throw new Error("Failed to load note details.");
          return res.json();
        })
        .then(function (note) {
          noteEditId.value = note.id;
          noteTitleInput.value = note.title;
          noteContentInput.value = note.content;
          noteTagsInput.value = Array.isArray(note.tags) ? note.tags.join(", ") : "";
          var noteTypeSelect = document.getElementById("note-type-select");
          if (noteTypeSelect) noteTypeSelect.value = note.type || "memory";
          noteModalTitle.textContent = "Edit Memory";
          openDialog(noteModal, noteModalBackdrop, noteTitleInput);
        })
        .catch(function (err) {
          showToast(err.message, "error");
        });
    }

    btnOpenCreate.addEventListener("click", openCreateModal);
    btnEmptyCreate.addEventListener("click", openCreateModal);

    btnCloseNoteModal.addEventListener("click", function () { closeDialog(noteModal, noteModalBackdrop); });
    btnCancelNote.addEventListener("click", function () { closeDialog(noteModal, noteModalBackdrop); });
    noteModalBackdrop.addEventListener("click", function () { closeDialog(noteModal, noteModalBackdrop); });

    noteForm.addEventListener("submit", function (e) {
      e.preventDefault();
      modalErrorAlert.style.display = "none";

      var titleVal = noteTitleInput.value.trim();
      var contentVal = noteContentInput.value;
      var rawTags = noteTagsInput.value.split(",");
      var tagsVal = [];
      rawTags.forEach(function (t) {
        var st = t.trim();
        if (st.length > 0 && tagsVal.indexOf(st) === -1) {
          tagsVal.push(st);
        }
      });

      // Low-friction capture: auto-generate title if omitted by user
      if (!titleVal) {
        if (contentVal && contentVal.trim()) {
          var firstLine = contentVal.trim().split("\n")[0].replace(/^[#\s*-_]+/, "").trim();
          titleVal = firstLine.length > 50 ? firstLine.substring(0, 47) + "..." : firstLine;
        }
        if (!titleVal) {
          var now = new Date();
          titleVal = "Memory on " + now.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
        }
      }

      if (!contentVal || !contentVal.trim()) {
        modalErrorAlert.textContent = "Content is required to capture a memory.";
        modalErrorAlert.style.display = "block";
        noteContentInput.focus();
        return;
      }

      var noteTypeSelect = document.getElementById("note-type-select");
      var typeVal = noteTypeSelect ? noteTypeSelect.value : "memory";

      var isEdit = Boolean(noteEditId.value);
      var method = isEdit ? "PUT" : "POST";
      var url = isEdit ? ("/api/notes/" + encodeURIComponent(noteEditId.value)) : "/api/notes";

      var payload = {
        title: titleVal,
        content: contentVal,
        tags: tagsVal,
        type: typeVal,
      };

      var saveBtn = document.getElementById("btn-save-note");
      saveBtn.disabled = true;
      saveBtn.textContent = "Saving...";

      fetch(url, {
        method: method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
        .then(function (res) {
          if (!res.ok) {
            return res.json().then(function (errData) {
              var msg = (errData && errData.detail) || "Failed to save note.";
              if (Array.isArray(msg)) {
                msg = msg.map(function (m) { return m.msg || JSON.stringify(m); }).join("; ");
              }
              throw new Error(msg);
            }).catch(function (parseErr) {
              throw new Error("Failed to save note (HTTP " + res.status + ")");
            });
          }
          return res.json();
        })
        .then(function (saved) {
          saveBtn.disabled = false;
          saveBtn.textContent = "Save Note";
          closeDialog(noteModal, noteModalBackdrop);
          showToast(isEdit ? "Note updated successfully" : "Research note created successfully", "success");
          loadNotes();
        })
        .catch(function (err) {
          saveBtn.disabled = false;
          saveBtn.textContent = "Save Note";
          modalErrorAlert.textContent = err.message || "An unexpected error occurred.";
          modalErrorAlert.style.display = "block";
          showToast(err.message, "error");
        });
    });

    // Delete Modal Logic
    function openDeleteModal(noteId, noteTitle) {
      state.noteToDelete = { id: noteId, title: noteTitle };
      deleteNoteTargetTitle.textContent = '"' + noteTitle + '"';
      openDialog(deleteModal, deleteModalBackdrop, btnCancelDelete);
    }

    btnCloseDeleteModal.addEventListener("click", function () { closeDialog(deleteModal, deleteModalBackdrop); });
    btnCancelDelete.addEventListener("click", function () { closeDialog(deleteModal, deleteModalBackdrop); });
    deleteModalBackdrop.addEventListener("click", function () { closeDialog(deleteModal, deleteModalBackdrop); });

    btnConfirmDelete.addEventListener("click", function () {
      if (!state.noteToDelete) return;
      var noteId = state.noteToDelete.id;
      btnConfirmDelete.disabled = true;
      btnConfirmDelete.textContent = "Deleting...";

      fetch("/api/notes/" + encodeURIComponent(noteId), { method: "DELETE" })
        .then(function (res) {
          if (!res.ok && res.status !== 204) {
            return res.json().then(function (errData) {
              throw new Error((errData && errData.detail) || "Failed to delete note.");
            }).catch(function () {
              throw new Error("Delete failed with HTTP " + res.status);
            });
          }
          btnConfirmDelete.disabled = false;
          btnConfirmDelete.textContent = "Delete Permanently";
          closeDialog(deleteModal, deleteModalBackdrop);
          showToast("Research note deleted", "success");
          state.noteToDelete = null;
          loadNotes();
        })
        .catch(function (err) {
          btnConfirmDelete.disabled = false;
          btnConfirmDelete.textContent = "Delete Permanently";
          closeDialog(deleteModal, deleteModalBackdrop);
          showToast(err.message, "error");
        });
    });

    // Evidence Modal & Gallery Controller
    function openEvidenceModal(noteId, noteTitle, triggerBtn) {
      state.activeEvidenceNote = { id: noteId, title: noteTitle };
      evidenceModalNoteTitle.textContent = noteTitle;

      evidenceUploadForm.reset();
      evidenceUploadError.style.display = "none";
      evidenceUploadError.textContent = "";

      openDialog(evidenceModal, evidenceModalBackdrop, btnCloseEvidenceModal);
      loadEvidence();
    }

    function closeEvidenceModal() {
      state.activeEvidenceNote = null;
      state.activeEvidenceRequestId++;
      closeDialog(evidenceModal, evidenceModalBackdrop);
    }

    function loadEvidence(onComplete) {
      if (!state.activeEvidenceNote) return;
      var noteId = state.activeEvidenceNote.id;
      var currentEvidenceRequestId = ++state.activeEvidenceRequestId;

      evidenceLoading.style.display = "flex";
      evidenceError.style.display = "none";
      evidenceEmpty.style.display = "none";
      evidenceGrid.style.display = "none";

      function isRequestCurrent() {
        return (
          currentEvidenceRequestId === state.activeEvidenceRequestId &&
          evidenceModal.classList.contains("is-open") &&
          state.activeEvidenceNote !== null &&
          state.activeEvidenceNote.id === noteId
        );
      }

      fetch("/api/notes/" + encodeURIComponent(noteId) + "/attachments")
        .then(function (res) {
          if (!isRequestCurrent()) return null;
          if (!res.ok) {
            return res.json().then(function (errData) {
              throw new Error((errData && errData.detail) || ("Failed to load attachments (HTTP " + res.status + ")"));
            }).catch(function (parseErr) {
              if (parseErr.message && parseErr.message.indexOf("Failed to load") !== -1) throw parseErr;
              throw new Error("Failed to load attachments (HTTP " + res.status + ")");
            });
          }
          return res.json();
        })
        .then(function (attachments) {
          if (!isRequestCurrent() || attachments === null) return;
          evidenceLoading.style.display = "none";
          state.evidenceList = attachments || [];
          if (!Array.isArray(attachments) || attachments.length === 0) {
            evidenceEmpty.style.display = "flex";
          } else {
            evidenceGrid.style.display = "grid";
            renderEvidenceGrid(attachments, noteId);
          }
          if (typeof onComplete === "function") {
            onComplete(null, attachments);
          }
        })
        .catch(function (err) {
          if (!isRequestCurrent()) return;
          evidenceLoading.style.display = "none";
          evidenceError.style.display = "flex";
          evidenceErrorDesc.textContent = err.message || "Failed to load evidence attachments.";
          if (typeof onComplete === "function") {
            onComplete(err);
          }
        });
    }

    function renderEvidenceGrid(attachments, noteId) {
      evidenceGrid.innerHTML = "";

      attachments.forEach(function (att) {
        var card = document.createElement("article");
        card.className = "evidence-card";

        var thumbWrap = document.createElement("div");
        thumbWrap.className = "evidence-thumb-wrap";

        var img = document.createElement("img");
        img.className = "evidence-thumb";
        img.alt = att.caption || att.filename || "Evidence image preview";
        img.loading = "lazy";
        var downloadUrl = "/api/notes/" + encodeURIComponent(noteId) + "/attachments/" + encodeURIComponent(att.id) + "/download";
        img.src = downloadUrl;

        var brokenFallback = document.createElement("div");
        brokenFallback.className = "evidence-broken";
        brokenFallback.style.display = "none";
        brokenFallback.textContent = "Image preview unavailable";

        img.onerror = function () {
          img.onerror = null; // Prevent retry loop
          img.style.display = "none";
          brokenFallback.style.display = "flex";
        };

        thumbWrap.appendChild(img);
        thumbWrap.appendChild(brokenFallback);
        card.appendChild(thumbWrap);

        var info = document.createElement("div");
        info.className = "evidence-info";

        var captionEl = document.createElement("div");
        captionEl.className = "evidence-caption";
        captionEl.textContent = att.caption ? att.caption : att.filename;
        info.appendChild(captionEl);

        if (att.description) {
          var descEl = document.createElement("div");
          descEl.className = "evidence-desc";
          descEl.textContent = att.description;
          info.appendChild(descEl);
        }

        var metaEl = document.createElement("div");
        metaEl.className = "evidence-meta";
        var metaParts = [];
        if (typeof att.file_size === "number") {
          metaParts.push(formatFileSize(att.file_size));
        }
        if (att.created_at) {
          metaParts.push(formatUtcDate(att.created_at));
        }
        metaEl.textContent = metaParts.join(" • ");
        info.appendChild(metaEl);

        card.appendChild(info);

        var actions = document.createElement("div");
        actions.className = "evidence-card-actions";

        var viewBtn = document.createElement("button");
        viewBtn.type = "button";
        viewBtn.className = "action-btn";
        viewBtn.textContent = "View Full";
        viewBtn.setAttribute("aria-label", "View full image: " + (att.caption || att.filename));
        viewBtn.addEventListener("click", function () {
          openLightbox(att, noteId, viewBtn);
        });
        actions.appendChild(viewBtn);

        var deleteAttBtn = document.createElement("button");
        deleteAttBtn.type = "button";
        deleteAttBtn.className = "action-btn action-btn-danger";
        deleteAttBtn.textContent = "Delete";
        deleteAttBtn.setAttribute("aria-label", "Delete attachment: " + (att.caption || att.filename));
        deleteAttBtn.addEventListener("click", function () {
          openDeleteAttachmentModal(att, noteId, deleteAttBtn);
        });
        actions.appendChild(deleteAttBtn);

        card.appendChild(actions);
        evidenceGrid.appendChild(card);
      });
    }

    // Lightbox Controller
    function openLightbox(att, noteId, triggerBtn) {
      lightboxImg.src = "/api/notes/" + encodeURIComponent(noteId) + "/attachments/" + encodeURIComponent(att.id) + "/download";
      lightboxImg.alt = att.caption || att.filename || "Evidence full view";
      lightboxCaption.textContent = att.caption ? att.caption : att.filename;
      lightboxDesc.textContent = att.description || "";
      lightboxDesc.style.display = att.description ? "block" : "none";

      var metaItems = [];
      if (att.filename) metaItems.push("File: " + att.filename);
      if (typeof att.file_size === "number") metaItems.push("Size: " + formatFileSize(att.file_size));
      if (att.content_type) metaItems.push("Type: " + att.content_type);
      if (att.created_at) metaItems.push("Uploaded: " + formatUtcDate(att.created_at));
      lightboxMeta.textContent = metaItems.join(" • ");

      openDialog(lightboxModal, lightboxModalBackdrop, btnCloseLightboxModal);
    }

    function closeLightbox() {
      closeDialog(lightboxModal, lightboxModalBackdrop);
      lightboxImg.src = "";
    }

    // Delete Attachment Controller
    function openDeleteAttachmentModal(att, noteId, triggerBtn) {
      state.attachmentToDelete = { id: att.id, noteId: noteId, filename: att.filename, caption: att.caption };
      deleteAttachmentTargetName.textContent = '"' + (att.caption || att.filename) + '"';
      openDialog(deleteAttachmentModal, deleteAttachmentModalBackdrop, btnCancelDeleteAttachment);
    }

    function closeDeleteAttachmentModal() {
      state.attachmentToDelete = null;
      closeDialog(deleteAttachmentModal, deleteAttachmentModalBackdrop);
    }

    // Upload Evidence Form Submit Listener
    evidenceUploadForm.addEventListener("submit", function (e) {
      e.preventDefault();
      evidenceUploadError.style.display = "none";
      evidenceUploadError.textContent = "";

      if (!state.activeEvidenceNote) {
        evidenceUploadError.textContent = "No note selected.";
        evidenceUploadError.style.display = "block";
        return;
      }

      var file = evidenceFileInput.files && evidenceFileInput.files[0];
      if (!file) {
        evidenceUploadError.textContent = "Please select an image file to upload.";
        evidenceUploadError.style.display = "block";
        evidenceFileInput.focus();
        return;
      }

      // Client validation: 5 MB limit
      var MAX_BYTES = 5 * 1024 * 1024;
      if (file.size > MAX_BYTES) {
        evidenceUploadError.textContent = "File size (" + formatFileSize(file.size) + ") exceeds the maximum allowed limit of 5.0 MB.";
        evidenceUploadError.style.display = "block";
        evidenceFileInput.focus();
        return;
      }

      // Client validation: MIME type check
      var allowedTypes = ["image/jpeg", "image/png", "image/webp"];
      if (file.type && allowedTypes.indexOf(file.type.toLowerCase()) === -1) {
        evidenceUploadError.textContent = "Unsupported file type (" + file.type + "). Only JPEG, PNG, and WebP images are permitted.";
        evidenceUploadError.style.display = "block";
        evidenceFileInput.focus();
        return;
      }

      var noteId = state.activeEvidenceNote.id;
      var formData = new FormData();
      formData.append("file", file);

      var captionVal = evidenceCaptionInput.value.trim();
      if (captionVal) {
        formData.append("caption", captionVal);
      }

      var descVal = evidenceDescInput.value.trim();
      if (descVal) {
        formData.append("description", descVal);
      }

      btnUploadEvidence.disabled = true;
      btnUploadEvidence.textContent = "Uploading...";

      // Browser sets multipart/form-data boundary automatically when Content-Type is omitted
      fetch("/api/notes/" + encodeURIComponent(noteId) + "/attachments", {
        method: "POST",
        body: formData,
      })
        .then(function (res) {
          if (!res.ok) {
            return res.json().then(function (errData) {
              var msg = (errData && errData.detail) || ("Upload failed with HTTP " + res.status);
              if (Array.isArray(msg)) {
                msg = msg.map(function (m) { return m.msg || JSON.stringify(m); }).join("; ");
              }
              throw new Error(msg);
            }).catch(function (parseErr) {
              if (parseErr.message && parseErr.message.indexOf("Upload failed") !== -1) throw parseErr;
              throw new Error("Upload failed with HTTP " + res.status);
            });
          }
          return res.json();
        })
        .then(function (savedAttachment) {
          btnUploadEvidence.disabled = false;
          btnUploadEvidence.textContent = "Upload Evidence";
          evidenceUploadForm.reset();
          showToast("Evidence attached successfully", "success");
          loadEvidence();
        })
        .catch(function (err) {
          btnUploadEvidence.disabled = false;
          btnUploadEvidence.textContent = "Upload Evidence";
          evidenceUploadError.textContent = err.message || "Failed to upload image.";
          evidenceUploadError.style.display = "block";
          showToast(err.message, "error");
        });
    });

    // Evidence Modal Event Listeners
    btnCloseEvidenceModal.addEventListener("click", closeEvidenceModal);
    btnDoneEvidence.addEventListener("click", closeEvidenceModal);
    evidenceModalBackdrop.addEventListener("click", closeEvidenceModal);
    btnRetryEvidence.addEventListener("click", function () { loadEvidence(); });

    // Lightbox Modal Event Listeners
    btnCloseLightboxModal.addEventListener("click", closeLightbox);
    btnCloseLightbox.addEventListener("click", closeLightbox);
    lightboxModalBackdrop.addEventListener("click", closeLightbox);

    // Delete Attachment Modal Event Listeners
    btnCloseDeleteAttachmentModal.addEventListener("click", closeDeleteAttachmentModal);
    btnCancelDeleteAttachment.addEventListener("click", closeDeleteAttachmentModal);
    deleteAttachmentModalBackdrop.addEventListener("click", closeDeleteAttachmentModal);

    btnConfirmDeleteAttachment.addEventListener("click", function () {
      if (!state.attachmentToDelete) return;
      var attId = state.attachmentToDelete.id;
      var noteId = state.attachmentToDelete.noteId;

      btnConfirmDeleteAttachment.disabled = true;
      btnConfirmDeleteAttachment.textContent = "Deleting...";

      fetch("/api/notes/" + encodeURIComponent(noteId) + "/attachments/" + encodeURIComponent(attId), {
        method: "DELETE",
      })
        .then(function (res) {
          if (!res.ok && res.status !== 204) {
            return res.json().then(function (errData) {
              throw new Error((errData && errData.detail) || "Failed to delete attachment.");
            }).catch(function (parseErr) {
              if (parseErr.message && parseErr.message.indexOf("Failed to delete") !== -1) throw parseErr;
              throw new Error("Delete attachment failed with HTTP " + res.status);
            });
          }
          // HTTP 204 No Content - do NOT parse JSON body
          btnConfirmDeleteAttachment.disabled = false;
          btnConfirmDeleteAttachment.textContent = "Delete Evidence";

          // Avoid focusing a button that is about to be unmounted from DOM
          deleteAttachmentModal._previousFocus = null;
          closeDialog(deleteAttachmentModal, deleteAttachmentModalBackdrop);
          state.attachmentToDelete = null;
          showToast("Attachment deleted successfully", "success");

          // Refresh gallery and restore focus to stable control inside evidenceModal
          loadEvidence(function (err) {
            if (evidenceModal.classList.contains("is-open")) {
              if (err && btnRetryEvidence && typeof btnRetryEvidence.focus === "function") {
                btnRetryEvidence.focus();
              } else if (btnUploadEvidence && typeof btnUploadEvidence.focus === "function") {
                btnUploadEvidence.focus();
              } else if (btnCloseEvidenceModal && typeof btnCloseEvidenceModal.focus === "function") {
                btnCloseEvidenceModal.focus();
              }
            }
          });
        })
        .catch(function (err) {
          btnConfirmDeleteAttachment.disabled = false;
          btnConfirmDeleteAttachment.textContent = "Delete Evidence";
          // On failure, preserve _previousFocus so user focus returns to delete button of the retained card
          closeDialog(deleteAttachmentModal, deleteAttachmentModalBackdrop);
          state.attachmentToDelete = null;
          showToast(err.message || "Failed to delete attachment", "error");
        });
    });

    // Global Keydown: Escape closes open dialog, Tab traps focus inside active dialog
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.key === "Esc") {
        if (lightboxModal.classList.contains("is-open")) {
          closeLightbox();
        } else if (deleteAttachmentModal.classList.contains("is-open")) {
          closeDeleteAttachmentModal();
        } else if (evidenceModal.classList.contains("is-open")) {
          closeEvidenceModal();
        } else if (noteModal.classList.contains("is-open")) {
          closeDialog(noteModal, noteModalBackdrop);
        } else if (deleteModal.classList.contains("is-open")) {
          closeDialog(deleteModal, deleteModalBackdrop);
        }
        return;
      }

      if (e.key === "Tab") {
        if (lightboxModal.classList.contains("is-open")) {
          trapModalFocus(lightboxModal, e);
        } else if (deleteAttachmentModal.classList.contains("is-open")) {
          trapModalFocus(deleteAttachmentModal, e);
        } else if (evidenceModal.classList.contains("is-open")) {
          trapModalFocus(evidenceModal, e);
        } else if (noteModal.classList.contains("is-open")) {
          trapModalFocus(noteModal, e);
        } else if (deleteModal.classList.contains("is-open")) {
          trapModalFocus(deleteModal, e);
        }
      }
    });

    // Memory Navigation Views Switcher (Timeline, Recall, Capture, Archive)
    var navTabs = document.querySelectorAll(".memory-nav-tab");
    var recallPrompts = document.getElementById("recall-prompts-section");
    var tagFilterSec = document.getElementById("tag-filter-section");

    function setView(viewName) {
      navTabs.forEach(function (tab) {
        var isCurrent = tab.getAttribute("data-view") === viewName;
        tab.classList.toggle("active", isCurrent);
        tab.setAttribute("aria-selected", isCurrent ? "true" : "false");
      });

      if (viewName === "timeline") {
        if (recallPrompts) recallPrompts.style.display = "none";
        if (tagFilterSec) tagFilterSec.style.display = "none";
        if (state.searchMode !== "text") {
          setSearchMode("text");
        }
        if (state.searchQuery || state.tagFilter) {
          state.searchQuery = "";
          searchInput.value = "";
          state.tagFilter = "";
          tagFilterInput.value = "";
          btnClearTags.style.display = "none";
          btnSearchClear.style.display = "none";
          state.skip = 0;
          loadNotes();
        }
      } else if (viewName === "recall") {
        if (recallPrompts) recallPrompts.style.display = "block";
        if (tagFilterSec) tagFilterSec.style.display = "none";
        setSearchMode("semantic");
        searchInput.focus();
      } else if (viewName === "capture") {
        openCreateModal();
        setView("timeline");
        return;
      } else if (viewName === "archive") {
        if (recallPrompts) recallPrompts.style.display = "none";
        if (tagFilterSec) tagFilterSec.style.display = "block";
      }
    }

    navTabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        setView(tab.getAttribute("data-view"));
      });
    });

    // Hash navigation support: #capture, #timeline, #recall, #archive
    function checkHashRoute() {
      var hash = window.location.hash.replace("#", "").toLowerCase();
      if (hash === "capture" || hash === "recall" || hash === "archive" || hash === "timeline") {
        setView(hash);
      }
    }
    window.addEventListener("hashchange", checkHashRoute);
    if (window.location.hash) {
      checkHashRoute();
    } else {
      // Default to Timeline clean view
      if (recallPrompts) recallPrompts.style.display = "none";
      if (tagFilterSec) tagFilterSec.style.display = "none";
    }

    // Natural Language Recall Prompt Suggestion Chips
    var promptChips = document.querySelectorAll(".recall-prompt-chip");
    promptChips.forEach(function (chip) {
      chip.addEventListener("click", function () {
        var query = chip.getAttribute("data-query");
        if (!query) return;
        searchInput.value = query;
        state.searchQuery = query;
        btnSearchClear.style.display = "inline-flex";
        setSearchMode("semantic");
        state.skip = 0;
        loadNotes();
      });
    });

    // Initial Load of Notes
    loadNotes();
  }

  /* ==========================================================================
     5. Research Analytics Controller (Phase 2C.2)
     ========================================================================== */
  function initAnalytics() {
    var analyticsDashboard = document.getElementById("analytics-dashboard");
    if (!analyticsDashboard) return;

    // Independent request IDs to protect every section against race conditions & out-of-order responses
    var reqIds = {
      overview: 0,
      tags: 0,
      activity: 0,
      attachments: 0
    };

    // DOM Elements
    var btnRefresh = document.getElementById("btn-refresh-analytics");

    // Overview Section Elements
    var overviewLoading = document.getElementById("overview-loading");
    var overviewError = document.getElementById("overview-error");
    var overviewErrorDesc = document.getElementById("overview-error-desc");
    var btnRetryOverview = document.getElementById("btn-retry-overview");
    var statTotalNotes = document.getElementById("stat-total-notes");
    var statTotalAttachments = document.getElementById("stat-total-attachments");
    var statNotesWithTags = document.getElementById("stat-notes-with-tags");

    // Tag Distribution Section Elements
    var tagsLoading = document.getElementById("tags-loading");
    var tagsError = document.getElementById("tags-error");
    var tagsErrorDesc = document.getElementById("tags-error-desc");
    var btnRetryTags = document.getElementById("btn-retry-tags");
    var tagsEmpty = document.getElementById("tags-empty");
    var tagsChartContainer = document.getElementById("tags-chart-container");
    var tagsChartBars = document.getElementById("tags-chart-bars");

    // Activity Timeline Section Elements
    var activityLoading = document.getElementById("activity-loading");
    var activityError = document.getElementById("activity-error");
    var activityErrorDesc = document.getElementById("activity-error-desc");
    var btnRetryActivity = document.getElementById("btn-retry-activity");
    var activityEmpty = document.getElementById("activity-empty");
    var activityChartContainer = document.getElementById("activity-chart-container");
    var activityTimelineList = document.getElementById("activity-timeline-list");

    // Evidence Distribution Section Elements
    var toggleIncludeZero = document.getElementById("toggle-include-zero");
    var attachmentsLoading = document.getElementById("attachments-loading");
    var attachmentsError = document.getElementById("attachments-error");
    var attachmentsErrorDesc = document.getElementById("attachments-error-desc");
    var btnRetryAttachments = document.getElementById("btn-retry-attachments");
    var attachmentsEmpty = document.getElementById("attachments-empty");
    var attachmentsEmptyDesc = document.getElementById("attachments-empty-desc");
    var attachmentsChartContainer = document.getElementById("attachments-chart-container");
    var attachmentsCountInfo = document.getElementById("attachments-count-info");
    var attachmentsChartList = document.getElementById("attachments-chart-list");

    // Section 1: Overview
    function loadOverview() {
      var currentId = ++reqIds.overview;
      if (overviewLoading) overviewLoading.style.display = "flex";
      if (overviewError) overviewError.style.display = "none";

      return fetch("/api/analytics/overview")
        .then(function (res) {
          if (currentId !== reqIds.overview) return null;
          if (!res.ok) {
            return res.json().then(function (err) {
              throw new Error((err && err.detail) || ("Failed to load overview (HTTP " + res.status + ")"));
            }).catch(function (pErr) {
              if (pErr.message && pErr.message.indexOf("Failed to load") !== -1) throw pErr;
              throw new Error("Failed to load overview (HTTP " + res.status + ")");
            });
          }
          return res.json();
        })
        .then(function (data) {
          if (currentId !== reqIds.overview || data === null) return;
          if (overviewLoading) overviewLoading.style.display = "none";
          if (statTotalNotes) {
            statTotalNotes.textContent = typeof data.total_notes === "number" ? data.total_notes.toLocaleString() : "0";
          }
          if (statTotalAttachments) {
            statTotalAttachments.textContent = typeof data.total_attachments === "number" ? data.total_attachments.toLocaleString() : "0";
          }
          if (statNotesWithTags) {
            statNotesWithTags.textContent = typeof data.notes_with_tags === "number" ? data.notes_with_tags.toLocaleString() : "0";
          }
        })
        .catch(function (err) {
          if (currentId !== reqIds.overview) return;
          if (overviewLoading) overviewLoading.style.display = "none";
          if (overviewError) overviewError.style.display = "flex";
          if (overviewErrorDesc) {
            overviewErrorDesc.textContent = err.message || "Failed to load research overview.";
          }
        });
    }

    // Section 2: Tag Distribution
    function renderTagsDistribution(tags) {
      if (!tagsChartBars) return;
      tagsChartBars.innerHTML = "";
      var maxCount = 0;
      for (var i = 0; i < tags.length; i++) {
        if (tags[i].count > maxCount) maxCount = tags[i].count;
      }
      if (maxCount <= 0) maxCount = 1;

      tags.forEach(function (item) {
        var row = document.createElement("div");
        row.className = "chart-bar-row";

        var header = document.createElement("div");
        header.className = "chart-bar-header";

        var label = document.createElement("span");
        label.className = "chart-bar-label tag-pill-label";
        label.textContent = item.tag;
        label.title = item.tag;

        var val = document.createElement("span");
        val.className = "chart-bar-value";
        val.textContent = item.count + (item.count === 1 ? " note" : " notes");

        header.appendChild(label);
        header.appendChild(val);

        var track = document.createElement("div");
        track.className = "chart-bar-track";

        var fill = document.createElement("div");
        fill.className = "chart-bar-fill fill-primary";
        var pct = Math.round((item.count / maxCount) * 100);
        fill.style.width = pct + "%";
        fill.setAttribute("role", "progressbar");
        fill.setAttribute("aria-valuenow", String(item.count));
        fill.setAttribute("aria-valuemin", "0");
        fill.setAttribute("aria-valuemax", String(maxCount));
        fill.setAttribute("aria-label", "Tag " + item.tag + ": " + item.count + " notes");

        track.appendChild(fill);

        row.appendChild(header);
        row.appendChild(track);
        tagsChartBars.appendChild(row);
      });
    }

    function loadTags() {
      var currentId = ++reqIds.tags;
      if (tagsLoading) tagsLoading.style.display = "flex";
      if (tagsError) tagsError.style.display = "none";
      if (tagsEmpty) tagsEmpty.style.display = "none";
      if (tagsChartContainer) tagsChartContainer.style.display = "none";

      return fetch("/api/analytics/tags")
        .then(function (res) {
          if (currentId !== reqIds.tags) return null;
          if (!res.ok) {
            return res.json().then(function (err) {
              throw new Error((err && err.detail) || ("Failed to load tags (HTTP " + res.status + ")"));
            }).catch(function (pErr) {
              if (pErr.message && pErr.message.indexOf("Failed to load") !== -1) throw pErr;
              throw new Error("Failed to load tags (HTTP " + res.status + ")");
            });
          }
          return res.json();
        })
        .then(function (tags) {
          if (currentId !== reqIds.tags || tags === null) return;
          if (tagsLoading) tagsLoading.style.display = "none";
          if (!Array.isArray(tags) || tags.length === 0) {
            if (tagsEmpty) tagsEmpty.style.display = "flex";
          } else {
            renderTagsDistribution(tags);
            if (tagsChartContainer) tagsChartContainer.style.display = "block";
          }
        })
        .catch(function (err) {
          if (currentId !== reqIds.tags) return;
          if (tagsLoading) tagsLoading.style.display = "none";
          if (tagsError) tagsError.style.display = "flex";
          if (tagsErrorDesc) {
            tagsErrorDesc.textContent = err.message || "Failed to load tag distribution.";
          }
        });
    }

    // Section 3: Research Activity
    function renderResearchActivity(activity) {
      if (!activityTimelineList) return;
      activityTimelineList.innerHTML = "";
      var maxCount = 0;
      for (var i = 0; i < activity.length; i++) {
        if (activity[i].count > maxCount) maxCount = activity[i].count;
      }
      if (maxCount <= 0) maxCount = 1;

      activity.forEach(function (item) {
        var row = document.createElement("div");
        row.className = "chart-bar-row";

        var header = document.createElement("div");
        header.className = "chart-bar-header";

        var dateLabel = document.createElement("span");
        dateLabel.className = "chart-bar-label font-mono";
        dateLabel.textContent = item.date + " (UTC)";
        dateLabel.title = item.date + " UTC";

        var val = document.createElement("span");
        val.className = "chart-bar-value";
        val.textContent = item.count + (item.count === 1 ? " note" : " notes");

        header.appendChild(dateLabel);
        header.appendChild(val);

        var track = document.createElement("div");
        track.className = "chart-bar-track";

        var fill = document.createElement("div");
        fill.className = "chart-bar-fill fill-accent";
        var pct = Math.round((item.count / maxCount) * 100);
        fill.style.width = pct + "%";
        fill.setAttribute("role", "progressbar");
        fill.setAttribute("aria-valuenow", String(item.count));
        fill.setAttribute("aria-valuemin", "0");
        fill.setAttribute("aria-valuemax", String(maxCount));
        fill.setAttribute("aria-label", item.date + " UTC: " + item.count + " notes");

        track.appendChild(fill);

        row.appendChild(header);
        row.appendChild(track);
        activityTimelineList.appendChild(row);
      });
    }

    function loadActivity() {
      var currentId = ++reqIds.activity;
      if (activityLoading) activityLoading.style.display = "flex";
      if (activityError) activityError.style.display = "none";
      if (activityEmpty) activityEmpty.style.display = "none";
      if (activityChartContainer) activityChartContainer.style.display = "none";

      return fetch("/api/analytics/activity")
        .then(function (res) {
          if (currentId !== reqIds.activity) return null;
          if (!res.ok) {
            return res.json().then(function (err) {
              throw new Error((err && err.detail) || ("Failed to load activity (HTTP " + res.status + ")"));
            }).catch(function (pErr) {
              if (pErr.message && pErr.message.indexOf("Failed to load") !== -1) throw pErr;
              throw new Error("Failed to load activity (HTTP " + res.status + ")");
            });
          }
          return res.json();
        })
        .then(function (activity) {
          if (currentId !== reqIds.activity || activity === null) return;
          if (activityLoading) activityLoading.style.display = "none";
          if (!Array.isArray(activity) || activity.length === 0) {
            if (activityEmpty) activityEmpty.style.display = "flex";
          } else {
            renderResearchActivity(activity);
            if (activityChartContainer) activityChartContainer.style.display = "block";
          }
        })
        .catch(function (err) {
          if (currentId !== reqIds.activity) return;
          if (activityLoading) activityLoading.style.display = "none";
          if (activityError) activityError.style.display = "flex";
          if (activityErrorDesc) {
            activityErrorDesc.textContent = err.message || "Failed to load research activity.";
          }
        });
    }

    // Section 4: Evidence Distribution
    function renderEvidenceDistribution(attachments) {
      if (!attachmentsChartList) return;
      attachmentsChartList.innerHTML = "";
      var totalReturned = attachments.length;
      var maxDisplay = 25;
      var sliced = attachments.slice(0, maxDisplay);

      if (attachmentsCountInfo) {
        if (totalReturned > maxDisplay) {
          attachmentsCountInfo.textContent = "Showing top " + maxDisplay + " of " + totalReturned + " research notes";
        } else {
          attachmentsCountInfo.textContent = "Showing " + totalReturned + " of " + totalReturned + " research notes";
        }
      }

      var maxCount = 0;
      for (var i = 0; i < sliced.length; i++) {
        if (sliced[i].attachment_count > maxCount) maxCount = sliced[i].attachment_count;
      }
      if (maxCount <= 0) maxCount = 1;

      sliced.forEach(function (item) {
        var row = document.createElement("div");
        row.className = "chart-bar-row";

        var header = document.createElement("div");
        header.className = "chart-bar-header";

        var titleSpan = document.createElement("span");
        titleSpan.className = "chart-bar-label chart-bar-title-truncate";
        titleSpan.textContent = item.title;
        titleSpan.title = item.title;
        titleSpan.setAttribute("aria-label", item.title);

        var val = document.createElement("span");
        val.className = "chart-bar-value";
        val.textContent = item.attachment_count + (item.attachment_count === 1 ? " attachment" : " attachments");

        header.appendChild(titleSpan);
        header.appendChild(val);

        var track = document.createElement("div");
        track.className = "chart-bar-track";

        var fill = document.createElement("div");
        fill.className = "chart-bar-fill fill-secondary";
        var pct = item.attachment_count > 0 ? Math.round((item.attachment_count / maxCount) * 100) : 0;
        fill.style.width = pct + "%";
        fill.setAttribute("role", "progressbar");
        fill.setAttribute("aria-valuenow", String(item.attachment_count));
        fill.setAttribute("aria-valuemin", "0");
        fill.setAttribute("aria-valuemax", String(maxCount));
        fill.setAttribute("aria-label", item.title + ": " + item.attachment_count + " attachments");

        track.appendChild(fill);

        row.appendChild(header);
        row.appendChild(track);
        attachmentsChartList.appendChild(row);
      });
    }

    function loadAttachments() {
      var includeZero = toggleIncludeZero ? toggleIncludeZero.checked : true;
      var currentId = ++reqIds.attachments;

      if (attachmentsLoading) attachmentsLoading.style.display = "flex";
      if (attachmentsError) attachmentsError.style.display = "none";
      if (attachmentsEmpty) attachmentsEmpty.style.display = "none";
      if (attachmentsChartContainer) attachmentsChartContainer.style.display = "none";

      var url = "/api/analytics/attachments?include_zero=" + (includeZero ? "true" : "false");

      return fetch(url)
        .then(function (res) {
          if (currentId !== reqIds.attachments) return null;
          if (!res.ok) {
            return res.json().then(function (err) {
              throw new Error((err && err.detail) || ("Failed to load attachments summary (HTTP " + res.status + ")"));
            }).catch(function (pErr) {
              if (pErr.message && pErr.message.indexOf("Failed to load") !== -1) throw pErr;
              throw new Error("Failed to load attachments summary (HTTP " + res.status + ")");
            });
          }
          return res.json();
        })
        .then(function (attachments) {
          if (currentId !== reqIds.attachments || attachments === null) return;
          if (attachmentsLoading) attachmentsLoading.style.display = "none";
          if (!Array.isArray(attachments) || attachments.length === 0) {
            if (attachmentsEmpty) attachmentsEmpty.style.display = "flex";
            if (attachmentsEmptyDesc) {
              attachmentsEmptyDesc.textContent = includeZero
                ? "No research notes exist in the database."
                : "No research notes currently have evidence attachments.";
            }
          } else {
            renderEvidenceDistribution(attachments);
            if (attachmentsChartContainer) attachmentsChartContainer.style.display = "block";
          }
        })
        .catch(function (err) {
          if (currentId !== reqIds.attachments) return;
          if (attachmentsLoading) attachmentsLoading.style.display = "none";
          if (attachmentsError) attachmentsError.style.display = "flex";
          if (attachmentsErrorDesc) {
            attachmentsErrorDesc.textContent = err.message || "Failed to load evidence distribution.";
          }
        });
    }

    function loadAllAnalytics() {
      // Use Promise.allSettled so individual failures do not disrupt other sections
      if (typeof Promise.allSettled === "function") {
        Promise.allSettled([
          loadOverview(),
          loadTags(),
          loadActivity(),
          loadAttachments()
        ]);
      } else {
        loadOverview();
        loadTags();
        loadActivity();
        loadAttachments();
      }
    }

    // Attach Event Listeners
    if (btnRefresh) {
      btnRefresh.addEventListener("click", function () {
        loadAllAnalytics();
      });
    }

    if (btnRetryOverview) {
      btnRetryOverview.addEventListener("click", function () {
        loadOverview();
      });
    }

    if (btnRetryTags) {
      btnRetryTags.addEventListener("click", function () {
        loadTags();
      });
    }

    if (btnRetryActivity) {
      btnRetryActivity.addEventListener("click", function () {
        loadActivity();
      });
    }

    if (btnRetryAttachments) {
      btnRetryAttachments.addEventListener("click", function () {
        loadAttachments();
      });
    }

    if (toggleIncludeZero) {
      toggleIncludeZero.addEventListener("change", function () {
        loadAttachments();
      });
    }

    // Initial load
    loadAllAnalytics();
  }

  // Initialize all features on DOM Ready
  document.addEventListener("DOMContentLoaded", function () {
    initDynamicYear();
    initMobileNavigation();
    initDashboard();
    initAnalytics();
  });
})();
