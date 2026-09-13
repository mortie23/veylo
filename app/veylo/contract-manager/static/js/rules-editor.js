// Rules Editor: Dynamic DQ Rule and Code Management Rows

document.addEventListener('DOMContentLoaded', () => {
  // Add Data Quality Rule
  const addDqBtn = document.getElementById('btn-add-dq');
  const dqTableBody = document.getElementById('dq-table-body');

  if (addDqBtn && dqTableBody) {
    let dqIndex = dqTableBody.querySelectorAll('tr.dq-row').length;

    addDqBtn.addEventListener('click', () => {
      const tr = document.createElement('tr');
      tr.className = 'dq-row';
      tr.innerHTML = `
        <td>
          <select class="au-select" name="dq_rules[${dqIndex}][rule_type]">
            <option value="REGEX">REGEX (Pattern matching)</option>
            <option value="RANGE">RANGE (Numeric min/max)</option>
            <option value="LENGTH">LENGTH (String length)</option>
            <option value="NOT_NULL">NOT_NULL (Non-empty check)</option>
          </select>
        </td>
        <td>
          <input type="text" class="au-text-input" name="dq_rules[${dqIndex}][rule_value]" placeholder='e.g. ^[0-9]{10}$ or {"min": 0, "max": 100}' />
        </td>
        <td>
          <select class="au-select" name="dq_rules[${dqIndex}][severity]">
            <option value="ERROR">ERROR (Reject file)</option>
            <option value="WARNING">WARNING (Log only)</option>
          </select>
        </td>
        <td>
          <input type="text" class="au-text-input" name="dq_rules[${dqIndex}][error_message]" placeholder="Custom error message template" />
        </td>
        <td class="text-center">
          <button type="button" class="icon-btn btn-remove-rule" title="Delete rule">✕</button>
        </td>
      `;

      tr.querySelector('.btn-remove-rule').addEventListener('click', () => tr.remove());
      dqTableBody.appendChild(tr);
      dqIndex++;
    });
  }

  // Add Code Management Row
  const addCodeBtn = document.getElementById('btn-add-code');
  const codeTableBody = document.getElementById('code-table-body');

  if (addCodeBtn && codeTableBody) {
    let codeIndex = codeTableBody.querySelectorAll('tr.code-row').length;

    addCodeBtn.addEventListener('click', () => {
      const tr = document.createElement('tr');
      tr.className = 'code-row';
      tr.innerHTML = `
        <td>
          <input type="text" class="au-text-input" name="code_maps[${codeIndex}][code_system_name]" placeholder="e.g. ISO_3166_COUNTRY" />
        </td>
        <td>
          <input type="text" class="au-text-input" name="code_maps[${codeIndex}][source_code]" placeholder="Incoming value (e.g. AUS)" required />
        </td>
        <td>
          <input type="text" class="au-text-input" name="code_maps[${codeIndex}][target_code]" placeholder="Standardized value (e.g. AU)" />
        </td>
        <td>
          <input type="text" class="au-text-input" name="code_maps[${codeIndex}][target_description]" placeholder="Description (e.g. Australia)" />
        </td>
        <td class="text-center">
          <button type="button" class="icon-btn btn-remove-code" title="Delete mapping">✕</button>
        </td>
      `;

      tr.querySelector('.btn-remove-code').addEventListener('click', () => tr.remove());
      codeTableBody.appendChild(tr);
      codeIndex++;
    });
  }
});
