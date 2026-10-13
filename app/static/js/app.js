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

    // Modal Elements
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

    var deleteModal = document.getElementById("delete-modal");
    var deleteModalBackdrop = document.getElementById("delete-modal-backdrop");
    var deleteNoteTargetTitle = document.getElementById("delete-note-target-title");
    var btnCloseDeleteModal = document.getElementById("btn-close-delete-modal");
    var btnCancelDelete = document.getElementById("btn-cancel-delete");
    var btnConfirmDelete = document.getElementById("btn-confirm-delete");

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

    // Modal Show/Hide Helpers
    function openDialog(modal, backdrop, focusTarget) {
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
      document.body.style.overflow = "";
      if (state.lastModalFocus && typeof state.lastModalFocus.focus === "function") {
        state.lastModalFocus.focus();
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
    function renderNotesGrid(notes, isSemantic) {
      notesGrid.innerHTML = "";

      notes.forEach(function (note) {
        var card = document.createElement("article");
        card.className = "note-card";
        card.setAttribute("tabindex", "0");

        // Header: Title + Optional Semantic Score Badge
        var header = document.createElement("div");
        header.className = "note-card-header";

        var title = document.createElement("h2");
        title.className = "note-card-title";
        title.textContent = note.title;
        header.appendChild(title);

        if (isSemantic && typeof note.score === "number") {
          var scoreBadge = document.createElement("span");
          scoreBadge.className = "score-badge";
          scoreBadge.textContent = "Score: " + note.score.toFixed(4);
          header.appendChild(scoreBadge);
        }
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
      noteModalTitle.textContent = "Create Research Note";
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
          noteModalTitle.textContent = "Edit Research Note";
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

      if (!titleVal) {
        modalErrorAlert.textContent = "Title is required and cannot be empty.";
        modalErrorAlert.style.display = "block";
        noteTitleInput.focus();
        return;
      }

      var isEdit = Boolean(noteEditId.value);
      var method = isEdit ? "PUT" : "POST";
      var url = isEdit ? ("/api/notes/" + encodeURIComponent(noteEditId.value)) : "/api/notes";

      var payload = {
        title: titleVal,
        content: contentVal,
        tags: tagsVal,
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

    // Global Keydown: Escape closes dialog, Tab traps focus inside open dialog
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" || e.key === "Esc") {
        if (noteModal.classList.contains("is-open")) {
          closeDialog(noteModal, noteModalBackdrop);
        } else if (deleteModal.classList.contains("is-open")) {
          closeDialog(deleteModal, deleteModalBackdrop);
        }
        return;
      }

      if (e.key === "Tab") {
        if (noteModal.classList.contains("is-open")) {
          trapModalFocus(noteModal, e);
        } else if (deleteModal.classList.contains("is-open")) {
          trapModalFocus(deleteModal, e);
        }
      }
    });

    // Initial Load of Notes
    loadNotes();
  }

  // Initialize all features on DOM Ready
  document.addEventListener("DOMContentLoaded", function () {
    initDynamicYear();
    initMobileNavigation();
    initDashboard();
  });
})();
