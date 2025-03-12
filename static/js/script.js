document.addEventListener('DOMContentLoaded', function() {
    // Get the table name select element
    const tableSelect = document.getElementById('existing_table');
    
    // Add event listener for table select change if it exists
    if (tableSelect) {
        tableSelect.addEventListener('change', function() {
            const selectedTable = this.value;
            if (selectedTable) {
                // Show loading indicator
                showLoadingIndicator('Loading table structure...');
                
                // Get table columns using AJAX
                fetch('/get_table_columns', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({ table_name: selectedTable }),
                })
                .then(response => response.json())
                .then(data => {
                    hideLoadingIndicator();
                    if (data.error) {
                        showAlert('error', data.error);
                    }
                })
                .catch(error => {
                    hideLoadingIndicator();
                    showAlert('error', 'Error fetching table structure: ' + error.message);
                });
            }
        });
    }
    
    // Handle file input change to validate file type and size
    const fileInput = document.getElementById('file');
    if (fileInput) {
        fileInput.addEventListener('change', function() {
            if (fileInput.files.length > 0) {
                const file = fileInput.files[0];
                
                // Check file type
                const validTypes = ['.xls', '.xlsx', 'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'];
                let validFile = false;
                
                for (const type of validTypes) {
                    if (file.type === type || file.name.toLowerCase().endsWith(type)) {
                        validFile = true;
                        break;
                    }
                }
                
                if (!validFile) {
                    showAlert('error', 'Invalid file type. Please upload an Excel file (.xls or .xlsx).');
                    fileInput.value = '';
                    return;
                }
                
                // Check file size (max 16MB)
                const maxSize = 16 * 1024 * 1024; // 16MB in bytes
                if (file.size > maxSize) {
                    showAlert('error', 'File size exceeds the maximum limit of 16MB.');
                    fileInput.value = '';
                    return;
                }
            }
        });
    }
    
    // Show auto-generated DB column name when typing in new table creation
    const newTableInputs = document.querySelectorAll('input[name^="mapping_"]');
    if (newTableInputs.length > 0) {
        newTableInputs.forEach(input => {
            const defaultValue = input.value;
            if (!defaultValue) {
                const excelCol = input.name.replace('mapping_', '');
                input.value = excelCol.replace(/ /g, '_').toLowerCase();
            }
        });
    }
    
    // Highlight primary key radio when clicked
    const primaryKeyRadios = document.querySelectorAll('.primary-key-radio');
    if (primaryKeyRadios.length > 0) {
        primaryKeyRadios.forEach(radio => {
            radio.addEventListener('change', function() {
                // Remove highlighting from all rows
                document.querySelectorAll('tr').forEach(row => {
                    row.classList.remove('table-primary');
                });
                
                // Highlight the selected row
                if (this.checked) {
                    this.closest('tr').classList.add('table-primary');
                }
            });
        });
    }
});

// Function to show a loading indicator
function showLoadingIndicator(message) {
    // Create a loading div if it doesn't exist
    let loadingDiv = document.getElementById('loading-indicator');
    if (!loadingDiv) {
        loadingDiv = document.createElement('div');
        loadingDiv.id = 'loading-indicator';
        loadingDiv.className = 'loading-overlay';
        loadingDiv.innerHTML = `
            <div class="loading-content">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <div class="loading-message mt-3">${message || 'Loading...'}</div>
            </div>
        `;
        document.body.appendChild(loadingDiv);
    } else {
        loadingDiv.querySelector('.loading-message').textContent = message || 'Loading...';
        loadingDiv.style.display = 'flex';
    }
}

// Function to hide the loading indicator
function hideLoadingIndicator() {
    const loadingDiv = document.getElementById('loading-indicator');
    if (loadingDiv) {
        loadingDiv.style.display = 'none';
    }
}

// Function to show alerts
function showAlert(type, message) {
    // Map type to Bootstrap alert class
    const alertClass = type === 'error' ? 'danger' : type;
    
    // Create alert element
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${alertClass} alert-dismissible fade show`;
    alertDiv.role = 'alert';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
    `;
    
    // Find a suitable container for the alert
    let container = document.querySelector('.card-body');
    if (!container) {
        container = document.querySelector('.container');
    }
    
    // Insert alert at the beginning of the container
    if (container) {
        const firstChild = container.firstChild;
        container.insertBefore(alertDiv, firstChild);
        
        // Auto-dismiss after 5 seconds
        setTimeout(() => {
            alertDiv.classList.remove('show');
            setTimeout(() => {
                alertDiv.remove();
            }, 150);
        }, 5000);
    }
}
