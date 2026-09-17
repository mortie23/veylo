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
    msalInstance: null,
    currentModalErrors: [],
    currentModalFilename: ''
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
  // UI Helpers & Toast Notification System
  // ============================================================
  function showToast(title, message, type, options) {
    var container = document.getElementById('fm-toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'fm-toast-container';
      container.className = 'fm-toast-container';
      container.setAttribute('aria-live', 'polite');
      container.setAttribute('aria-atomic', 'true');
      document.body.appendChild(container);
    }

    var toastType = type || 'info';
    var toast = document.createElement('div');
    toast.className = 'fm-toast fm-toast--' + toastType;

    var iconMap = {
      error: 'glyphicon-remove-sign',
      warning: 'glyphicon-warning-sign',
      success: 'glyphicon-ok-sign',
      info: 'glyphicon-info-sign'
    };
    var iconClass = iconMap[toastType] || iconMap.info;

    var actionHtml = '';
    if (options && options.actionLabel) {
      actionHtml = '<button type="button" class="au-btn au-btn--sm fm-toast__action-btn">' + esc(options.actionLabel) + '</button>';
    }

    toast.innerHTML = [
      '<div class="fm-toast__icon"><span class="glyphicon ' + iconClass + '" aria-hidden="true"></span></div>',
      '<div class="fm-toast__content">',
        '<div class="fm-toast__title">' + esc(title) + '</div>',
        '<div class="fm-toast__message">' + esc(message) + '</div>',
        actionHtml ? '<div class="fm-toast__actions">' + actionHtml + '</div>' : '',
      '</div>',
      '<button type="button" class="fm-toast__close" aria-label="Dismiss notification">&times;</button>'
    ].join('');

    if (options && options.actionLabel && typeof options.onAction === 'function') {
      var actBtn = toast.querySelector('.fm-toast__action-btn');
      if (actBtn) {
        actBtn.addEventListener('click', function () {
          options.onAction();
          dismissToast(toast);
        });
      }
    }

    var closeBtn = toast.querySelector('.fm-toast__close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        dismissToast(toast);
      });
    }

    container.appendChild(toast);

    var autoDismissMs = (options && options.duration) || (toastType === 'error' ? 15000 : 8000);
    var timer = setTimeout(function () {
      dismissToast(toast);
    }, autoDismissMs);

    toast.addEventListener('mouseenter', function () { clearTimeout(timer); });
    toast.addEventListener('mouseleave', function () {
      timer = setTimeout(function () { dismissToast(toast); }, 4000);
    });

    return toast;
  }

  function dismissToast(toast) {
    if (!toast || toast._dismissing) return;
    toast._dismissing = true;
    toast.classList.add('is-dismissing');
    setTimeout(function () {
      if (toast.parentNode) toast.parentNode.removeChild(toast);
    }, 300);
  }

  function copyToClipboard(text, btnEl) {
    if (!navigator.clipboard) {
      var ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    } else {
      navigator.clipboard.writeText(text);
    }
    if (btnEl) {
      var origHtml = btnEl.innerHTML;
      btnEl.innerHTML = '<span class="glyphicon glyphicon-ok" style="color:#0b996c;" aria-hidden="true"></span>';
      setTimeout(function () {
        btnEl.innerHTML = origHtml;
      }, 1500);
    }
  }

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
      setTimeout(function () { el.style.display = 'none'; }, 6000);
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

      // Set active account if existing session accounts are found in cache
      var accounts = state.msalInstance.getAllAccounts();
      if (accounts && accounts.length > 0) {
        state.msalInstance.setActiveAccount(accounts[0]);
      }
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

    var activeAccount = state.msalInstance.getActiveAccount();
    if (!activeAccount) {
      var accounts = state.msalInstance.getAllAccounts();
      if (accounts && accounts.length > 0) {
        activeAccount = accounts[0];
        state.msalInstance.setActiveAccount(activeAccount);
      }
    }

    var tokenRequest = {
      scopes: [CONFIG.apiScope],
      account: activeAccount
    };

    // If no account exists yet, skip silent failure and prompt directly
    if (!activeAccount) {
      return state.msalInstance.acquireTokenPopup({ scopes: [CONFIG.apiScope] }).then(function (res) {
        if (res && res.account) {
          state.msalInstance.setActiveAccount(res.account);
        }
        return res.accessToken;
      }).catch(function (popupErr) {
        var msg = popupErr.errorMessage || popupErr.message || String(popupErr);
        throw new Error('Entra ID authentication required. ' + msg);
      });
    }

    return state.msalInstance.acquireTokenSilent(tokenRequest).then(function (res) {
      return res.accessToken;
    }).catch(function (silentErr) {
      console.info('Silent token acquisition failed, prompting with popup:', silentErr);
      return state.msalInstance.acquireTokenPopup(tokenRequest).then(function (res) {
        if (res && res.account) {
          state.msalInstance.setActiveAccount(res.account);
        }
        return res.accessToken;
      }).catch(function (popupErr) {
        var msg = popupErr.errorMessage || popupErr.message || String(popupErr);
        throw new Error(
          'Entra ID authentication required. ' +
          'Direct Azure upload requires an active Microsoft Entra ID session. (' + msg + ')'
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
    } else {
      // Prevent browser and intermediate proxy/CDN caching for GET queries
      headers['Cache-Control'] = 'no-cache, no-store, must-revalidate';
      headers['Pragma'] = 'no-cache';
    }

    return tokenPromise.then(function (token) {
      if (token) headers['__RequestVerificationToken'] = token;
      var opts = { method: method, headers: headers };
      if (method === 'GET') opts.cache = 'no-store';
      if (body) opts.body = JSON.stringify(body);

      var url = '/_api/' + endpoint;
      return fetch(url, opts);
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
        return Promise.resolve();
      }

      if (state.currentOrgId) {
        return apiRequest('GET', 'accounts(' + state.currentOrgId + ')?$select=name')
          .then(function (acc) {
            state.currentOrgName = acc.name || 'Your Organisation';
            var el = document.getElementById('fm-current-org-name');
            if (el) el.textContent = state.currentOrgName;
          })
          .catch(function () {
            var el = document.getElementById('fm-current-org-name');
            if (el) el.textContent = 'Your Organisation';
          });
      }
    }

    var contactQuery = state.currentContactId
      ? 'contacts(' + state.currentContactId + ')?$select=contactid,fullname,emailaddress1,_parentcustomerid_value'
      : 'contacts?$select=contactid,fullname,emailaddress1,_parentcustomerid_value&$top=1';

    return apiRequest('GET', contactQuery)
      .then(function (data) {
        var contact = (data.value && data.value[0]) || data || {};
        if (!state.currentContactId) state.currentContactId = contact.contactid || '';
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
          if (el) {
            el.textContent = 'No Organisation Assigned';
            el.style.color = '#718096';
          }
          var badge = document.getElementById('fm-org-badge');
          if (badge) {
            badge.innerHTML = '<span class="au-tag" style="background-color: #edf2f7; color: #4a5568;">Individual Submissions</span>';
          }
        }
      })
      .catch(function (err) {
        console.warn('Failed to load user org info:', err);
        var el = document.getElementById('fm-current-org-name');
        if (el && !state.currentOrgName) {
          el.textContent = 'No Organisation Assigned';
        }
      });
  }

  function formatContractName(name) {
    return (name || '').split('-').map(function (w) {
      return w.charAt(0).toUpperCase() + w.slice(1);
    }).join(' ');
  }

  function loadContracts() {
    var select = document.getElementById('fm-schema-select');
    if (!select) return;

    select.disabled = true;
    select.innerHTML = '<option value="">Loading active data standards\u2026</option>';

    fetch(CONFIG.functionBaseUrl + '/api/contracts')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (contracts) {
        select.disabled = false;
        if (!contracts || !contracts.length) {
          select.innerHTML = '<option value="">-- No Active Contracts Found --</option><option value="__custom__">Custom Schema Version...</option>';
          return;
        }

        select.innerHTML = '<option value="">-- Select Active Data Contract --</option>';
        contracts.forEach(function (c) {
          var opt = document.createElement('option');
          opt.value = c.contract_name + '::' + c.contract_version;
          opt.dataset.contractName = c.contract_name;
          opt.dataset.contractVersion = c.contract_version;

          var displayName = formatContractName(c.contract_name) + ' (' + c.contract_version + ')';
          opt.textContent = displayName;
          select.appendChild(opt);
        });

        var customOpt = document.createElement('option');
        customOpt.value = '__custom__';
        customOpt.textContent = 'Custom Schema Version...';
        select.appendChild(customOpt);
      })
      .catch(function (err) {
        console.warn('Failed to load dynamic contracts:', err);
        select.disabled = false;
        select.innerHTML = '<option value="">-- Failed to load contracts (Refresh page) --</option><option value="__custom__">Custom Schema Version...</option>';
      });
  }

  // Polling Engine for In-Flight Validations (SEC-11)
  var _pollTimer = null;
  var _pollIntervalMs = 4000;
  var _pollAttempts = 0;
  var _maxPollAttempts = 60; // 4 minutes max to prevent runaway polling

  function stopPolling() {
    if (_pollTimer) {
      clearInterval(_pollTimer);
      _pollTimer = null;
    }
    _pollAttempts = 0;
  }

  function checkAndStartPolling() {
    var hasPending = (state.submissions || []).some(function (s) {
      var status = Number(s.vey_submissionstatus);
      return status === 948740000 || status === 948740001; // Uploaded or Validating
    });

    if (!hasPending) {
      stopPolling();
      return;
    }

    if (_pollTimer) return;

    _pollAttempts = 0;
    _pollTimer = setInterval(function () {
      _pollAttempts++;
      if (_pollAttempts > _maxPollAttempts) {
        stopPolling();
        console.warn('Polling attempt limit reached for active validations.');
        return;
      }

      loadSubmissions().then(function () {
        var stillPending = (state.submissions || []).some(function (s) {
          var status = Number(s.vey_submissionstatus);
          return status === 948740000 || status === 948740001;
        });

        if (!stillPending) {
          stopPolling();
          var anyFailed = (state.submissions || []).some(function (s) {
            return Number(s.vey_submissionstatus) === 948740004;
          });
          if (!anyFailed) {
            showStatus('File validation processing completed successfully.', 'success');
          }
        }
      }).catch(function (err) {
        console.warn('Polling error:', err);
      });
    }, _pollIntervalMs);
  }

  function loadSubmissions() {
    var selectFields = [
      'vey_filesubmissionid',
      'vey_filename',
      'vey_submissionreference',
      'vey_filesizebytes',
      'vey_filehash',
      'vey_contractname',
      'vey_contractversion',
      'vey_schemaversion',
      'vey_submissionstatus',
      'vey_reportingperiodstart',
      'vey_reportingperiodend',
      'createdon',
      'vey_storageuri'
    ].join(',');

    return apiRequest('GET', 'vey_filesubmissions?$select=' + selectFields + '&$orderby=createdon desc')
      .then(function (data) {
        var serverItems = (data && data.value) || [];
        var serverIds = {};
        serverItems.forEach(function (s) { serverIds[s.vey_filesubmissionid] = true; });

        // Detect validation state transitions for notification
        state.knownStatuses = state.knownStatuses || {};
        serverItems.forEach(function (s) {
          var id = s.vey_filesubmissionid;
          var cur = Number(s.vey_submissionstatus);
          var prev = state.knownStatuses[id];

          if (prev !== undefined && prev !== cur) {
            var label = s.vey_submissionreference || s.vey_filename || 'File submission';
            if ((prev === 948740000 || prev === 948740001) && cur === 948740004) {
              // FAILED!
              showToast(
                'Validation Failed',
                'Submission "' + label + '" failed data contract verification.',
                'error',
                {
                  actionLabel: 'Inspect Errors',
                  onAction: function () {
                    inspectSubmission(id);
                  }
                }
              );
              showStatus('Submission "' + label + '" failed data contract validation. Click "Inspect Errors" to view issues.', 'error');
            } else if ((prev === 948740000 || prev === 948740001) && cur === 948740002) {
              // PROCESSED
              showToast(
                'Validation Passed',
                'Submission "' + label + '" was processed successfully.',
                'success'
              );
            } else if ((prev === 948740000 || prev === 948740001) && cur === 948740003) {
              // PARTIAL SUCCESS
              showToast(
                'Validation Completed with Warnings',
                'Submission "' + label + '" has partial validation warnings.',
                'warning',
                {
                  actionLabel: 'Inspect Errors',
                  onAction: function () {
                    inspectSubmission(id);
                  }
                }
              );
            }
          }
          state.knownStatuses[id] = cur;
        });

        // Preserve any recent locally submitted records that server read replica hasn't synced yet (up to 5 mins)
        var recentPending = (state.submissions || []).filter(function (s) {
          if (serverIds[s.vey_filesubmissionid]) return false;
          var createdTime = s.createdon ? new Date(s.createdon).getTime() : 0;
          var age = Date.now() - createdTime;
          return age >= 0 && age < 300000;
        });

        state.submissions = recentPending.concat(serverItems);
        renderSubmissionsTable();
        checkAndStartPolling();
      })
      .catch(function (err) {
        console.error('Failed to load submissions:', err);
        showStatus('Failed to load submissions: ' + (err.message || err), 'error');
        throw err;
      });
  }

  function loadIngestionErrors(submissionId) {
    var selectFields = 'vey_fileingestionerrorid,vey_rownumber,vey_errorcode,vey_errormessage,vey_errorreference,vey_rawpayload,createdon';

    // Primary: Query via FetchXML (Microsoft-recommended for parent-scoped table permissions in Power Pages)
    // Avoids URL-routing 403 on child relationships and bypasses OData $filter limitations
    var fetchXml = '<fetch>' +
      '<entity name="vey_fileingestionerror">' +
      '<attribute name="vey_fileingestionerrorid"/>' +
      '<attribute name="vey_rownumber"/>' +
      '<attribute name="vey_errorcode"/>' +
      '<attribute name="vey_errormessage"/>' +
      '<attribute name="vey_errorreference"/>' +
      '<attribute name="vey_rawpayload"/>' +
      '<attribute name="createdon"/>' +
      '<order attribute="vey_rownumber" descending="false"/>' +
      '<filter type="and">' +
      '<condition attribute="vey_filesubmission" operator="eq" value="' + submissionId + '"/>' +
      '</filter>' +
      '</entity>' +
      '</fetch>';

    return apiRequest('GET', 'vey_fileingestionerrors?fetchXml=' + encodeURIComponent(fetchXml))
      .then(function (data) {
        return (data && data.value) || [];
      })
      .catch(function (fetchErr) {
        console.warn('FetchXML query for ingestion errors failed, falling back to OData filter:', fetchErr);

        // Fallback 1: OData $filter with quoted GUID
        return apiRequest('GET', 'vey_fileingestionerrors?$filter=_vey_filesubmission_value eq \'' + submissionId + '\'&$select=' + selectFields + '&$orderby=vey_rownumber asc')
          .then(function (data) {
            return (data && data.value) || [];
          })
          .catch(function () {
            // Fallback 2: OData $filter with unquoted GUID
            return apiRequest('GET', 'vey_fileingestionerrors?$filter=_vey_filesubmission_value eq ' + submissionId + '&$select=' + selectFields)
              .then(function (data) {
                return (data && data.value) || [];
              })
              .catch(function () {
                // Fallback 3: OData $filter with guid prefix
                return apiRequest('GET', 'vey_fileingestionerrors?$filter=_vey_filesubmission_value eq guid\'' + submissionId + '\'&$select=' + selectFields)
                  .then(function (data) {
                    return (data && data.value) || [];
                  })
                  .catch(function (err) {
                    console.error('All retrieval methods failed for ingestion errors (submission ' + submissionId + '):', err);
                    throw err;
                  });
              });
          });
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
      var statusNum = Number(s.vey_submissionstatus);
      var statusObj = STATUS_LABELS[statusNum] || { text: 'Uploaded', cls: 'fm-status-pill--uploaded' };
      var period = '\u2014';
      if (s.vey_reportingperiodstart || s.vey_reportingperiodend) {
        var startStr = s.vey_reportingperiodstart ? s.vey_reportingperiodstart.split('T')[0] : '...';
        var endStr = s.vey_reportingperiodend ? s.vey_reportingperiodend.split('T')[0] : '...';
        period = startStr + ' to ' + endStr;
      }

      var isFailed = statusNum === 948740004;
      var isValidating = statusNum === 948740001;

      var pillHtml = '<span class="fm-status-pill ' + statusObj.cls + '">';
      if (isFailed) {
        pillHtml += '<span class="glyphicon glyphicon-remove-sign" aria-hidden="true" style="margin-right: 4px;"></span>';
      } else if (isValidating) {
        pillHtml += '<span class="glyphicon glyphicon-refresh fm-spin" aria-hidden="true" style="margin-right: 4px;"></span>';
      }
      pillHtml += esc(statusObj.text) + '</span>';

      var actionBtnHtml = isFailed
        ? '<button type="button" class="au-btn au-btn--sm js-inspect-btn fm-btn--inspect-failed" data-id="' + s.vey_filesubmissionid + '"><span class="glyphicon glyphicon-exclamation-sign" aria-hidden="true"></span> Inspect Errors</button>'
        : '<button type="button" class="au-btn au-btn--secondary au-btn--sm js-inspect-btn" data-id="' + s.vey_filesubmissionid + '">Inspect</button>';

      rows += '<tr style="cursor: pointer;" data-id="' + s.vey_filesubmissionid + '">';
      rows += '<td><strong>' + esc(s.vey_submissionreference || s.vey_filename || '—') + '</strong></td>';
      rows += '<td>' + esc(s.vey_filename) + '</td>';
      rows += '<td>' + (s.vey_schemaversion ? '<span class="au-tag">' + esc(s.vey_schemaversion) + '</span>' : '\u2014') + '</td>';
      rows += '<td>' + formatBytes(s.vey_filesizebytes) + '</td>';
      rows += '<td>' + esc(period) + '</td>';
      rows += '<td>' + formatDate(s.createdon) + '</td>';
      rows += '<td>' + pillHtml + '</td>';
      rows += '<td>' + actionBtnHtml + '</td>';
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
    var contractName = null;
    var contractVersion = null;
    var schemaToggle = document.getElementById('fm-schema-toggle');
    if (schemaToggle && schemaToggle.checked) {
      var select = document.getElementById('fm-schema-select');
      var selVal = select ? select.value : '';
      if (selVal === '__custom__') {
        var customInput = document.getElementById('fm-schema-custom');
        schemaVersion = (customInput && customInput.value.trim()) || '';
      } else if (selVal) {
        var selectedOpt = (select.selectedOptions && select.selectedOptions[0]) || (select.options && select.options[select.selectedIndex]);
        if (selectedOpt && selectedOpt.dataset) {
          contractName = selectedOpt.dataset.contractName || null;
          contractVersion = selectedOpt.dataset.contractVersion || null;
        }
        if ((!contractName || !contractVersion) && selVal.indexOf('::') !== -1) {
          var parts = selVal.split('::');
          contractName = parts[0];
          contractVersion = parts[1];
        }
        schemaVersion = (contractName && contractVersion) ? (formatContractName(contractName) + ' (' + contractVersion + ')') : selVal;
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
          contractName: contractName,
          contractVersion: contractVersion,
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
          return compRes.json().then(function (compData) {
            return { ticket: ticket, complete: compData };
          });
        });

      });

    }).then(function (result) {
      var ticket = result.ticket;
      var compData = result.complete;
      var isPendingValidation = compData && compData.status === 'Validating';
      var statusNum = isPendingValidation ? 948740001 : 948740000;
      var statusText = isPendingValidation ? 'Validating' : 'Uploaded';

      showStatus('File "' + file.name + '" uploaded successfully (Status: ' + statusText + ')!', 'success');
      clearSelectedFile();
      if (progressContainer) progressContainer.style.display = 'none';
      if (cancelBtn) cancelBtn.style.display = 'none';

      // Optimistically add to state.submissions so user sees it immediately without cache lag
      if (ticket && ticket.submissionId) {
        var localRecord = {
          vey_filesubmissionid: ticket.submissionId,
          vey_filename: file.name,
          vey_submissionreference: submissionReference || file.name,
          vey_filesizebytes: file.size,
          vey_filehash: state.selectedFileHash,
          vey_contractname: contractName,
          vey_contractversion: contractVersion,
          vey_schemaversion: schemaVersion || null,
          vey_submissionstatus: statusNum,
          vey_reportingperiodstart: periodStart,
          vey_reportingperiodend: periodEnd,
          createdon: new Date().toISOString()
        };
        var exists = (state.submissions || []).some(function (s) { return s.vey_filesubmissionid === ticket.submissionId; });
        if (!exists) {
          state.submissions = [localRecord].concat(state.submissions || []);
          renderSubmissionsTable();
        }
        state.knownStatuses = state.knownStatuses || {};
        state.knownStatuses[ticket.submissionId] = statusNum;
      }

      switchTab('history');

      // Reload submissions from server to sync with Dataverse and start polling
      loadSubmissions();

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
      var url = CONFIG.functionBaseUrl + '/api/download?submissionId=' + encodeURIComponent(submissionId);
      if (state.currentContactId) {
        url += '&contactId=' + encodeURIComponent(state.currentContactId);
      }
      return fetch(url, {
        headers: { 'Authorization': 'Bearer ' + token }
      }).then(function (res) {
        if (!res.ok) throw new Error('Download request denied: HTTP ' + res.status);
        return res.json();
      });
    }).then(function (data) {
      showStatus('Download authorized. Fetching file\u2026', 'success');
      var filename = data.filename || 'download.bin';

      // Fetch the blob via the SAS URL, then create a same-origin Blob URL.
      // This ensures the a.download filename attribute is respected by the browser,
      // which ignores it for cross-origin URLs (the SAS URL is on blob.core.windows.net).
      return fetch(data.downloadUrl).then(function (blobRes) {
        if (!blobRes.ok) throw new Error('Failed to fetch file from storage: HTTP ' + blobRes.status);
        return blobRes.blob();
      }).then(function (blob) {
        var blobUrl = URL.createObjectURL(blob);
        var a = document.createElement('a');
        a.href = blobUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        // Revoke the object URL after a short delay to free memory
        setTimeout(function () { URL.revokeObjectURL(blobUrl); }, 5000);
      });
    }).catch(function (err) {
      console.error('Download error:', err);
      showStatus('Failed to download file: ' + err.message, 'error');
    });
  }

  // ============================================================
  // Inspection Modal & Errors Viewer
  // ============================================================
  function renderModalErrors(errors, searchTerm) {
    var tbody = document.getElementById('fm-modal-errors-tbody');
    var filterCountEl = document.getElementById('fm-errors-filter-count');
    if (!tbody) return;

    var term = (searchTerm || '').toLowerCase().trim();
    var filtered = (errors || []).filter(function (e) {
      if (!term) return true;
      var rowStr = e.vey_rownumber !== null && e.vey_rownumber !== undefined ? String(e.vey_rownumber) : '';
      var codeStr = (e.vey_errorcode || '').toLowerCase();
      var refStr = (e.vey_errorreference || '').toLowerCase();
      var msgStr = (e.vey_errormessage || '').toLowerCase();
      var rawStr = (e.vey_rawpayload || '').toLowerCase();
      return rowStr.indexOf(term) !== -1 ||
             codeStr.indexOf(term) !== -1 ||
             refStr.indexOf(term) !== -1 ||
             msgStr.indexOf(term) !== -1 ||
             rawStr.indexOf(term) !== -1;
    });

    if (filterCountEl) {
      if (term) {
        filterCountEl.textContent = 'Showing ' + filtered.length + ' of ' + errors.length + ' errors';
      } else {
        filterCountEl.textContent = errors.length + ' error' + (errors.length === 1 ? '' : 's') + ' recorded';
      }
    }

    if (filtered.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center" style="padding: 20px; color: #64748b;">No validation errors match your search.</td></tr>';
      return;
    }

    var html = '';
    filtered.forEach(function (e) {
      var rowDisplay = (e.vey_rownumber !== null && e.vey_rownumber !== undefined && e.vey_rownumber !== '')
        ? '<span class="fm-row-badge">Row ' + esc(String(e.vey_rownumber)) + '</span>'
        : '<span class="fm-row-badge fm-row-badge--file">File-level</span>';

      var codeDisplay = '<span class="fm-code-badge">' + esc(e.vey_errorcode || 'SCHEMA_ERR') + '</span>';
      var refDisplay = e.vey_errorreference ? '<span class="fm-ref-badge">' + esc(e.vey_errorreference) + '</span>' : '\u2014';
      var msgDisplay = '<div class="fm-error-msg">' + esc(e.vey_errormessage || 'Validation constraint violated') + '</div>';

      var rawDisplay = '\u2014';
      if (e.vey_rawpayload) {
        rawDisplay = '<div class="fm-payload-cell">' +
          '<code class="fm-payload-code" title="' + esc(e.vey_rawpayload) + '">' + esc(e.vey_rawpayload) + '</code>' +
          '<button type="button" class="fm-copy-payload-btn js-copy-payload" title="Copy raw payload" data-raw="' + esc(e.vey_rawpayload) + '">' +
          '<span class="glyphicon glyphicon-copy" aria-hidden="true"></span>' +
          '</button>' +
          '</div>';
      }

      var timeDisplay = '<span class="fm-time-badge">' + formatDate(e.createdon) + '</span>';

      html += '<tr>' +
        '<td>' + rowDisplay + '</td>' +
        '<td>' + codeDisplay + '</td>' +
        '<td>' + refDisplay + '</td>' +
        '<td>' + msgDisplay + '</td>' +
        '<td>' + rawDisplay + '</td>' +
        '<td>' + timeDisplay + '</td>' +
        '</tr>';
    });

    tbody.innerHTML = html;
  }

  function inspectSubmission(submissionId) {
    var sub = state.submissions.find(function (s) {
      return s.vey_filesubmissionid === submissionId;
    });
    if (!sub) return;

    var modal = document.getElementById('fm-details-modal');
    if (!modal) return;

    var statusObj = STATUS_LABELS[sub.vey_submissionstatus] || { text: 'Uploaded', cls: 'fm-status-pill--uploaded' };
    var isFailed = Number(sub.vey_submissionstatus) === 948740004;
    var isPartial = Number(sub.vey_submissionstatus) === 948740003;
    var isSuccess = Number(sub.vey_submissionstatus) === 948740002;

    // Update modal title
    var modalTitle = document.getElementById('fm-modal-title');
    if (modalTitle) {
      if (isFailed) {
        modalTitle.innerHTML = '<span class="glyphicon glyphicon-exclamation-sign" style="color:#d60000; margin-right:8px;" aria-hidden="true"></span> Submission Details &mdash; Validation Failed';
      } else {
        modalTitle.textContent = 'Submission Details';
      }
    }

    // High-impact Failure Alert Card
    var failureAlert = document.getElementById('fm-modal-failure-alert');
    var failureTitle = document.getElementById('fm-modal-failure-title');
    var failureDesc = document.getElementById('fm-modal-failure-desc');
    if (failureAlert) {
      if (isFailed) {
        if (failureTitle) failureTitle.textContent = 'Data Contract Validation Failed';
        if (failureDesc) {
          var contractTxt = sub.vey_contractname ? formatContractName(sub.vey_contractname) + (sub.vey_contractversion ? ' (' + sub.vey_contractversion + ')' : '') : 'the configured data contract';
          failureDesc.textContent = 'File "' + (sub.vey_filename || 'submission') + '" failed verification against ' + contractTxt + '. Review row-level errors and validation messages below.';
        }
        failureAlert.style.display = 'flex';
      } else {
        failureAlert.style.display = 'none';
      }
    }

    // Validation & Schema Summary
    var summaryContainer = document.getElementById('fm-modal-summary-container');
    var summaryEl = document.getElementById('fm-modal-summary');
    if (summaryContainer && summaryEl) {
      var contractInfo = sub.vey_contractname
        ? 'Data Contract: ' + formatContractName(sub.vey_contractname) + (sub.vey_contractversion ? ' (' + sub.vey_contractversion + ')' : '')
        : (sub.vey_schemaversion ? 'Schema: ' + sub.vey_schemaversion : 'No Data Contract / Schema specified');

      var statusNote = '';
      if (isFailed) {
        summaryContainer.style.borderLeftColor = '#dc2626';
        summaryContainer.style.backgroundColor = '#fffafb';
        statusNote = ' &bull; <strong style="color:#dc2626;">Status: Failed</strong>';
      } else if (isPartial) {
        summaryContainer.style.borderLeftColor = '#d97706';
        summaryContainer.style.backgroundColor = '#fffdf5';
        statusNote = ' &bull; <strong style="color:#d97706;">Status: Partial Success (Warnings)</strong>';
      } else if (isSuccess) {
        summaryContainer.style.borderLeftColor = '#0b996c';
        summaryContainer.style.backgroundColor = '#f6fdf9';
        statusNote = ' &bull; <strong style="color:#0b996c;">Status: Processed (Passed)</strong>';
      } else {
        summaryContainer.style.borderLeftColor = '#0284c7';
        summaryContainer.style.backgroundColor = '#f8fafc';
        statusNote = ' &bull; <strong>Status: ' + statusObj.text + '</strong>';
      }

      summaryEl.innerHTML = esc(contractInfo) + statusNote;
      summaryContainer.style.display = 'block';
    }

    document.getElementById('fm-modal-ref').textContent = sub.vey_submissionreference || sub.vey_filename || '\u2014';
    document.getElementById('fm-modal-status').innerHTML = '<span class="fm-status-pill ' + statusObj.cls + '">' + esc(statusObj.text) + '</span>';
    document.getElementById('fm-modal-filename').textContent = sub.vey_filename || '\u2014';
    document.getElementById('fm-modal-filesize').textContent = formatBytes(sub.vey_filesizebytes);

    var modalSchema = sub.vey_contractname
      ? (formatContractName(sub.vey_contractname) + (sub.vey_contractversion ? ' (' + sub.vey_contractversion + ')' : ''))
      : (sub.vey_schemaversion || 'None / Unvalidated');
    document.getElementById('fm-modal-schema').textContent = modalSchema;

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

    // Load child errors
    var errorsSection = document.getElementById('fm-modal-errors-section');
    var errorsLoading = document.getElementById('fm-modal-errors-loading');
    var errorsFetchError = document.getElementById('fm-modal-errors-fetch-error');
    var errorsFetchErrorText = document.getElementById('fm-modal-fetch-error-text');
    var errorsEmpty = document.getElementById('fm-modal-errors-empty');
    var errorsTableWrap = document.getElementById('fm-modal-errors-table-wrap');
    var errorsToolbar = document.getElementById('fm-errors-toolbar');
    var errorBadge = document.getElementById('fm-modal-error-badge');
    var csvBtn = document.getElementById('fm-download-errors-csv');
    var searchInput = document.getElementById('fm-errors-search-input');
    var retryBtn = document.getElementById('fm-errors-retry-btn');

    state.currentModalErrors = [];
    state.currentModalFilename = sub.vey_filename || 'submission';

    if (csvBtn) {
      csvBtn.onclick = function () {
        exportErrorsToCsv(state.currentModalErrors, state.currentModalFilename);
      };
    }

    if (searchInput) {
      searchInput.value = '';
      searchInput.oninput = function () {
        renderModalErrors(state.currentModalErrors, searchInput.value);
      };
    }

    function loadErrorsForModal(submission) {
      if (!errorsSection) return;

      errorsSection.style.display = 'block';
      if (errorsLoading) errorsLoading.style.display = 'block';
      if (errorsFetchError) errorsFetchError.style.display = 'none';
      if (errorsEmpty) errorsEmpty.style.display = 'none';
      if (errorsTableWrap) errorsTableWrap.style.display = 'none';
      if (errorsToolbar) errorsToolbar.style.display = 'none';

      loadIngestionErrors(submission.vey_filesubmissionid)
        .then(function (errors) {
          if (errorsLoading) errorsLoading.style.display = 'none';
          state.currentModalErrors = errors || [];

          if (errorBadge) errorBadge.textContent = state.currentModalErrors.length;

          if (state.currentModalErrors.length > 0) {
            renderModalErrors(state.currentModalErrors, '');
            if (errorsToolbar) errorsToolbar.style.display = 'flex';
            if (errorsTableWrap) errorsTableWrap.style.display = 'block';
            if (errorsEmpty) errorsEmpty.style.display = 'none';
          } else {
            // 0 errors returned
            if (isFailed || isPartial) {
              if (errorsEmpty) errorsEmpty.style.display = 'block';
            } else {
              // Processed or unvalidated with 0 errors
              errorsSection.style.display = 'none';
            }
          }
        })
        .catch(function (err) {
          if (errorsLoading) errorsLoading.style.display = 'none';
          if (errorsFetchError) {
            if (errorsFetchErrorText) {
              errorsFetchErrorText.textContent = err.message || 'An unexpected Dataverse Web API error occurred.';
            }
            errorsFetchError.style.display = 'flex';
          }
        });
    }

    if (retryBtn) {
      retryBtn.onclick = function () {
        loadErrorsForModal(sub);
      };
    }

    // Only attempt loading ingestion errors if submission is Failed, Partial, or has contract/schema
    if (isFailed || isPartial || sub.vey_contractname || sub.vey_schemaversion) {
      loadErrorsForModal(sub);
    } else if (errorsSection) {
      errorsSection.style.display = 'none';
    }

    modal.classList.add('is-active');
  }

  function sanitizeCsvCell(val) {
    if (val === null || val === undefined) return '""';
    var str = String(val);
    // SEC-09: Prevent CSV Formula Injection
    if (/^[=+\-@\t\r]/.test(str)) {
      str = "'" + str;
    }
    return '"' + str.replace(/"/g, '""') + '"';
  }

  function exportErrorsToCsv(errors, filename) {
    if (!errors || !errors.length) {
      showStatus('No validation errors available to export.', 'info');
      return;
    }

    var headers = ['Row Number', 'Error Code', 'Column / Reference', 'Error Message', 'Raw Value', 'Logged At'];
    var rows = errors.map(function (e) {
      return [
        sanitizeCsvCell(e.vey_rownumber !== null && e.vey_rownumber !== undefined ? e.vey_rownumber : 'File-level'),
        sanitizeCsvCell(e.vey_errorcode || ''),
        sanitizeCsvCell(e.vey_errorreference || ''),
        sanitizeCsvCell(e.vey_errormessage || ''),
        sanitizeCsvCell(e.vey_rawpayload || ''),
        sanitizeCsvCell(formatDate(e.createdon) || '')
      ].join(',');
    });

    var csvContent = [headers.map(sanitizeCsvCell).join(',')].concat(rows).join('\r\n');
    var blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    var cleanBase = (filename || 'submission').replace(/\.[^/.]+$/, '').replace(/[^a-zA-Z0-9_-]/g, '_');
    var downloadFileName = 'validation-errors-' + cleanBase + '.csv';

    if (window.navigator && window.navigator.msSaveOrOpenBlob) {
      window.navigator.msSaveOrOpenBlob(blob, downloadFileName);
    } else {
      var url = URL.createObjectURL(blob);
      var link = document.createElement('a');
      link.setAttribute('href', url);
      link.setAttribute('download', downloadFileName);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      setTimeout(function () { URL.revokeObjectURL(url); }, 5000);
    }
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
        loadSubmissions()
          .then(function () {
            showStatus('Submissions list up to date (' + state.submissions.length + ' lodgments found).', 'success');
          })
          .catch(function () {
            // Error already displayed by loadSubmissions
          });
      });
    }

    if (searchInput) searchInput.addEventListener('input', renderSubmissionsTable);
    if (statusFilter) statusFilter.addEventListener('change', renderSubmissionsTable);

    if (modalCloseBtn) modalCloseBtn.addEventListener('click', closeModal);
    var modalCloseX = document.querySelector('.js-modal-close-x');
    if (modalCloseX) modalCloseX.addEventListener('click', closeModal);

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' || e.keyCode === 27) {
        closeModal();
      }
    });

    var errorsTbody = document.getElementById('fm-modal-errors-tbody');
    if (errorsTbody) {
      errorsTbody.addEventListener('click', function (e) {
        var copyBtn = e.target.closest && e.target.closest('.js-copy-payload');
        if (copyBtn) {
          var raw = copyBtn.getAttribute('data-raw');
          if (raw) copyToClipboard(raw, copyBtn);
        }
      });
    }

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

    // Initialize MSAL, dynamic contracts, and load submissions
    initMsal();
    loadContracts();
    loadCurrentUserAndOrg().then(loadSubmissions);

    // Pause/resume polling based on browser tab visibility
    document.addEventListener('visibilitychange', function () {
      if (document.hidden) {
        stopPolling();
      } else {
        checkAndStartPolling();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
