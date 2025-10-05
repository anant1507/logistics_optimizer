// Basic JavaScript functionality

// Set minimum date for schedule creation to today
document.addEventListener('DOMContentLoaded', function() {
    const dateInput = document.getElementById('scheduled_date');
    if (dateInput) {
        const today = new Date().toISOString().split('T')[0];
        dateInput.min = today;
    }
    
    // Add confirmation for important actions
    const deleteButtons = document.querySelectorAll('.delete-btn');
    deleteButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            if (!confirm('Are you sure you want to delete this item?')) {
                e.preventDefault();
            }
        });
    });
});

// File upload handling
function handleFileUpload(input) {
    const file = input.files[0];
    if (file) {
        const fileName = file.name;
        const fileSize = (file.size / 1024 / 1024).toFixed(2); // Size in MB
        
        if (fileSize > 10) {
            alert('File size exceeds 10MB limit. Please choose a smaller file.');
            input.value = '';
            return;
        }
        
        // Update UI to show selected file
        const fileNameDisplay = document.getElementById('file-name');
        if (fileNameDisplay) {
            fileNameDisplay.textContent = `Selected: ${fileName} (${fileSize} MB)`;
        }
    }
}

// Additional JavaScript functions

// Stock level editing
function makeStockEditable(element, type, id, currentStock) {
    if (!element.classList.contains('can-edit')) return;
    
    const input = document.createElement('input');
    input.type = 'number';
    input.value = currentStock;
    input.className = 'stock-input';
    input.min = 0;
    
    element.innerHTML = '';
    element.appendChild(input);
    input.focus();
    
    const saveStock = function() {
        const newStock = parseInt(input.value);
        if (!isNaN(newStock) && newStock >= 0) {
            updateStock(type, id, newStock);
        } else {
            element.textContent = currentStock;
        }
    };
    
    input.addEventListener('blur', saveStock);
    input.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            saveStock();
        }
    });
}

function updateStock(type, id, newStock) {
    fetch('/update_stock', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            type: type,
            id: id,
            stock: newStock
        })
    })
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            location.reload(); // Reload to show updated stock
        } else {
            alert('Error: ' + result.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Failed to update stock');
    });
}

// Schedule management
function deleteSchedule(scheduleId) {
    if (!confirm('Are you sure you want to delete this schedule?')) {
        return;
    }
    
    fetch('/delete_schedule/' + scheduleId)
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            location.reload();
        } else {
            alert('Error: ' + result.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Failed to delete schedule');
    });
}

function updateScheduleStatus(scheduleId, newStatus) {
    fetch('/update_schedule_status/' + scheduleId + '/' + newStatus)
    .then(response => response.json())
    .then(result => {
        if (result.success) {
            location.reload();
        } else {
            alert('Error: ' + result.message);
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Failed to update schedule status');
    });
}