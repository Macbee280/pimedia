// Main functionality for PiMedia Player
document.addEventListener('DOMContentLoaded', function() {
    // Elements
    const youtubeForm = document.getElementById('youtube-form');
    const youtubeUrlInput = document.getElementById('youtube-url');
    const stopBtn = document.getElementById('stop-btn');
    const refreshBtn = document.getElementById('refresh-btn');
    const statusText = document.getElementById('status-text');
    const statusIndicator = document.querySelector('.status-dot');
    const dashboardItems = document.querySelectorAll('.dashboard-item');
    const presetItems = document.querySelectorAll('.preset-item');
    const castStatus = document.getElementById('cast-status');
    const currentTimeEl = document.getElementById('current-time');
    const qrImage = document.getElementById('cast-qr-code');
    
    // Update current time
    function updateTime() {
        const now = new Date();
        const hours = now.getHours().toString().padStart(2, '0');
        const minutes = now.getMinutes().toString().padStart(2, '0');
        const seconds = now.getSeconds().toString().padStart(2, '0');
        currentTimeEl.textContent = `${hours}:${minutes}:${seconds}`;
    }
    
    // Update status display
    function updateStatus() {
        fetch('/api/status')
            .then(response => response.json())
            .then(data => {
                if (data.display_type === null || data.current_display === null) {
                    statusText.textContent = 'Idle';
                    statusIndicator.style.backgroundColor = '#34c759'; // Green
                } else if (data.display_type === 'youtube' || data.display_type === 'youtube_cast') {
                    statusText.textContent = 'Playing YouTube';
                    statusIndicator.style.backgroundColor = '#ff3b30'; // Red
                } else if (data.display_type === 'dashboard') {
                    statusText.textContent = 'Showing Dashboard';
                    statusIndicator.style.backgroundColor = '#007aff'; // Blue
                } else if (data.display_type === 'media_cast') {
                    statusText.textContent = 'Casting Media';
                    statusIndicator.style.backgroundColor = '#ff9500'; // Orange
                }
            })
            .catch(error => {
                console.error('Error fetching status:', error);
                statusText.textContent = 'Error';
                statusIndicator.style.backgroundColor = '#ff3b30'; // Red
            });
    }
    
    // Play YouTube URL
    function playYouTubeUrl(url) {
        // Visual feedback - show loading in status
        statusText.textContent = 'Loading...';
        
        // Prepare form data
        const formData = new FormData();
        formData.append('youtube_url', url);
        
        // Submit to API
        fetch('/api/play-youtube', {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            console.log(data);
            updateStatus();
        })
        .catch(error => {
            console.error('Error playing YouTube video:', error);
            updateStatus();
        });
    }
    
    // Handle YouTube form submission
    youtubeForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        const youtubeUrl = youtubeUrlInput.value.trim();
        if (!youtubeUrl) return;
        
        // Visual feedback
        const submitBtn = youtubeForm.querySelector('button[type="submit"]');
        submitBtn.textContent = 'Loading...';
        submitBtn.disabled = true;
        
        playYouTubeUrl(youtubeUrl);
        
        // Reset form
        youtubeUrlInput.value = '';
        
        // Reset button
        setTimeout(() => {
            submitBtn.textContent = 'Play';
            submitBtn.disabled = false;
        }, 1000);
    });
    
    // Handle preset selections
    presetItems.forEach(item => {
        item.addEventListener('click', function() {
            const youtubeUrl = this.getAttribute('data-url');
            if (!youtubeUrl) return;
            
            // Visual feedback - add active class
            presetItems.forEach(preset => preset.classList.remove('active'));
            this.classList.add('active');
            
            playYouTubeUrl(youtubeUrl);
            
            // Remove active class after a delay
            setTimeout(() => {
                this.classList.remove('active');
            }, 1000);
        });
    });
    
    // Handle dashboard selections
    dashboardItems.forEach(item => {
        item.addEventListener('click', function() {
            const dashboardUrl = this.getAttribute('data-url');
            
            // Visual feedback - add active class
            dashboardItems.forEach(dash => dash.classList.remove('active'));
            this.classList.add('active');
            
            // Prepare form data
            const formData = new FormData();
            formData.append('dashboard_url', dashboardUrl);
            
            // Submit to API
            fetch('/api/show-dashboard', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                console.log(data);
                updateStatus();
            })
            .catch(error => {
                console.error('Error showing dashboard:', error);
                this.classList.remove('active');
            });
        });
    });
    
    // Handle stop button
    stopBtn.addEventListener('click', function() {
        this.disabled = true;
        this.textContent = 'Stopping...';
        
        fetch('/api/stop', {
            method: 'POST'
        })
        .then(response => response.json())
        .then(data => {
            console.log(data);
            updateStatus();
            dashboardItems.forEach(dash => dash.classList.remove('active'));
            presetItems.forEach(preset => preset.classList.remove('active'));
        })
        .catch(error => {
            console.error('Error stopping display:', error);
        })
        .finally(() => {
            this.disabled = false;
            this.textContent = 'Stop Display';
        });
    });
    
    // Handle refresh button
    refreshBtn.addEventListener('click', function() {
        this.disabled = true;
        this.textContent = 'Refreshing...';
        
        updateStatus();
        refreshQRCode();
        
        setTimeout(() => {
            this.disabled = false;
            this.textContent = 'Refresh';
        }, 1000);
    });
    
    // Refresh QR code (in case the IP address changes)
    function refreshQRCode() {
        // Add a timestamp to force a fresh image
        const timestamp = new Date().getTime();
        qrImage.src = `/cast_qr?t=${timestamp}`;
    }
    
    // Setup websocket for cast connection
    function setupCastSocket() {
        // Create WebSocket connection.
        const protocol = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
        const wsUrl = `${protocol}${window.location.host}/ws/cast`;
        const socket = new WebSocket(wsUrl);
        
        socket.onopen = function(e) {
            console.log('Cast socket connected');
            castStatus.textContent = 'Ready to receive cast';
        };
        
        socket.onmessage = function(event) {
            console.log('Message from cast:', event.data);
            const data = JSON.parse(event.data);
            
            if (data.type === 'connect') {
                castStatus.textContent = 'Device connected: ' + data.device;
            } else if (data.type === 'disconnect') {
                castStatus.textContent = 'Device disconnected';
                setTimeout(() => {
                    castStatus.textContent = 'Ready to receive cast';
                }, 3000);
            } else if (data.type === 'cast') {
                castStatus.textContent = 'Receiving cast...';
                
                // Process media based on type
                if (data.media_type === 'youtube') {
                    playYouTubeUrl(data.url);
                    castStatus.textContent = 'Playing YouTube from cast';
                } else if (data.media_type === 'video' || data.media_type === 'audio') {
                    // Handle direct media URL
                    fetch('/api/cast-media', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            media_url: data.url,
                            media_type: data.media_type
                        })
                    })
                    .then(response => response.json())
                    .then(result => {
                        console.log(result);
                        updateStatus();
                        castStatus.textContent = 'Playing media from cast';
                    })
                    .catch(error => {
                        console.error('Error processing cast media:', error);
                        castStatus.textContent = 'Cast error';
                    });
                }
            } else if (data.type === 'error') {
                castStatus.textContent = 'Cast error: ' + data.message;
                setTimeout(() => {
                    castStatus.textContent = 'Ready to receive cast';
                }, 3000);
            }
        };
        
        socket.onclose = function(event) {
            console.log('Cast socket closed:', event);
            castStatus.textContent = 'Cast connection lost';
            
            // Try to reconnect after a delay
            setTimeout(() => {
                setupCastSocket();
            }, 5000);
        };
        
        socket.onerror = function(error) {
            console.error('Cast socket error:', error);
            castStatus.textContent = 'Cast error';
        };
    }
    
    // Check if WebSocket is supported
    if (window.WebSocket) {
        setupCastSocket();
    } else {
        castStatus.textContent = 'WebSocket not supported';
        console.error('WebSocket is not supported by your browser!');
    }
    
    // Initialize
    updateTime();
    setInterval(updateTime, 1000);
    updateStatus();
    setInterval(updateStatus, 5000);  // Poll status every 5 seconds
    
    // Refresh QR code periodically in case IP changes
    setInterval(refreshQRCode, 300000);  // Every 5 minutes
});