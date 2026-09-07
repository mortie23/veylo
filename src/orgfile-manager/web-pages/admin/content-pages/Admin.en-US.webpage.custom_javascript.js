/**
 * Veylo Admin Panel — Dataverse Web API Client
 *
 * Calls the Power Pages Web API (/_api/) to manage Contact ↔ Account
 * relationships. Requires the following site settings to be enabled:
 *   - Webapi/contact/enabled = true
 *   - Webapi/contact/fields = fullname,emailaddress1,_parentcustomerid_value
 *   - Webapi/account/enabled = true
 *   - Webapi/account/fields = name,accountnumber,emailaddress1,_primarycontactid_value
 *
 * Also requires Table Permissions granting the Administrators web role:
 *   - Contact: Read, Write
 *   - Account:  Read, Write, Create
 */
(function () {
  'use strict';

  // ============================================================
  // Configuration
  // ============================================================
  var API_BASE = '/_api/';

  // ============================================================
  // State
  // ============================================================
  var state = {
    contacts: [],
    accounts: [],
    accountMap: {}, // accountid → name (for fast lookups in users table)
    contactMap: {}  // contactid → fullname (for primary contact display)
  };

  // ============================================================
  // Helpers
  // ============================================================

  /** Display a status message in the admin panel. */
  function showStatus(message, type) {
    var el = document.getElementById('admin-status');
    if (!el) return;
    el.textContent = message;
    
    // Map type to HDS page-alerts modifier
    var hdsType = 'info'; // default for au-page-alerts
    if (type === 'success' || type === 'warning' || type === 'error') {
      hdsType = type;
    }
    
    el.className = 'au-page-alerts';
    if (hdsType !== 'info') {
      el.className += ' au-page-alerts--' + hdsType;
    }
    
    el.style.display = 'block';
    if (type === 'success') {
      setTimeout(function () { el.style.display = 'none'; }, 4000);
    }
  }

  /** HTML-escape a string for safe insertion. */
  function esc(str) {
    if (!str) return '';
    var d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
  }

  /**
   * Generic fetch wrapper for the Dataverse Web API.
   * Automatically includes OData headers and the CSRF token for mutations.
   */
  function apiRequest(method, endpoint, body) {
    var headers = {
      'Accept': 'application/json',
      'OData-MaxVersion': '4.0',
      'OData-Version': '4.0'
    };

    var tokenPromise = Promise.resolve('');

    if (method !== 'GET') {
      headers['Content-Type'] = 'application/json';
      // Use the official Power Pages shell object to get the token
      if (window.shell && window.shell.getTokenDeferred) {
        tokenPromise = new Promise(function(resolve) {
          window.shell.getTokenDeferred().done(function(token) {
            resolve(token);
          });
        });
      } else {
        // Fallback for isolated environments where shell might not exist
        var el = document.querySelector('input[name="__RequestVerificationToken"]');
        tokenPromise = Promise.resolve(el ? el.value : '');
      }
    }

    return tokenPromise.then(function(token) {
      if (token) {
        headers['__RequestVerificationToken'] = token;
      }
      var opts = { method: method, headers: headers };
      if (body) {
        opts.body = JSON.stringify(body);
      }
      return fetch(API_BASE + endpoint, opts);
    }).then(function (response) {
      if (!response.ok) {
        return response.text().then(function (text) {
          throw new Error('API ' + response.status + ': ' + text);
        });
      }
      if (response.status === 204) return null; // No Content (successful PATCH)
      return response.json();
    });
  }

  // ============================================================
  // Data Loading
  // ============================================================

  function loadAccounts() {
    return apiRequest('GET', 'accounts?$select=name,accountnumber,emailaddress1,_primarycontactid_value&$orderby=name')
      .then(function (data) {
        state.accounts = data.value || [];
        state.accountMap = {};
        state.accounts.forEach(function (a) {
          state.accountMap[a.accountid] = a.name;
        });
        populateOrgDropdown();
      })
      .catch(function (err) {
        console.error('Failed to load accounts:', err);
        showStatus(
          'Failed to load organisations. Ensure Web API site settings are configured and table permissions are set for the Administrators role.',
          'error'
        );
      });
  }

  function loadContacts() {
    return apiRequest('GET', 'contacts?$select=fullname,emailaddress1,_parentcustomerid_value&$orderby=fullname')
      .then(function (data) {
        state.contacts = data.value || [];
        // Build a contactid → name lookup for primary contact display in orgs table
        state.contactMap = {};
        state.contacts.forEach(function (c) {
          state.contactMap[c.contactid] = c.fullname || c.emailaddress1 || c.contactid;
        });
        renderUsersTable();
        renderOrgsTable();
        populateUserDropdown();
        populatePrimaryContactDropdown();
        updateDashboard();
      })
      .catch(function (err) {
        console.error('Failed to load contacts:', err);
        showStatus(
          'Failed to load users. Ensure Web API site settings are configured and table permissions are set for the Administrators role.',
          'error'
        );
      });
  }

  function updateDashboard() {
    var elUsers = document.getElementById('metric-total-users');
    var elOrgs = document.getElementById('metric-total-orgs');
    var elAssigned = document.getElementById('metric-assigned-users');
    
    if (elUsers) elUsers.textContent = state.contacts.length;
    if (elOrgs) elOrgs.textContent = state.accounts.length;
    
    if (elAssigned) {
      var assignedCount = 0;
      state.contacts.forEach(function (c) {
        if (c._parentcustomerid_value) assignedCount++;
      });
      elAssigned.textContent = assignedCount;
    }
  }

  // ============================================================
  // Rendering
  // ============================================================

  function renderUsersTable() {
    var tbody = document.getElementById('admin-users-tbody');
    if (!tbody) return;

    if (state.contacts.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="admin-empty">No users found.</td></tr>';
      return;
    }

    var rows = '';
    state.contacts.forEach(function (c) {
      var orgName = c._parentcustomerid_value
        ? (state.accountMap[c._parentcustomerid_value] || 'Unknown')
        : '\u2014'; // em dash
      rows += '<tr>';
      rows += '<td>' + esc(c.fullname) + '</td>';
      rows += '<td>' + esc(c.emailaddress1) + '</td>';
      rows += '<td>' + esc(orgName) + '</td>';
      rows += '<td>';
      if (c._parentcustomerid_value) {
        rows += '<button type="button" class="au-btn au-btn--tertiary au-btn--sm" '
              + 'onclick="VeyloAdmin.removeFromOrg(\'' + c.contactid + '\')" '
              + 'title="Remove from organisation">Remove</button>';
      }
      rows += '</td>';
      rows += '</tr>';
    });
    tbody.innerHTML = rows;
  }

  function renderOrgsTable() {
    var tbody = document.getElementById('admin-orgs-tbody');
    if (!tbody) return;

    if (state.accounts.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5">No organisations found. Use the form above to register one.</td></tr>';
      return;
    }

    var rows = '';
    state.accounts.forEach(function (a) {
      var memberCount = 0;
      state.contacts.forEach(function (c) {
        if (c._parentcustomerid_value === a.accountid) memberCount++;
      });
      var primaryName = a._primarycontactid_value
        ? (state.contactMap[a._primarycontactid_value] || '\u2014')
        : '\u2014';
      rows += '<tr>';
      rows += '<td>' + esc(a.name) + '</td>';
      rows += '<td>' + esc(a.accountnumber || '\u2014') + '</td>';
      rows += '<td>' + esc(a.emailaddress1 || '\u2014') + '</td>';
      rows += '<td>' + esc(primaryName) + '</td>';
      rows += '<td>' + memberCount + '</td>';
      rows += '</tr>';
    });
    tbody.innerHTML = rows;
  }

  function populateUserDropdown() {
    var sel = document.getElementById('admin-user-select');
    if (!sel) return;
    var html = '<option value="">\u2014 Select a user \u2014</option>';
    state.contacts.forEach(function (c) {
      html += '<option value="' + c.contactid + '">'
            + esc(c.fullname || c.emailaddress1 || c.contactid)
            + '</option>';
    });
    sel.innerHTML = html;
  }

  function populateOrgDropdown() {
    var sel = document.getElementById('admin-org-select');
    if (!sel) return;
    var html = '<option value="">\u2014 Select an organisation \u2014</option>';
    state.accounts.forEach(function (a) {
      html += '<option value="' + a.accountid + '">' + esc(a.name) + '</option>';
    });
    sel.innerHTML = html;
  }

  function populatePrimaryContactDropdown() {
    var sel = document.getElementById('admin-org-primary-contact');
    if (!sel) return;
    var html = '<option value="">\u2014 No primary contact \u2014</option>';
    state.contacts.forEach(function (c) {
      html += '<option value="' + c.contactid + '">'
            + esc(c.fullname || c.emailaddress1 || c.contactid)
            + '</option>';
    });
    sel.innerHTML = html;
  }

  // ============================================================
  // Actions
  // ============================================================

  /** Assign the selected user to the selected organisation. */
  function assignToOrg() {
    var contactId = document.getElementById('admin-user-select').value;
    var accountId = document.getElementById('admin-org-select').value;
    if (!contactId || !accountId) {
      showStatus('Please select both a user and an organisation.', 'warning');
      return;
    }

    showStatus('Assigning user to organisation\u2026', 'info');

    apiRequest('PATCH', 'contacts(' + contactId + ')', {
      'parentcustomerid_account@odata.bind': '/accounts(' + accountId + ')'
    })
    .then(function () {
      showStatus('User assigned to organisation successfully.', 'success');
      return loadContacts();
    })
    .catch(function (err) {
      console.error('Assign failed:', err);
      showStatus('Failed to assign user. Check browser console for details.', 'error');
    });
  }

  /** Remove a user from their current organisation. */
  function removeFromOrg(contactId) {
    if (!confirm('Remove this user from their organisation?')) return;

    showStatus('Removing user from organisation\u2026', 'info');

    apiRequest('PATCH', 'contacts(' + contactId + ')', {
      'parentcustomerid_account@odata.bind': null
    })
    .then(function () {
      showStatus('User removed from organisation successfully.', 'success');
      return loadContacts();
    })
    .catch(function (err) {
      console.error('Remove failed:', err);
      showStatus('Failed to remove user. Check browser console for details.', 'error');
    });
  }

  /** Register a new organisation (Account) in Dataverse. */
  function createOrganisation() {
    var name = (document.getElementById('admin-org-name').value || '').trim();
    var abn  = (document.getElementById('admin-org-abn').value || '').trim();
    var email = (document.getElementById('admin-org-email').value || '').trim();
    var primaryContactId = document.getElementById('admin-org-primary-contact').value;

    if (!name) {
      showStatus('Organisation Name is required.', 'warning');
      document.getElementById('admin-org-name').focus();
      return;
    }

    var payload = { name: name };
    if (abn)   payload['accountnumber'] = abn;
    if (email) payload['emailaddress1'] = email;
    if (primaryContactId) {
      payload['primarycontactid@odata.bind'] = '/contacts(' + primaryContactId + ')';
    }

    showStatus('Registering organisation\u2026', 'info');

    // Disable button to prevent double-submit
    var btn = document.getElementById('admin-create-org-btn');
    if (btn) btn.disabled = true;

    apiRequest('POST', 'accounts', payload)
    .then(function () {
      showStatus('Organisation "' + name + '" registered successfully.', 'success');
      // Clear the form
      document.getElementById('admin-org-name').value = '';
      document.getElementById('admin-org-abn').value = '';
      document.getElementById('admin-org-email').value = '';
      document.getElementById('admin-org-primary-contact').value = '';
      // Reload accounts first (so new org appears in dropdown + table), then contacts
      return loadAccounts().then(loadContacts);
    })
    .catch(function (err) {
      console.error('Create organisation failed:', err);
      showStatus('Failed to register organisation. Check browser console for details.', 'error');
    })
    .then(function () {
      if (btn) btn.disabled = false;
    });
  }

  // ============================================================
  // Initialisation
  // ============================================================

  function init() {
    var panel = document.getElementById('admin-panel');
    if (!panel) return; // Not on admin page or user not authorised

    var assignBtn = document.getElementById('admin-assign-btn');
    if (assignBtn) assignBtn.addEventListener('click', assignToOrg);

    var createOrgBtn = document.getElementById('admin-create-org-btn');
    if (createOrgBtn) createOrgBtn.addEventListener('click', createOrganisation);

    var refreshBtn = document.getElementById('admin-refresh-btn');
    if (refreshBtn) {
      refreshBtn.addEventListener('click', function () {
        showStatus('Refreshing data\u2026', 'info');
        loadAccounts().then(loadContacts).then(function () {
          showStatus('Data refreshed.', 'success');
        });
      });
    }

    // Initial data load
    loadAccounts().then(loadContacts);
  }

  // Expose actions for inline onclick handlers in the rendered table
  window.VeyloAdmin = {
    removeFromOrg: removeFromOrg
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
