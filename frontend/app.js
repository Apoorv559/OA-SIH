document.addEventListener('DOMContentLoaded', () => {
    // ========================== RISK PREDICTOR ==========================
    const form = document.getElementById('prediction-form');
    const heightInput = document.getElementById('Height');
    const weightInput = document.getElementById('Weight');
    const bmiInput = document.getElementById('BMI');
    const submitBtn = document.getElementById('submit-btn');
    
    const modal = document.getElementById('result-modal');
    const closeBtn = document.querySelector('.close-btn');
    const resetBtn = document.getElementById('reset-btn');
    const riskScoreEl = document.getElementById('risk-score');
    const riskProbabilitiesEl = document.getElementById('risk-probabilities');

    const API_URL = 'http://10.101.53.71:8000/predict'; // FastAPI local IP address

    // Auto-calculate BMI
    const calculateBMI = () => {
        const height = parseFloat(heightInput.value);
        const weight = parseFloat(weightInput.value);
        
        if (height && weight && height > 0) {
            // Height is in cm, convert to meters
            const heightM = height / 100;
            const bmi = weight / (heightM * heightM);
            bmiInput.value = bmi.toFixed(1);
        } else {
            bmiInput.value = '';
        }
    };

    heightInput.addEventListener('input', calculateBMI);
    weightInput.addEventListener('input', calculateBMI);

    // Form Submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        if (!bmiInput.value) {
            alert('Please enter valid Height and Weight to calculate BMI.');
            return;
        }

        // Gather form data
        const formData = new FormData(form);
        const payload = {
            Age: parseFloat(formData.get('Age')),
            Sex: formData.get('Sex'),
            Height: parseFloat(formData.get('Height')),
            Weight: parseFloat(formData.get('Weight')),
            BMI: parseFloat(formData.get('BMI')),
            Previous_injury: formData.get('Previous_injury'),
            Surgery: formData.get('Surgery'),
            Family_history: formData.get('Family_history'),
            Occupation: formData.get('Occupation'),
            Physical_activity: formData.get('Physical_activity'),
            Pain: parseFloat(formData.get('Pain')),
            Morning_stiffness: formData.get('Morning_stiffness'),
            Functional_limitations: formData.get('Functional_limitations'),
            Relevant_comorbidities: formData.get('Relevant_comorbidities')
        };

        // Loading state
        const originalBtnText = submitBtn.innerText;
        submitBtn.innerText = 'Analyzing...';
        submitBtn.disabled = true;

        try {
            const response = await fetch(API_URL, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                throw new Error(`API Error: ${response.statusText}`);
            }

            const data = await response.json();
            showResult(data);

        } catch (error) {
            console.error('Error:', error);
            alert('Failed to connect to the prediction server. Ensure the backend is running on http://localhost:8000.');
        } finally {
            submitBtn.innerText = originalBtnText;
            submitBtn.disabled = false;
        }
    });

    // Show Result in Modal
    const showResult = (data) => {
        const prediction = data.prediction; // e.g., "High Risk"
        const probs = data.probabilities;

        riskScoreEl.textContent = prediction;
        
        // Remove old classes and add color class
        riskScoreEl.className = 'risk-score';
        if (prediction.includes('Low')) riskScoreEl.classList.add('risk-Low');
        else if (prediction.includes('Moderate')) riskScoreEl.classList.add('risk-Moderate');
        else if (prediction.includes('High')) riskScoreEl.classList.add('risk-High');

        // Format probabilities if available
        if (probs && Object.keys(probs).length > 0) {
            let probText = '<strong>Confidence:</strong><br>';
            for (const [cls, p] of Object.entries(probs)) {
                probText += `${cls}: ${(p * 100).toFixed(1)}%<br>`;
            }
            riskProbabilitiesEl.innerHTML = probText;
        } else {
            riskProbabilitiesEl.innerHTML = '';
        }

        modal.classList.remove('hidden');
    };

    // Close Modal Logic
    const closeModal = () => {
        modal.classList.add('hidden');
    };

    closeBtn.addEventListener('click', closeModal);
    resetBtn.addEventListener('click', () => {
        closeModal();
        form.reset();
        bmiInput.value = '';
        document.querySelector('output').value = '5'; // Reset slider output
    });

    // Close on outside click
    window.addEventListener('click', (e) => {
        if (e.target === modal) {
            closeModal();
        }
    });

    // ========================== NAVIGATION ==========================
    const navRisk = document.getElementById('nav-risk');
    const navMovement = document.getElementById('nav-movement');
    const navIot = document.getElementById('nav-iot');
    const sectionRisk = document.getElementById('risk-score-section');
    const sectionMovement = document.getElementById('movement-assessment-section');
    const sectionIot = document.getElementById('iot-dashboard-section');

    const allNavBtns = [navRisk, navMovement, navIot];
    const allSections = [sectionRisk, sectionMovement, sectionIot];

    function switchSection(activeBtn, activeSection) {
        allNavBtns.forEach(btn => btn.classList.remove('active'));
        allSections.forEach(sec => {
            sec.classList.remove('active');
            sec.classList.add('hidden');
        });
        activeBtn.classList.add('active');
        activeSection.classList.add('active');
        activeSection.classList.remove('hidden');
    }

    navRisk.addEventListener('click', () => switchSection(navRisk, sectionRisk));
    navMovement.addEventListener('click', () => switchSection(navMovement, sectionMovement));
    navIot.addEventListener('click', () => {
        switchSection(navIot, sectionIot);
        // Initialize charts on first visit
        if (!chartsInitialized) initCharts();
    });

    // ========================== MOVEMENT ASSESSMENT ==========================
    const videoRecord = document.getElementById('video-record');
    const videoUpload = document.getElementById('video-upload');
    const fileNameDisplay = document.getElementById('file-name-display');
    const analyzeBtn = document.getElementById('analyze-btn');
    const loadingSpinner = document.getElementById('loading-spinner');
    const assessmentResults = document.getElementById('assessment-results');
    const movementType = document.getElementById('movement-type');
    let selectedFile = null;

    const handleFileSelect = (e) => {
        selectedFile = e.target.files[0];
        if (selectedFile) {
            fileNameDisplay.textContent = `Selected: ${selectedFile.name}`;
            fileNameDisplay.classList.remove('hidden');
            analyzeBtn.disabled = false;
        } else {
            fileNameDisplay.classList.add('hidden');
            analyzeBtn.disabled = true;
        }
    };

    videoRecord.addEventListener('change', handleFileSelect);
    videoUpload.addEventListener('change', handleFileSelect);

    analyzeBtn.addEventListener('click', async () => {
        if (!selectedFile) return;

        const formData = new FormData();
        formData.append('video', selectedFile);
        formData.append('movement_type', movementType.value);

        // UI states
        analyzeBtn.disabled = true;
        loadingSpinner.classList.remove('hidden');
        assessmentResults.classList.add('hidden');

        try {
            const response = await fetch('http://10.101.53.71:8000/api/analyze-movement', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                const err = await response.json();
                throw new Error(err.detail || 'Failed to analyze video');
            }

            const data = await response.json();
            
            // Populate results
            document.getElementById('bio-score-val').textContent = data.biomechanical_score;
            document.getElementById('knee-rom-val').textContent = `${data.left_knee_ROM}° / ${data.right_knee_ROM}°`;
            document.getElementById('symmetry-val').textContent = data.movement_symmetry;
            document.getElementById('hip-angle-val').textContent = `${data.avg_left_hip_angle}° / ${data.avg_right_hip_angle}°`;
            document.getElementById('knee-angle-val').textContent = `${data.avg_left_knee_angle}° / ${data.avg_right_knee_angle}°`;
            document.getElementById('ankle-angle-val').textContent = `${data.avg_left_ankle_angle}° / ${data.avg_right_ankle_angle}°`;
            document.getElementById('gait-val').textContent = data.gait_characteristics;

            // Change score color based on value
            const scoreCircle = document.querySelector('.score-circle');
            if (data.biomechanical_score > 80) {
                scoreCircle.style.color = '#10b981'; // Green
            } else if (data.biomechanical_score > 60) {
                scoreCircle.style.color = '#f59e0b'; // Amber
            } else {
                scoreCircle.style.color = '#ef4444'; // Red
            }

            // Show results
            assessmentResults.classList.remove('hidden');
            
        } catch (error) {
            console.error(error);
            alert(`Error analyzing movement: ${error.message}`);
        } finally {
            analyzeBtn.disabled = false;
            loadingSpinner.classList.add('hidden');
        }
    });


    // ========================== IOT DASHBOARD ==========================
    let chartsInitialized = false;
    let dashboardWS = null;
    let isConnected = false;

    // Chart instances
    let kneeAngleChart = null;
    let loadDistChart = null;
    let imuActivityChart = null;

    // Data buffers for charts (rolling window)
    const MAX_DATA_POINTS = 100; // ~2 seconds at 50Hz
    const chartLabels = [];
    const kneeLeftData = [];
    const kneeRightData = [];
    const loadLeftData = [];
    const loadRightData = [];
    const accelLTData = [];
    const accelRTData = [];
    const accelLSData = [];
    const accelRSData = [];

    // Common chart styling
    const chartDefaults = {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 0 }, // Disable animation for real-time performance
        plugins: {
            legend: {
                labels: {
                    color: '#cbd5e1',
                    font: { family: 'Inter', size: 11 },
                    boxWidth: 12,
                    padding: 12,
                }
            }
        },
        scales: {
            x: {
                display: false,
            },
            y: {
                grid: {
                    color: 'rgba(255,255,255,0.05)',
                },
                ticks: {
                    color: '#94a3b8',
                    font: { size: 10 },
                }
            }
        }
    };

    function initCharts() {
        if (chartsInitialized) return;

        // Knee Angle Chart
        const ctxKnee = document.getElementById('chart-knee-angles').getContext('2d');
        kneeAngleChart = new Chart(ctxKnee, {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [
                    {
                        label: 'Left Knee (°)',
                        data: kneeLeftData,
                        borderColor: '#818cf8',
                        backgroundColor: 'rgba(129, 140, 248, 0.1)',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3,
                        fill: true,
                    },
                    {
                        label: 'Right Knee (°)',
                        data: kneeRightData,
                        borderColor: '#f472b6',
                        backgroundColor: 'rgba(244, 114, 182, 0.1)',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3,
                        fill: true,
                    }
                ]
            },
            options: {
                ...chartDefaults,
                scales: {
                    ...chartDefaults.scales,
                    y: {
                        ...chartDefaults.scales.y,
                        min: 0,
                        max: 180,
                        title: { display: true, text: 'Degrees', color: '#64748b', font: { size: 10 } }
                    }
                }
            }
        });

        // Load Distribution Chart
        const ctxLoad = document.getElementById('chart-load-distribution').getContext('2d');
        loadDistChart = new Chart(ctxLoad, {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [
                    {
                        label: 'Left Foot',
                        data: loadLeftData,
                        borderColor: '#34d399',
                        backgroundColor: 'rgba(52, 211, 153, 0.1)',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3,
                        fill: true,
                    },
                    {
                        label: 'Right Foot',
                        data: loadRightData,
                        borderColor: '#fbbf24',
                        backgroundColor: 'rgba(251, 191, 36, 0.1)',
                        borderWidth: 2,
                        pointRadius: 0,
                        tension: 0.3,
                        fill: true,
                    }
                ]
            },
            options: {
                ...chartDefaults,
                scales: {
                    ...chartDefaults.scales,
                    y: {
                        ...chartDefaults.scales.y,
                        min: 0,
                        title: { display: true, text: 'Total Load', color: '#64748b', font: { size: 10 } }
                    }
                }
            }
        });

        // IMU Activity Chart
        const ctxIMU = document.getElementById('chart-imu-activity').getContext('2d');
        imuActivityChart = new Chart(ctxIMU, {
            type: 'line',
            data: {
                labels: chartLabels,
                datasets: [
                    {
                        label: 'L-Thigh',
                        data: accelLTData,
                        borderColor: '#818cf8',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        tension: 0.3,
                    },
                    {
                        label: 'R-Thigh',
                        data: accelRTData,
                        borderColor: '#f472b6',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        tension: 0.3,
                    },
                    {
                        label: 'L-Shin',
                        data: accelLSData,
                        borderColor: '#34d399',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        tension: 0.3,
                    },
                    {
                        label: 'R-Shin',
                        data: accelRSData,
                        borderColor: '#fbbf24',
                        borderWidth: 1.5,
                        pointRadius: 0,
                        tension: 0.3,
                    }
                ]
            },
            options: {
                ...chartDefaults,
                scales: {
                    ...chartDefaults.scales,
                    y: {
                        ...chartDefaults.scales.y,
                        title: { display: true, text: 'Accel (m/s²)', color: '#64748b', font: { size: 10 } }
                    }
                }
            }
        });

        chartsInitialized = true;
    }

    // ========================== WEBSOCKET CONNECTION ==========================

    const connectBtn = document.getElementById('iot-connect-btn');
    const statusDot = document.getElementById('iot-status-dot');
    const statusText = document.getElementById('iot-status-text');
    const alertBanner = document.getElementById('iot-alert-banner');
    const alertTextEl = document.getElementById('iot-alert-text');
    const alertDismiss = document.getElementById('iot-alert-dismiss');

    connectBtn.addEventListener('click', () => {
        if (isConnected) {
            disconnectDashboard();
        } else {
            connectDashboard();
        }
    });

    alertDismiss.addEventListener('click', () => {
        alertBanner.classList.add('hidden');
    });

    function connectDashboard() {
        const wsUrl = `ws://${window.location.hostname || 'localhost'}:8000/ws/dashboard`;
        dashboardWS = new WebSocket(wsUrl);

        dashboardWS.onopen = () => {
            isConnected = true;
            statusDot.className = 'status-dot connected';
            statusText.textContent = 'ESP32 Connected';
            connectBtn.textContent = 'Disconnect';
            connectBtn.classList.add('active');
            console.log('[Dashboard WS] Connected');
        };

        dashboardWS.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'summary' || data.type === 'info') return;
                updateDashboard(data);
            } catch (e) {
                console.warn('[Dashboard WS] Parse error:', e);
            }
        };

        dashboardWS.onclose = () => {
            isConnected = false;
            statusDot.className = 'status-dot disconnected';
            statusText.textContent = 'ESP32 Disconnected';
            connectBtn.textContent = 'Connect';
            connectBtn.classList.remove('active');
            console.log('[Dashboard WS] Disconnected');
        };

        dashboardWS.onerror = (err) => {
            console.error('[Dashboard WS] Error:', err);
        };
    }

    function disconnectDashboard() {
        if (dashboardWS) {
            dashboardWS.close();
            dashboardWS = null;
        }
    }

    // ========================== DASHBOARD UPDATE ==========================

    let frameCount = 0;

    function updateDashboard(data) {
        frameCount++;

        // --- Joint Angles ---
        const angles = data.joint_angles || {};
        document.getElementById('iot-left-knee').textContent = `${angles.left_knee ?? '--'}°`;
        document.getElementById('iot-right-knee').textContent = `${angles.right_knee ?? '--'}°`;

        // --- Gait ---
        const gait = data.gait || {};
        document.getElementById('iot-step-count').textContent = `Steps: ${gait.step_count ?? 0}`;
        document.getElementById('iot-cadence').textContent = `Cadence: ${gait.cadence ?? '--'} spm`;
        document.getElementById('iot-stride-time').textContent = `Stride: ${gait.stride_time ?? '--'} s`;

        // Update gait phase indicators
        updateGaitPhase('gait-phase-left', gait.phase_left);
        updateGaitPhase('gait-phase-right', gait.phase_right);

        // --- Pressure ---
        const pressure = data.pressure || {};
        document.getElementById('iot-load-asymmetry').textContent = 
            `${((pressure.load_asymmetry ?? 0) * 100).toFixed(1)}%`;

        // Update pressure heatmap (using raw data from the stream)
        // We use left_foot_load and right_foot_load for overall,
        // and the data flows via the FSR zones for individual zones
        updatePressureZones(pressure);

        // --- Activity ---
        const activity = data.activity || {};
        document.getElementById('iot-lt-accel').textContent = activity.left_thigh ?? '--';
        document.getElementById('iot-rt-accel').textContent = activity.right_thigh ?? '--';
        document.getElementById('iot-ls-accel').textContent = activity.left_shin ?? '--';
        document.getElementById('iot-rs-accel').textContent = activity.right_shin ?? '--';

        // --- Charts (update every 2nd frame for performance) ---
        if (frameCount % 2 === 0) {
            const label = frameCount.toString();
            pushDataPoint(chartLabels, label);
            pushDataPoint(kneeLeftData, angles.left_knee ?? 0);
            pushDataPoint(kneeRightData, angles.right_knee ?? 0);
            pushDataPoint(loadLeftData, pressure.left_foot_load ?? 0);
            pushDataPoint(loadRightData, pressure.right_foot_load ?? 0);
            pushDataPoint(accelLTData, activity.left_thigh ?? 0);
            pushDataPoint(accelRTData, activity.right_thigh ?? 0);
            pushDataPoint(accelLSData, activity.left_shin ?? 0);
            pushDataPoint(accelRSData, activity.right_shin ?? 0);

            if (kneeAngleChart) kneeAngleChart.update();
            if (loadDistChart) loadDistChart.update();
            if (imuActivityChart) imuActivityChart.update();
        }

        // --- Alerts ---
        const alert = data.alert || {};
        if (alert.active) {
            alertTextEl.textContent = alert.message;
            alertBanner.classList.remove('hidden');
        }
    }

    function pushDataPoint(arr, value) {
        arr.push(value);
        if (arr.length > MAX_DATA_POINTS) arr.shift();
    }

    function updateGaitPhase(elementId, phase) {
        const el = document.getElementById(elementId);
        if (!el) return;
        const p = (phase || 'unknown').toLowerCase();
        el.textContent = p.replace('_', ' ');
        el.className = `phase-indicator ${p}`;
    }

    function updatePressureZones(pressure) {
        // Since the edge processor sends total load values,
        // we use a simple mapping for heat levels.
        // In a production system, individual FSR values would be streamed too.
        const leftLoad = pressure.left_foot_load ?? 0;
        const rightLoad = pressure.right_foot_load ?? 0;

        // Estimate zone values (distribute evenly as placeholder when no individual data)
        const leftZoneAvg = leftLoad / 4;
        const rightZoneAvg = rightLoad / 4;

        const zones = [
            { id: 'pz-l-heel', val: leftZoneAvg },
            { id: 'pz-l-toe', val: leftZoneAvg },
            { id: 'pz-l-outer', val: leftZoneAvg },
            { id: 'pz-l-inner', val: leftZoneAvg },
            { id: 'pz-r-heel', val: rightZoneAvg },
            { id: 'pz-r-toe', val: rightZoneAvg },
            { id: 'pz-r-outer', val: rightZoneAvg },
            { id: 'pz-r-inner', val: rightZoneAvg },
        ];

        zones.forEach(zone => {
            const el = document.getElementById(zone.id);
            if (!el) return;
            const valEl = el.querySelector('.pz-val');
            if (valEl) valEl.textContent = Math.round(zone.val);

            // Set heat level class (0-4)
            const heat = getHeatLevel(zone.val);
            el.className = el.className.replace(/heat-\d/g, '').trim();
            el.classList.add(`heat-${heat}`);
        });
    }

    function getHeatLevel(value) {
        if (value < 100) return 0;
        if (value < 500) return 1;
        if (value < 1500) return 2;
        if (value < 3000) return 3;
        return 4;
    }
});
