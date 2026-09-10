/**
   * Veylo File Manager & Submissions Client
   *
   * Coordinates:
   * 1. Dataverse Web API (/_api/) for submissions history & ingestion error logging.
   * 2. MSAL.js client authentication for acquiring Bearer tokens for Azure Function.
   * 3. Pre-Signed SAS generation via Azure Function (/api/upload-request).
   * 4. Direct binary PUT upload to Azure Blob Storage with progress tracking.
   * 5. Upload completion confirmation (/api/upload-complete).
   * 6. Authorized file download ticket retrieval (/api/download).
   */
(function () {
  'use strict';

  // ============================================================
  // Configuration
  // ============================================================
  var CONFIG = {
    tenantId: 'd63e78bd-9ee3-4a7d-a868-738824c13bd1',
    clientId: '5a7e8db6-561b-4a60-aed2-f0c652661f0d', // Frontend SPA Client ID
    apiScope: 'api://func-vey-portal-dev/File.Upload',
    functionBaseUrl: 'https://func-vey-portal-dev-up-01.azurewebsites.net',
    maxSizeBytes: 50 * 1024 * 1024, // 50 MB
    allowedExtensions: ['.pdf', '.docx', '.xlsx', '.csv', '.png', '.jpg', '.jpeg', '.txt', '.zip']
  };

  // Detect local development environment
  var isLocalDev = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1';

  // ============================================================
  // State
  // ============================================================
  var state = {
    selectedFile: null,
    selectedFileHash: '',
    currentOrgId: '',
    currentOrgName: '',
    currentContactId: '',
    submissions: [],
    currentUploadXhr: null,
    msalInstance: null
  };

  // Status mapping
  var STATUS_LABELS = {
    948740000: { text: 'Uploaded', cls: 'fm-status-pill--uploaded' },
    948740001: { text: 'Validating', cls: 'fm-status-pill--validating' },
    948740002: { text: 'Processed', cls: 'fm-status-pill--processed' },
    948740003: { text: 'Partial Success', cls: 'fm-status-pill--partial' },
    948740004: { text: 'Failed', cls: 'fm-status-pill--failed' }
  };

  // ============================================================
  // UI Helpers
  // ============================================================
  function showStatus(message, type) {
    var el = document.getElementById('fm-status');
    if (!el) return;
    el.textContent = message;

    var hdsType = 'info';
    if (type === 'success' || type === 'warning' || type === 'error') {
      hdsType = type;
    }

    el.className = 'au-page-alerts';
    if (hdsType !== 'info') {
      el.className += ' au-page-alerts--' + hdsType;
    }

    el.style.display = 'block';
    if (type === 'success') {
      setTimeout(function () { el.style.display = 'none'; }, 5000);
    }
  }

  function esc(str) {
    if (!str) return '';
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  function formatBytes(bytes) {
    if (!bytes || bytes === 0) return '0 B';
    var k = 1024;
    var sizes = ['B', 'KB', 'MB', 'GB'];
    var i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  function formatDate(isoStr) {
    if (!isoStr) return '\u2014';
    try {
      var d = new Date(isoStr);
      return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoStr;
    }
  }

  // ============================================================
  // MSAL Authentication
  // ============================================================
  function initMsal() {
    if (typeof msal === 'undefined') {
      console.warn('MSAL library not loaded; local mock or offline mode active.');
      return;
    }

    try {
      var msalConfig = {
        auth: {
          clientId: CONFIG.clientId,
          authority: 'https://login.microsoftonline.com/' + CONFIG.tenantId,
          redirectUri: window.location.origin + window.location.pathname
        },
        cache: {
          cacheLocation: 'sessionStorage',
          storeAuthStateInCookie: false
        }
      };
      state.msalInstance = new msal.PublicClientApplication(msalConfig);
    } catch (ex) {
      console.error('Failed to initialize MSAL:', ex);
    }
  }

  function getAccessToken() {
    if (isLocalDev && (!state.msalInstance || !state.msalInstance.getAllAccounts().length)) {
      // Local development mock token
      return Promise.resolve('dev-mock-token');
    }

    if (!state.msalInstance && typeof msal !== 'undefined') {
      initMsal();
    }

    if (!state.msalInstance) {
      return Promise.reject(new Error('MSAL library is not initialized. Please ensure msal-browser.min.js is loaded.'));
    }

    var accounts = state.msalInstance.getAllAccounts();
    var tokenRequest = {
      scopes: [CONFIG.apiScope],
      account: accounts[0]
    };

    return state.msalInstance.acquireTokenSilent(tokenRequest).then(function (res) {
      return res.accessToken;
    }).catch(function (silentErr) {
      console.info('Silent token acquisition failed, prompting with popup:', silentErr);
      return state.msalInstance.acquireTokenPopup(tokenRequest).then(function (res) {
        return res.accessToken;
      }).catch(function (popupErr) {
        var msg = popupErr.errorMessage || popupErr.message || String(popupErr);
        throw new Error(
          'Entra ID authentication required. ' +
          'Direct Azure upload requires an active Microsoft Entra ID session. ' +
          'Users registered via standard portal accounts must sign in or link their account with Microsoft Entra ID. (' + msg + ')'
        );
      });
    });
  }

  // ============================================================
  // Cryptographic Hashing (SHA-256)
  // ============================================================
  function computeFileHash(file) {
    if (!window.crypto || !window.crypto.subtle) {
      return Promise.resolve('SHA256_UNSUPPORTED_BROWSER');
    }

    return file.arrayBuffer().then(function (buffer) {
      return crypto.subtle.digest('SHA-256', buffer);
    }).then(function (hashBuffer) {
      var hashArray = Array.from(new Uint8Array(hashBuffer));
      var hashHex = hashArray.map(function (b) {
        return b.toString(16).padStart(2, '0');
      }).join('');
      return hashHex;
    });
  }

  // ============================================================
  // Power Pages Web API (/_api/)
  // ============================================================
  function apiRequest(method, endpoint, body) {
    var headers = {
      'Accept': 'application/json',
      'OData-MaxVersion': '4.0',
      'OData-Version': '4.0'
    };

    var tokenPromise = Promise.resolve('');

    if (method !== 'GET') {
      headers['Content-Type'] = 'application/json';
      if (window.shell && window.shell.getTokenDeferred) {
        tokenPromise = new Promise(function (resolve) {
          window.shell.getTokenDeferred().done(function (token) {
            resolve(token);
          });
        });
      } else {
        var el = document.querySelector('input[name="__RequestVerificationToken"]');
        tokenPromise = Promise.resolve(el ? el.value : '');
      }
    }

    return tokenPromise.then(function (token) {
      if (token) headers['__RequestVerificationToken'] = token;
      var opts = { method: method, headers: headers };
      if (body) opts.body = JSON.stringify(body);
      return fetch('/_api/' + endpoint, opts);
    }).then(function (response) {
      if (!response.ok) {
        return response.text().then(function (text) {
          throw new Error('API ' + response.status + ': ' + text);
        });
      }
      if (response.status === 204) return null;
      return response.json();
    });
  }

  // ============================================================
  // Data Loading: User Organization & Submissions
  // ============================================================
  function loadCurrentUserAndOrg() {
    var ctx = document.getElementById('fm-portal-context');
    if (ctx) {
      state.currentContactId = ctx.getAttribute('data-contact-id') || '';
      state.currentOrgId = ctx.getAttribute('data-org-id') || '';
      state.currentOrgName = ctx.getAttribute('data-org-name') || '';

      if (state.currentOrgName) {
        var el = document.getElementById('fm-current-org-name');
        if (el) el.textContent = state.currentOrgName;
      }

      if (state.currentContactId) {
        return Promise.resolve();
      }
    }

    return apiRequest('GET', 'contacts?$select=contactid,fullname,emailaddress1,_parentcustomerid_value&$top=1')
      .then(function (data) {
        var contact = (data.value && data.value[0]) || {};
        state.currentContactId = contact.contactid || '';
        state.currentOrgId = contact._parentcustomerid_value || '';

        if (state.currentOrgId) {
          return apiRequest('GET', 'accounts(' + state.currentOrgId + ')?$select=name')
            .then(function (acc) {
              state.currentOrgName = acc.name || 'Your Organisation';
              var el = document.getElementById('fm-current-org-name');
              if (el) el.textContent = state.currentOrgName;
            });
        } else {
          var el = document.getElementById('fm-current-org-name');
          if (el) el.textContent = 'Unassigned Organisation';
        }
      })
      .catch(function (err) {
        console.warn('Failed to load user org info:', err);
        var el = document.getElementById('fm-current-org-name');
        if (el && !state.currentOrgName) el.textContent = 'Default Organisation';
      });
  }

  function loadSubmissions() {
    var selectFields = [
      'vey_filesubmissionid',
      'vey_filename',
      'vey_submissionreference',
      'vey_filesizebytes',
      'vey_filehash',
      'vey_schemaversion',
      'vey_submissionstatus',
      'vey_reportingperiodstart',
      'vey_reportingperiodend',
      'createdon',
      'vey_storageuri'
    ].join(',');

    return apiRequest('GET', 'vey_filesubmissions?$select=' + selectFields + '&$orderby=createdon desc')
      .then(function (data) {
        state.submissions = data.value || [];
        renderSubmissionsTable();
      })
      .catch(function (err) {
        console.error('Failed to load submissions:', err);
        showStatus('Failed to load submissions list. Check permissions or network connection.', 'error');
      });
  }

  function loadIngestionErrors(submissionId) {
    var selectFields = 'vey_fileingestionerrorid,vey_rownumber,vey_errorcode,vey_errormessage,vey_errorreference,vey_rawpayload,createdon';
    return apiRequest('GET', 'vey_fileingestionerrors?$filter=_vey_filesubmission_value eq ' + submissionId + '&$select=' + selectFields)
      .then(function (data) {
        return data.value || [];
      })
      .catch(function (err) {
        console.warn('Failed to load ingestion errors:', err);
        return [];
      });
  }

  // ============================================================
  // Rendering
  // ============================================================
  function renderSubmissionsTable() {
    var tbody = document.getElementById('fm-submissions-tbody');
    if (!tbody) return;

    var searchTerm = (document.getElementById('fm-search-input') && document.getElementById('fm-search-input').value.toLowerCase().trim()) || '';
    var statusFilter = (document.getElementById('fm-status-filter') && document.getElementById('fm-status-filter').value) || '';

    var filtered = state.submissions.filter(function (s) {
      var matchesSearch = !searchTerm ||
        (s.vey_submissionreference && s.vey_submissionreference.toLowerCase().indexOf(searchTerm) !== -1) ||
        (s.vey_filename && s.vey_filename.toLowerCase().indexOf(searchTerm) !== -1);
      var matchesStatus = !statusFilter || String(s.vey_submissionstatus) === String(statusFilter);
      return matchesSearch && matchesStatus;
    });

    if (filtered.length === 0) {
      tbody.innerHTML = '<tr><td colspan="8" class="text-center" style="padding: 24px; color: #666;">No submissions found.</td></tr>';
      return;
    }

    var rows = '';
    filtered.forEach(function (s) {
      var statusObj = STATUS_LABELS[s.vey_submissionstatus] || { text: 'Uploaded', cls: 'fm-status-pill--uploaded' };
      var period = '\u2014';
      if (s.vey_reportingperiodstart || s.vey_reportingperiodend) {
        var startStr = s.vey_reportingperiodstart ? s.vey_reportingperiodstart.split('T')[0] : '...';
        var endStr = s.vey_reportingperiodend ? s.vey_reportingperiodend.split('T')[0] : '...';
        period = startStr + ' to ' + endStr;
      }

      rows += '<tr style="cursor: pointer;" data-id="' + s.vey_filesubmissionid + '">';
      rows += '<td><strong>' + esc(s.vey_submissionreference || s.vey_filename || '—') + '</strong></td>';
      rows += '<td>' + esc(s.vey_filename) + '</td>';
      rows += '<td>' + (s.vey_schemaversion ? '<span class="au-tag">' + esc(s.vey_schemaversion) + '</span>' : '\u2014') + '</td>';
      rows += '<td>' + formatBytes(s.vey_filesizebytes) + '</td>';
      rows += '<td>' + esc(period) + '</td>';
      rows += '<td>' + formatDate(s.createdon) + '</td>';
      rows += '<td><span class="fm-status-pill ' + statusObj.cls + '">' + esc(statusObj.text) + '</span></td>';
      rows += '<td>';
      rows += '<button type="button" class="au-btn au-btn--secondary au-btn--sm js-inspect-btn" data-id="' + s.vey_filesubmissionid + '">Inspect</button>';
      rows += '</td>';
      rows += '</tr>';
    });

    tbody.innerHTML = rows;
  }

  // ============================================================
  // File Selection & Drag & Drop
  // ============================================================
  function handleFileSelected(file) {
    if (!file) return;

    // Validate size
    if (file.size <= 0 || file.size > CONFIG.maxSizeBytes) {
      showStatus('File size must be between 1 byte and 50 MB.', 'warning');
      clearSelectedFile();
      return;
    }

    // Validate extension
    var ext = '.' + file.name.split('.').pop().toLowerCase();
    if (CONFIG.allowedExtensions.indexOf(ext) === -1) {
      showStatus("File extension '" + ext + "' is not permitted.", 'warning');
      clearSelectedFile();
      return;
    }

    state.selectedFile = file;

    // Update summary chip
    var chip = document.getElementById('fm-file-chip');
    var chipName = document.getElementById('fm-chip-name');
    var chipMeta = document.getElementById('fm-chip-meta');
    var chipHash = document.getElementById('fm-chip-hash');

    if (chip && chipName && chipMeta && chipHash) {
      chipName.textContent = file.name;
      chipMeta.textContent = 'Size: ' + formatBytes(file.size) + ' \u2022 Type: ' + (file.type || 'application/octet-stream');
      chipHash.textContent = 'SHA-256: Computing checksum\u2026';
      chip.style.display = 'block';
    }

    // Suggest default submission reference
    var refInput = document.getElementById('fm-input-reference');
    if (refInput && !refInput.value) {
      var cleanBase = file.name.replace(/\.[^/.]+$/, '').replace(/[^a-zA-Z0-9_-]/g, '_');
      var dateStr = new Date().toISOString().split('T')[0];
      refInput.value = cleanBase + '-' + dateStr;
    }

    // Compute cryptographic SHA-256 checksum
    computeFileHash(file).then(function (hash) {
      state.selectedFileHash = hash;
      if (chipHash) {
        chipHash.textContent = 'SHA-256: ' + hash;
      }
      var submitBtn = document.getElementById('fm-submit-btn');
      if (submitBtn) submitBtn.disabled = false;
    }).catch(function (err) {
      console.error('Failed to compute hash:', err);
      if (chipHash) chipHash.textContent = 'SHA-256: Computation failed';
      var submitBtn = document.getElementById('fm-submit-btn');
      if (submitBtn) submitBtn.disabled = false;
    });
  }

  function clearSelectedFile() {
    state.selectedFile = null;
    state.selectedFileHash = '';
    var input = document.getElementById('fm-file-input');
    if (input) input.value = '';
    var chip = document.getElementById('fm-file-chip');
    if (chip) chip.style.display = 'none';
    var submitBtn = document.getElementById('fm-submit-btn');
    if (submitBtn) submitBtn.disabled = true;
  }

  // ============================================================
  // Direct-to-Storage Upload Pipeline
  // ============================================================
  function startUpload() {
    var file = state.selectedFile;
    if (!file) {
      showStatus('Please select a file to upload.', 'warning');
      return;
    }

    var refInput = document.getElementById('fm-input-reference');
    var submissionReference = (refInput && refInput.value.trim()) || file.name;

    // Check schema toggle
    var schemaVersion = '';
    var schemaToggle = document.getElementById('fm-schema-toggle');
    if (schemaToggle && schemaToggle.checked) {
      var select = document.getElementById('fm-schema-select');
      var selVal = select ? select.value : '';
      if (selVal === '__custom__') {
        var customInput = document.getElementById('fm-schema-custom');
        schemaVersion = (customInput && customInput.value.trim()) || '';
      } else {
        schemaVersion = selVal;
      }
    }

    var periodStart = (document.getElementById('fm-input-period-start') && document.getElementById('fm-input-period-start').value) || null;
    var periodEnd = (document.getElementById('fm-input-period-end') && document.getElementById('fm-input-period-end').value) || null;

    var submitBtn = document.getElementById('fm-submit-btn');
    var cancelBtn = document.getElementById('fm-cancel-btn');
    var progressContainer = document.getElementById('fm-progress-container');
    var progressBar = document.getElementById('fm-progress-bar');
    var progressLabel = document.getElementById('fm-progress-label');

    if (submitBtn) submitBtn.disabled = true;
    if (cancelBtn) cancelBtn.style.display = 'inline-block';
    if (progressContainer) progressContainer.style.display = 'block';
    if (progressBar) progressBar.style.width = '0%';
    if (progressLabel) progressLabel.textContent = 'Requesting upload authorization\u2026';

    // Step 1: Acquire MSAL Access Token
    getAccessToken().then(function (token) {
      
      // Step 2: Request SAS ticket from Azure Function
      return fetch(CONFIG.functionBaseUrl + '/api/upload-request', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer ' + token
        },
        body: JSON.stringify({
          filename: file.name,
          fileSizeBytes: file.size,
          mimeType: file.type || 'application/octet-stream',
          fileHash: state.selectedFileHash,
          organizationId: state.currentOrgId,
          contactId: state.currentContactId,
          submissionReference: submissionReference,
          schemaVersion: schemaVersion || null,
          reportingPeriodStart: periodStart,
          reportingPeriodEnd: periodEnd
        })
      }).then(function (ticketRes) {
        if (!ticketRes.ok) {
          return ticketRes.text().then(function (t) {
            throw new Error('Upload ticket request failed: ' + t);
          });
        }
        return ticketRes.json();
      }).then(function (ticket) {
        
        // Step 3: Direct binary PUT to Azure Blob Storage via XHR
        return new Promise(function (resolve, reject) {
          var xhr = new XMLHttpRequest();
          state.currentUploadXhr = xhr;

          xhr.upload.onprogress = function (e) {
            if (e.lengthComputable) {
              var percent = Math.round((e.loaded / e.total) * 100);
              if (progressBar) progressBar.style.width = percent + '%';
              if (progressLabel) progressLabel.textContent = percent + '% (' + formatBytes(e.loaded) + ' of ' + formatBytes(e.total) + ')';
            }
          };

          xhr.onload = function () {
            if (xhr.status >= 200 && xhr.status < 300) {
              resolve(ticket);
            } else {
              reject(new Error('Storage upload failed with HTTP ' + xhr.status));
            }
          };

          xhr.onerror = function () {
            reject(new Error('Network error during direct storage transfer.'));
          };

          xhr.onabort = function () {
            reject(new Error('Upload was cancelled.'));
          };

          xhr.open('PUT', ticket.uploadUrl, true);
          xhr.setRequestHeader('x-ms-blob-type', 'BlockBlob');
          if (file.type) xhr.setRequestHeader('Content-Type', file.type);
          xhr.send(file);
        });

      }).then(function (ticket) {
        
        // Step 4: Notify Azure Function upload is complete
        if (progressLabel) progressLabel.textContent = 'Confirming submission with Dataverse\u2026';
        
        return fetch(CONFIG.functionBaseUrl + '/api/upload-complete', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + token
          },
          body: JSON.stringify({ submissionId: ticket.submissionId })
        }).then(function (compRes) {
          if (!compRes.ok) throw new Error('Completion notification failed');
          return compRes.json();
        });

      });

    }).then(function () {
      showStatus('File "' + file.name + '" uploaded and registered successfully!', 'success');
      clearSelectedFile();
      if (progressContainer) progressContainer.style.display = 'none';
      if (cancelBtn) cancelBtn.style.display = 'none';

      // Reload submissions and switch to History tab
      loadSubmissions().then(function () {
        switchTab('history');
      });

    }).catch(function (err) {
      console.error('Upload failed:', err);
      showStatus('Upload failed: ' + err.message, 'error');
      if (progressContainer) progressContainer.style.display = 'none';
      if (cancelBtn) cancelBtn.style.display = 'none';
      if (submitBtn) submitBtn.disabled = false;
    });
  }

  function cancelUpload() {
    if (state.currentUploadXhr) {
      state.currentUploadXhr.abort();
      state.currentUploadXhr = null;
    }
  }

  // ============================================================
  // Download Action
  // ============================================================
  function downloadSubmission(submissionId) {
    showStatus('Requesting secure download authorization\u2026', 'info');

    getAccessToken().then(function (token) {
      return fetch(CONFIG.functionBaseUrl + '/api/download?submissionId=' + submissionId, {
        headers: { 'Authorization': 'Bearer ' + token }
      }).then(function (res) {
        if (!res.ok) throw new Error('Download request denied: HTTP ' + res.status);
        return res.json();
      });
    }).then(function (data) {
      showStatus('Download authorized. Starting download...', 'success');
      var a = document.createElement('a');
      a.href = data.downloadUrl;
      a.download = data.filename || 'download.bin';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    }).catch(function (err) {
      console.error('Download error:', err);
      showStatus('Failed to download file: ' + err.message, 'error');
    });
  }

  // ============================================================
  // Inspection Modal
  // ============================================================
  function inspectSubmission(submissionId) {
    var sub = state.submissions.find(function (s) {
      return s.vey_filesubmissionid === submissionId;
    });
    if (!sub) return;

    var modal = document.getElementById('fm-details-modal');
    if (!modal) return;

    var statusObj = STATUS_LABELS[sub.vey_submissionstatus] || { text: 'Uploaded', cls: 'fm-status-pill--uploaded' };

    document.getElementById('fm-modal-ref').textContent = sub.vey_submissionreference || sub.vey_filename || '\u2014';
    document.getElementById('fm-modal-status').innerHTML = '<span class="fm-status-pill ' + statusObj.cls + '">' + esc(statusObj.text) + '</span>';
    document.getElementById('fm-modal-filename').textContent = sub.vey_filename || '\u2014';
    document.getElementById('fm-modal-filesize').textContent = formatBytes(sub.vey_filesizebytes);
    document.getElementById('fm-modal-schema').textContent = sub.vey_schemaversion || 'None / Unvalidated';
    
    var period = '\u2014';
    if (sub.vey_reportingperiodstart || sub.vey_reportingperiodend) {
      period = (sub.vey_reportingperiodstart ? sub.vey_reportingperiodstart.split('T')[0] : '...') +
               ' to ' +
               (sub.vey_reportingperiodend ? sub.vey_reportingperiodend.split('T')[0] : '...');
    }
    document.getElementById('fm-modal-period').textContent = period;
    document.getElementById('fm-modal-createdon').textContent = formatDate(sub.createdon);
    document.getElementById('fm-modal-hash').textContent = sub.vey_filehash || '\u2014';

    // Hook download button
    var dlBtn = document.getElementById('fm-modal-download-btn');
    if (dlBtn) {
      dlBtn.onclick = function () {
        downloadSubmission(sub.vey_filesubmissionid);
      };
    }

    // Load child errors if applicable
    var errorsSection = document.getElementById('fm-modal-errors-section');
    var errorsTbody = document.getElementById('fm-modal-errors-tbody');
    var errorCount = document.getElementById('fm-modal-error-count');

    if (errorsSection && errorsTbody && errorCount) {
      errorsSection.style.display = 'none';
      errorsTbody.innerHTML = '';

      loadIngestionErrors(sub.vey_filesubmissionid).then(function (errors) {
        if (errors.length > 0) {
          errorCount.textContent = errors.length;
          var errRows = '';
          errors.forEach(function (e) {
            errRows += '<tr>';
            errRows += '<td>' + (e.vey_rownumber || '\u2014') + '</td>';
            errRows += '<td><code>' + esc(e.vey_errorcode || 'SCHEMA_ERR') + '</code></td>';
            errRows += '<td>' + esc(e.vey_errormessage || '\u2014') + '</td>';
            errRows += '<td><code>' + esc(e.vey_rawpayload || '\u2014') + '</code></td>';
            errRows += '</tr>';
          });
          errorsTbody.innerHTML = errRows;
          errorsSection.style.display = 'block';
        }
      });
    }

    modal.classList.add('is-active');
  }

  function closeModal() {
    var modal = document.getElementById('fm-details-modal');
    if (modal) modal.classList.remove('is-active');
  }

  // ============================================================
  // Tab Switching
  // ============================================================
  function switchTab(tabName) {
    var btnHistory = document.getElementById('tab-btn-history');
    var btnUpload = document.getElementById('tab-btn-upload');
    var panelHistory = document.getElementById('fm-panel-history');
    var panelUpload = document.getElementById('fm-panel-upload');

    if (tabName === 'upload') {
      if (btnUpload) { btnUpload.classList.add('is-active'); btnUpload.setAttribute('aria-selected', 'true'); }
      if (btnHistory) { btnHistory.classList.remove('is-active'); btnHistory.setAttribute('aria-selected', 'false'); }
      if (panelUpload) panelUpload.style.display = 'block';
      if (panelHistory) panelHistory.style.display = 'none';
    } else {
      if (btnHistory) { btnHistory.classList.add('is-active'); btnHistory.setAttribute('aria-selected', 'true'); }
      if (btnUpload) { btnUpload.classList.remove('is-active'); btnUpload.setAttribute('aria-selected', 'false'); }
      if (panelHistory) panelHistory.style.display = 'block';
      if (panelUpload) panelUpload.style.display = 'none';
    }
  }

  // ============================================================
  // Initialisation
  // ============================================================
  function init() {
    var dropzone = document.getElementById('fm-dropzone');
    var fileInput = document.getElementById('fm-file-input');
    var submitBtn = document.getElementById('fm-submit-btn');
    var cancelBtn = document.getElementById('fm-cancel-btn');
    var chipRemove = document.getElementById('fm-chip-remove');
    var refreshBtn = document.getElementById('fm-refresh-btn');
    var searchInput = document.getElementById('fm-search-input');
    var statusFilter = document.getElementById('fm-status-filter');
    var tabBtnHistory = document.getElementById('tab-btn-history');
    var tabBtnUpload = document.getElementById('tab-btn-upload');
    var schemaToggle = document.getElementById('fm-schema-toggle');
    var schemaSelect = document.getElementById('fm-schema-select');
    var modalCloseBtn = document.getElementById('fm-modal-close-btn');
    var tbody = document.getElementById('fm-submissions-tbody');

    if (tabBtnHistory) tabBtnHistory.addEventListener('click', function () { switchTab('history'); });
    if (tabBtnUpload) tabBtnUpload.addEventListener('click', function () { switchTab('upload'); });

    // File input change
    if (fileInput) {
      fileInput.addEventListener('change', function (e) {
        if (e.target.files && e.target.files[0]) {
          handleFileSelected(e.target.files[0]);
        }
      });
    }

    // Drag and drop
    if (dropzone) {
      ['dragenter', 'dragover'].forEach(function (eventName) {
        dropzone.addEventListener(eventName, function (e) {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.add('is-dragover');
        });
      });

      ['dragleave', 'drop'].forEach(function (eventName) {
        dropzone.addEventListener(eventName, function (e) {
          e.preventDefault();
          e.stopPropagation();
          dropzone.classList.remove('is-dragover');
        });
      });

      dropzone.addEventListener('drop', function (e) {
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]) {
          handleFileSelected(e.dataTransfer.files[0]);
        }
      });
    }

    if (chipRemove) chipRemove.addEventListener('click', clearSelectedFile);
    if (submitBtn) submitBtn.addEventListener('click', startUpload);
    if (cancelBtn) cancelBtn.addEventListener('click', cancelUpload);

    if (schemaToggle) {
      schemaToggle.addEventListener('change', function () {
        var opts = document.getElementById('fm-schema-options');
        if (opts) opts.style.display = schemaToggle.checked ? 'block' : 'none';
      });
    }

    if (schemaSelect) {
      schemaSelect.addEventListener('change', function () {
        var custom = document.getElementById('fm-schema-custom-wrapper');
        if (custom) custom.style.display = schemaSelect.value === '__custom__' ? 'block' : 'none';
      });
    }

    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        showStatus('Refreshing submissions list\u2026', 'info');
        loadSubmissions().then(function () {
          showStatus('Submissions list up to date.', 'success');
        });
      });
    }

    if (searchInput) searchInput.addEventListener('input', renderSubmissionsTable);
    if (statusFilter) statusFilter.addEventListener('change', renderSubmissionsTable);

    if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);

    var modal = document.getElementById('fm-details-modal');
    if (modal) {
      modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
      });
    }

    if (tbody) {
      tbody.addEventListener('click', function (e) {
        var row = e.target.closest && e.target.closest('tr');
        if (row) {
          var id = row.getAttribute('data-id');
          if (id) inspectSubmission(id);
        }
      });
    }

    // Initialize MSAL and load data
    initMsal();
    loadCurrentUserAndOrg().then(loadSubmissions);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
