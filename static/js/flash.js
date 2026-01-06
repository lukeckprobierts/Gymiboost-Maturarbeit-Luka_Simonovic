document.addEventListener('DOMContentLoaded', function() {
    // Handle both flash messages and alerts
    const messages = document.querySelectorAll('.flash-message, .alert');
    
    messages.forEach(function(message) {
        // Fade out after 3 seconds
        setTimeout(function() {
            message.style.transition = 'opacity 0.5s ease';
            message.style.opacity = '0';
            
            // Remove from DOM after fade out
            setTimeout(function() {
                message.remove();
            }, 500);
        }, 3000);
    });
});