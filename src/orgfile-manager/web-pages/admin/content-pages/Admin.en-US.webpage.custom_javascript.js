/**
 * Veylo Admin Panel — Dataverse Web API Client
 *
 * Calls the Power Pages Web API (/_api/) to manage Contact ↔ Account
 * relationships. Requires the following site settings to be enabled:
 *   - Webapi/contact/enabled = true
 *   - Webapi/contact/fields = fullname,emailaddress1,parentcustomerid
 *   - Webapi/account/enabled = true
 *   - Webapi/account/fields = name
 *
 * Also requires Table Permissions granting the Administrators web role
 * read/write access to the Contact and Account tables.
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
    accountMap: {} // accountid → name
  };

  // ============================================================
  // Helpers
  // ============================================================

  /** Get the Power Pages anti-forgery token for write operations. */
  function getToken() {
    var el = document.querySelector('input[name="__RequestVerificationToken"]');
    return el ? el.value : '';
  }

  /** Display a status message in the admin panel. */
  function showStatus(message, type) {
    var el = document.getElementById('admin-status');
    if (!el) return;
    el.textContent = message;
    el.className = 'admin-status admin-status--' + (type || 'info');
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
    if (method !== 'GET') {
      headers['Content-Type'] = 'application/json';
      headers['__RequestVerificationToken'] = getToken();
    }
    var opts = { method: method, headers: headers };
    if (body) {
      opts.body = JSON.stringify(body);
    }
    return fetch(API_BASE + endpoint, opts).then(function (response) {
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
    return apiRequest('GET', 'accounts?$select=name&$orderby=name')
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
        renderUsersTable();
        renderOrgsTable();
        populateUserDropdown();
      })
      .catch(function (err) {
        console.error('Failed to load contacts:', err);
        showStatus(
          'Failed to load users. Ensure Web API site settings are configured and table permissions are set for the Administrators role.',
          'error'
        );
      });
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
      tbody.innerHTML = '<tr><td colspan="2" class="admin-empty">No organisations found.</td></tr>';
      return;
    }

    var rows = '';
    state.accounts.forEach(function (a) {
      var count = 0;
      state.contacts.forEach(function (c) {
        if (c._parentcustomerid_value === a.accountid) count++;
      });
      rows += '<tr>';
      rows += '<td>' + esc(a.name) + '</td>';
      rows += '<td>' + count + '</td>';
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

  // ============================================================
  // Initialisation
  // ============================================================

  function init() {
    var panel = document.getElementById('admin-panel');
    if (!panel) return; // Not on admin page or user not authorised

    var assignBtn = document.getElementById('admin-assign-btn');
    if (assignBtn) assignBtn.addEventListener('click', assignToOrg);

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
