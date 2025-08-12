// Dashboard Main JavaScript
document.addEventListener('DOMContentLoaded', function() {
    // WebSocket connection
    let socket = null;
    let reconnectAttempts = 0;
    const MAX_RECONNECT_ATTEMPTS = 5;
    const RECONNECT_DELAY = 3000;
    
    // Ping data for chart
    const pingData = {
        timestamps: [],
        values: []
    };
    const MAX_PING_POINTS = 30;
    
    // Initialize the dashboard
    initializeDashboard();
    
    // Connect to WebSocket for real-time updates
    connectWebSocket();
    
    // Update clock every second
    setInterval(updateClock, 1000);
    
    // Error log toggle
    const errorLogHeader = document.getElementById('error-log-header');
    const errorLogContent = document.getElementById('error-log-content');
    errorLogHeader.addEventListener('click', function() {
        errorLogHeader.classList.toggle('open');
        errorLogContent.classList.toggle('open');
    });
    
    // Connect/Disconnect buttons
    const connectBtn = document.getElementById('connect-btn');
    const disconnectBtn = document.getElementById('disconnect-btn');
    
    connectBtn.addEventListener('click', function() {
        sendCommand('connect_telescope');
    });
    
    disconnectBtn.addEventListener('click', function() {
        sendCommand('disconnect_telescope');
    });
    
    // Initialize Dashboard Components
    function initializeDashboard() {
        updateClock();
        initPingChart();
    }
    
    // WebSocket Connection
    function connectWebSocket() {
        // Close existing socket if needed
        if (socket) {
            socket.close();
        }
        
        // Create new WebSocket connection
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;
        
        socket = new WebSocket(wsUrl);
        
        socket.onopen = function() {
            console.log('WebSocket connection established');
            reconnectAttempts = 0;
        };
        
        socket.onmessage = function(event) {
            try {
                const data = JSON.parse(event.data);
                handleWebSocketUpdate(data);
            } catch (error) {
                console.error('Error parsing WebSocket message:', error);
            }
        };
        
        socket.onclose = function() {
            console.log('WebSocket connection closed');
            
            // Attempt to reconnect
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                reconnectAttempts++;
                setTimeout(connectWebSocket, RECONNECT_DELAY);
                console.log(`Reconnecting... Attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS}`);
            } else {
                console.error('Maximum reconnect attempts reached');
            }
        };
        
        socket.onerror = function(error) {
            console.error('WebSocket error:', error);
        };
    }
    
    // Send command to server
    function sendCommand(command, payload = {}) {
        if (socket && socket.readyState === WebSocket.OPEN) {
            const message = {
                command: command,
                ...payload
            };
            socket.send(JSON.stringify(message));
        } else {
            console.error('WebSocket not connected');
        }
    }
    
    // Handle WebSocket updates
    function handleWebSocketUpdate(data) {
        // Handle telescope connection stats
        if (data.connection_stats) {
            updateConnectionStats(data.connection_stats);
        }
        
        // Handle telescope status
        if (data.telescope_status) {
            updateTelescopeStatus(data.telescope_status);
        } else {
            const telescopeStatusContainer = document.getElementById('telescope-status-container');
            telescopeStatusContainer.innerHTML = '<p>Not connected to telescope</p>';
        }
        
        // Handle upcoming passes
        if (data.upcoming_passes) {
            updateUpcomingPasses(data.upcoming_passes);
        }
        
        // Handle weather data
        if (data.weather) {
            updateWeatherData(data.weather);
        }
        
        // Handle command results
        if (data.command_result) {
            console.log('Command result:', data.command_result);
        }
        
        // Update visualization data if needed
        // This is handled in visualization.js
        if (data.upcoming_passes && data.upcoming_passes.length > 0) {
            // The visualization.js file will check for this global variable
            window.nextSatellitePass = data.upcoming_passes[0];
        }
    }
    
    // Update connection stats display
    function updateConnectionStats(stats) {
        // Update status indicator
        const statusIcon = document.getElementById('connection-status-icon');
        const statusText = document.getElementById('connection-status-text');
        
        statusIcon.className = 'status-icon';
        switch (stats.current_status) {
            case 'Connected':
                statusIcon.classList.add('connected');
                statusText.innerText = 'Connected';
                break;
            case 'Connecting':
                statusIcon.classList.add('connecting');
                statusText.innerText = 'Connecting...';
                break;
            default:
                statusIcon.classList.add('disconnected');
                statusText.innerText = 'Disconnected';
                break;
        }
        
        // Update stats values
        document.getElementById('connection-attempts').innerText = stats.connection_attempts;
        document.getElementById('successful-connections').innerText = stats.successful_connections;
        document.getElementById('disconnections').innerText = stats.disconnections;
        
        // Update timestamps
        document.getElementById('last-connected').innerText = stats.last_connected 
            ? new Date(stats.last_connected).toLocaleString() 
            : 'Never';
        document.getElementById('last-disconnected').innerText = stats.last_disconnected 
            ? new Date(stats.last_disconnected).toLocaleString() 
            : 'Never';
        
        // Update uptime
        const uptime = formatDuration(stats.uptime_seconds);
        document.getElementById('uptime').innerText = uptime;
        
        // Update error log
        if (stats.error_log && stats.error_log.length > 0) {
            const errorLogContainer = document.getElementById('error-log-container');
            errorLogContainer.innerHTML = '';
            
            stats.error_log.forEach(error => {
                const errorEntry = document.createElement('div');
                errorEntry.className = 'log-entry';
                errorEntry.innerHTML = `
                    <span class="log-timestamp">${new Date(error.timestamp).toLocaleString()}</span>
                    <span class="log-message">${error.error}</span>
                `;
                errorLogContainer.appendChild(errorEntry);
            });
        }
        
        // Add to ping data if we have ping responses
        if (stats.ping_responses && stats.ping_responses.length > 0) {
            const lastPing = stats.ping_responses[stats.ping_responses.length - 1];
            if (lastPing) {
                addPingData(new Date(), lastPing.response_time);
                
                // Update ping stats
                document.getElementById('current-ping').innerText = `${lastPing.response_time.toFixed(2)}ms`;
                
                // Calculate average and max
                const pingValues = pingData.values;
                if (pingValues.length > 0) {
                    const avgPing = pingValues.reduce((a, b) => a + b, 0) / pingValues.length;
                    const maxPing = Math.max(...pingValues);
                    
                    document.getElementById('average-ping').innerText = `${avgPing.toFixed(2)}ms`;
                    document.getElementById('max-ping').innerText = `${maxPing.toFixed(2)}ms`;
                }
            }
        }
    }
    
    // Update telescope status display
    function updateTelescopeStatus(status) {
        if (!status) {
            return;
        }
        
        const telescopeStatusContainer = document.getElementById('telescope-status-container');
        
        // Handle error case
        if (status.error) {
            telescopeStatusContainer.innerHTML = `
                <p class="error-message">Error: ${status.error}</p>
            `;
            return;
        }
        
        // Format the status display
        let statusHtml = '<div class="telescope-details">';
        
        if (status.system_version) {
            statusHtml += `<div class="detail-item"><span class="detail-label">Version:</span> ${status.system_version}</div>`;
        }
        
        if (status.mount) {
            statusHtml += `
                <div class="detail-item">
                    <span class="detail-label">Battery:</span> 
                    ${status.mount.battery_level} (${status.mount.battery_voltage.toFixed(2)}V)
                </div>
                <div class="detail-item">
                    <span class="detail-label">Aligned:</span> 
                    ${status.mount.is_aligned ? 'Yes' : 'No'}
                </div>
                <div class="detail-item">
                    <span class="detail-label">Tracking:</span> 
                    ${status.mount.is_tracking ? 'Yes' : 'No'}
                </div>
                <div class="detail-item">
                    <span class="detail-label">Time:</span> 
                    ${status.mount.timestamp}
                </div>
            `;
        }
        
        if (status.environment) {
            statusHtml += `
                <div class="detail-item">
                    <span class="detail-label">Temperature:</span> 
                    ${typeof status.environment.ambient_temp === 'number' 
                        ? status.environment.ambient_temp.toFixed(1) + '°C' 
                        : status.environment.ambient_temp}
                </div>
                <div class="detail-item">
                    <span class="detail-label">Humidity:</span> 
                    ${typeof status.environment.humidity === 'number' 
                        ? status.environment.humidity.toFixed(1) + '%' 
                        : status.environment.humidity}
                </div>
                <div class="detail-item">
                    <span class="detail-label">Dew Point:</span> 
                    ${typeof status.environment.dew_point === 'number' 
                        ? status.environment.dew_point.toFixed(1) + '°C' 
                        : status.environment.dew_point}
                </div>
            `;
        }
        
        statusHtml += '</div>';
        telescopeStatusContainer.innerHTML = statusHtml;
    }
    
    // Update upcoming passes table
    function updateUpcomingPasses(passes) {
        const tableBody = document.getElementById('tle-table-body');
        const noPassesMessage = document.getElementById('no-passes-message');
        
        if (!passes || passes.length === 0) {
            tableBody.innerHTML = '';
            noPassesMessage.style.display = 'block';
            return;
        }
        
        noPassesMessage.style.display = 'none';
        tableBody.innerHTML = '';
        
        passes.forEach(pass => {
            const startTime = new Date(pass.startUTC_actual * 1000).toISOString().replace('T', ' ').substring(0, 19);
            
            const row = document.createElement('tr');
            row.innerHTML = `
                <td>${pass.satname || 'Unknown'}</td>
                <td>${pass.norad_id}</td>
                <td>${pass.maxElevation_actual ? pass.maxElevation_actual.toFixed(1) + '°' : 'N/A'}</td>
                <td>${startTime}</td>
                <td class="countdown">${pass.countdown || 'N/A'}</td>
            `;
            
            tableBody.appendChild(row);
        });
    }
    
    // Update weather data display
    function updateWeatherData(weather) {
        const currentConditionsContainer = document.getElementById('current-conditions');
        const forecastContainer = document.getElementById('forecast-hours');
        
        // Clear loading message and previous forecast
        currentConditionsContainer.innerHTML = ''; // Clear loading/error message
        forecastContainer.innerHTML = '';

        if (weather.error) {
            currentConditionsContainer.innerHTML = `
                <div class="weather-error">
                    <p>${weather.error}</p>
                </div>
            `;
            return;
        }
        
        if (!weather || weather.length === 0) {
             currentConditionsContainer.innerHTML = `
                <div class="weather-loading">
                    <p>No weather data available for the selected period.</p>
                </div>
            `;
            return;
        }
        
        // Add forecast items
        weather.forEach(hour => {
            const forecastHour = document.createElement('div');
            forecastHour.className = 'forecast-hour';
            
            let ratingClass = '';
            switch (hour.observation_rating) {
                case 'Excellent':
                    ratingClass = 'rating-excellent';
                    break;
                case 'Good':
                    ratingClass = 'rating-good';
                    break;
                case 'Fair':
                    ratingClass = 'rating-fair';
                    break;
                case 'Poor':
                    ratingClass = 'rating-poor';
                    break;
            }
            
            forecastHour.innerHTML = `
                <div class="forecast-time">${hour.time}</div>
                <div class="forecast-condition">${hour.sky_condition}</div>
                <div class="forecast-detail">Clouds: ${hour.clouds}%</div>
                <div class="forecast-detail">Visibility: ${hour.visibility_km}km</div>
                <div class="forecast-detail">Temp: ${hour.temperature}°C</div>
                <div class="forecast-rating ${ratingClass}">${hour.observation_rating}</div>
            `;
            
            forecastContainer.appendChild(forecastHour);
        });
    }
    
    // Initialize ping chart
    function initPingChart() {
        const ctx = document.getElementById('ping-chart').getContext('2d');
        window.pingChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: [],
                datasets: [{
                    label: 'Response Time (ms)',
                    data: [],
                    borderColor: '#3498db',
                    backgroundColor: 'rgba(52, 152, 219, 0.1)',
                    borderWidth: 2,
                    fill: true,
                    tension: 0.4
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#ecf0f1'
                        }
                    },
                    x: {
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)'
                        },
                        ticks: {
                            color: '#ecf0f1',
                            maxTicksLimit: 5
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false
                    }
                }
            }
        });
    }
    
    // Add ping data point and update chart
    function addPingData(timestamp, value) {
        // Add to data arrays
        pingData.timestamps.push(timestamp);
        pingData.values.push(value);
        
        // Keep only the last MAX_PING_POINTS
        if (pingData.timestamps.length > MAX_PING_POINTS) {
            pingData.timestamps.shift();
            pingData.values.shift();
        }
        
        // Update chart
        window.pingChart.data.labels = pingData.timestamps.map(t => t.toLocaleTimeString());
        window.pingChart.data.datasets[0].data = pingData.values;
        window.pingChart.update();
    }
    
    // Format duration in seconds to HH:MM:SS
    function formatDuration(totalSeconds) {
        if (!totalSeconds && totalSeconds !== 0) return '00:00:00';
        
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = Math.floor(totalSeconds % 60);
        
        return [
            hours.toString().padStart(2, '0'),
            minutes.toString().padStart(2, '0'),
            seconds.toString().padStart(2, '0')
        ].join(':');
    }
    
    // Update clock display
    function updateClock() {
        const now = new Date();
        const utcNow = new Date(now.getTime());
        
        document.getElementById('local-time').textContent = now.toLocaleTimeString();
        document.getElementById('utc-time').textContent = utcNow.toLocaleTimeString() + ' UTC';
    }
}); 