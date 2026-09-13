// Veylo Contract Builder & Dynamic Attribute Manager

document.addEventListener('DOMContentLoaded', () => {
  // Live filtering on contracts index table
  const searchInput = document.getElementById('contract-search-input');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      const query = e.target.value.toLowerCase().trim();
      const rows = document.querySelectorAll('#contracts-table-body tr');
      rows.forEach(row => {
        const text = row.textContent.toLowerCase();
        row.style.display = text.includes(query) ? '' : 'none';
      });
    });
  }

  // Contract builder dynamic attribute table
  const addFieldBtn = document.getElementById('btn-add-field');
  const fieldsTableBody = document.getElementById('fields-table-body');

  if (addFieldBtn && fieldsTableBody) {
    let rowIndex = fieldsTableBody.querySelectorAll('tr').length;

    const toSnakeCase = (str) => {
      return str
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, '');
    };

    addFieldBtn.addEventListener('click', () => {
      const tr = document.createElement('tr');
      tr.className = 'field-row';
      tr.innerHTML = `
        <td>
          <input type="text" class="au-text-input input-src-field" name="attributes[${rowIndex}][src_field_name]" placeholder="e.g. Patient ID" required />
        </td>
        <td>
          <input type="text" class="au-text-input input-tgt-field" name="attributes[${rowIndex}][tgt_field_name]" placeholder="e.g. patient_id" required />
        </td>
        <td>
          <select class="au-select select-tgt-type" name="attributes[${rowIndex}][tgt_data_type]">
            <option value="STRING">STRING</option>
            <option value="DATE">DATE</option>
            <option value="INT64">INT64</option>
            <option value="FLOAT64">FLOAT64</option>
            <option value="BOOL">BOOL</option>
            <option value="TIMESTAMP">TIMESTAMP</option>
          </select>
        </td>
        <td class="text-center">
          <input type="checkbox" name="attributes[${rowIndex}][is_pk]" value="true" />
        </td>
        <td class="text-center">
          <input type="checkbox" name="attributes[${rowIndex}][is_nullable]" value="true" checked />
        </td>
        <td class="text-center">
          <button type="button" class="icon-btn btn-remove-row" title="Delete attribute">
            ✕
          </button>
        </td>
      `;

      // Auto-populate snake_case target field from source field
      const srcInput = tr.querySelector('.input-src-field');
      const tgtInput = tr.querySelector('.input-tgt-field');
      srcInput.addEventListener('input', (e) => {
        if (!tgtInput.dataset.manuallyEdited) {
          tgtInput.value = toSnakeCase(e.target.value);
        }
      });
      tgtInput.addEventListener('input', () => {
        tgtInput.dataset.manuallyEdited = "true";
      });

      // Remove row handler
      tr.querySelector('.btn-remove-row').addEventListener('click', () => {
        tr.remove();
        reindexRows();
      });

      fieldsTableBody.appendChild(tr);
      rowIndex++;
      srcInput.focus();
    });

    // Delegate row removal for any pre-rendered rows
    fieldsTableBody.addEventListener('click', (e) => {
      if (e.target.classList.contains('btn-remove-row') || e.target.closest('.btn-remove-row')) {
        const tr = e.target.closest('tr');
        if (tr) {
          tr.remove();
          reindexRows();
        }
      }
    });

    function reindexRows() {
      const rows = fieldsTableBody.querySelectorAll('tr');
      rows.forEach((r, idx) => {
        r.querySelectorAll('input, select').forEach(input => {
          const name = input.getAttribute('name');
          if (name) {
            input.setAttribute('name', name.replace(/attributes\[\d+\]/, `attributes[${idx}]`));
          }
        });
      });
    }
  }
});
