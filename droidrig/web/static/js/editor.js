/**
 * DroidRig Curve Editor
 * A timeline-based animation editor where you can draw servo position curves
 */

// Servo colors for the curves (vibrant palette)
const SERVO_COLORS = [
    '#3b9eff', // blue
    '#ff9f43', // orange
    '#26de81', // green
    '#a55eea', // purple
    '#fed330', // yellow
    '#fd79a8', // pink
    '#0abde3', // cyan
    '#ff6b6b', // red
    '#2ed573', // lime
    '#70a1ff', // light blue
    '#ffa502', // amber
    '#ff4757', // coral
    '#1dd1a1', // teal
    '#5f27cd', // violet
    '#ff9ff3', // magenta
    '#54a0ff', // sky blue
];

// State
let curves = {};  // { servoId: [{time, pulse}, ...] }
let annotations = [];  // [{ time, text }, ...]
let activeServo = 0;
let isDrawing = false;
let isDragging = false;
let selectedPoint = null;  // { servoIndex, pointIndex }
let selectedAnnotation = null;  // index
let annotationHoverX = null;  // hover position for preview
let pendingAnnotationTime = null;  // time for annotation being added
let rulerCanvas, rulerCtx;
let annotationCanvas, annotationCtx;
let audioCanvas, audioCtx;
let tracksCanvas, tracksCtx;
let trackHeight = 80;
let rulerHeight = 40;  // Height of the timeline ruler
let annotationHeight = 28;  // Height of the annotation track
let audioTrackHeight = 48;  // Height of the audio track
let duration = 3000;
let animationFrame = null;
let playStartTime = null;
let isPlaying = false;
let isPaused = false;
let pausedElapsed = 0;  // Time elapsed when paused
let canvasWidth = 0;  // Display width (not scaled)
let tracksHeight = 0; // Tracks canvas height (not scaled)
const POINT_HIT_RADIUS = 10;  // Pixels for point selection
const ANNOTATION_HIT_RADIUS = 15;  // Pixels for annotation selection
let lastLivePreviewTime = 0;  // Throttle live preview updates
const LIVE_PREVIEW_THROTTLE = 50;  // ms between live preview updates

// Audio state
let audioFile = null;  // { filename, duration_ms, waveform }
let audioElement = null;  // HTML5 Audio element for browser playback

// Initialize
async function init() {
    await loadServoConfigs();
    
    // Check if we're loading an existing animation or starting fresh
    const params = new URLSearchParams(window.location.search);
    const isLoadingAnimation = params.has('load');
    
    if (!isLoadingAnimation) {
        // New animation - clear any existing audio
        await clearAudioOnServer();
    }
    
    setupCanvas();
    buildServoLabels();
    setupEventListeners();
    setupAnnotationPopoverEvents();
    setupAudioEventListeners();
    initializeCurves();
    render();
    
    // Start status polling
    setInterval(updateStatus, 500);
    log('Curve editor ready', 'success');
}

async function clearAudioOnServer() {
    try {
        await fetch('/audio/clear', { method: 'POST' });
        audioFile = null;
        audioElement = null;
        updateAudioUI();
    } catch (e) {
        console.log('Could not clear audio:', e);
    }
}

async function loadServoConfigs() {
    try {
        const res = await fetch('/config');
        const data = await res.json();
        CONFIG.numServos = data.numServos;
        CONFIG.servos = data.servos || {};
    } catch (e) {
        console.error('Failed to load config:', e);
    }
}

async function loadCurrentAudio() {
    try {
        const res = await fetch('/audio/current');
        const data = await res.json();
        if (data.has_audio) {
            audioFile = {
                filename: data.filename,
                duration_ms: data.duration_ms || 0,
                waveform: data.waveform || []
            };
            // Update duration to match audio length (only if valid)
            if (data.duration_ms && data.duration_ms > 0) {
                duration = data.duration_ms;
                document.getElementById('duration').value = duration;
            }
            
            // Create audio element for browser preview
            audioElement = new Audio(`/audio/file/${data.filename}`);
            
            updateAudioUI();
        }
    } catch (e) {
        console.error('Failed to load audio:', e);
    }
}

function setupAudioEventListeners() {
    const fileInput = document.getElementById('audioFileInput');
    const container = document.getElementById('audioContainer');
    const clearBtn = document.getElementById('audioClearBtn');
    const offsetInput = document.getElementById('audioOffset');
    
    // Guard against missing elements (if HTML hasn't been updated)
    if (!fileInput || !container || !clearBtn) {
        console.warn('Audio UI elements not found, skipping audio setup');
        return;
    }
    
    // File input change
    fileInput.addEventListener('change', async (e) => {
        const file = e.target.files[0];
        if (file) {
            await uploadAudioFile(file);
        }
        // Reset input so same file can be selected again
        fileInput.value = '';
    });
    
    // Clear button
    clearBtn.addEventListener('click', clearAudio);
    
    // Audio offset change
    if (offsetInput) {
        // Load current offset from server
        loadAudioOffset();
        
        offsetInput.addEventListener('change', async (e) => {
            const offset = parseInt(e.target.value) || 150;
            await setAudioOffset(offset);
        });
    }
    
    // Drag and drop
    container.addEventListener('dragover', (e) => {
        e.preventDefault();
        container.classList.add('dragover');
    });
    
    container.addEventListener('dragleave', () => {
        container.classList.remove('dragover');
    });
    
    container.addEventListener('drop', async (e) => {
        e.preventDefault();
        container.classList.remove('dragover');
        
        const file = e.dataTransfer.files[0];
        if (file) {
            await uploadAudioFile(file);
        }
    });
}

async function loadAudioOffset() {
    try {
        const res = await fetch('/audio/offset');
        const data = await res.json();
        if (data.status === 'ok') {
            const input = document.getElementById('audioOffset');
            if (input) input.value = data.offset_ms;
        }
    } catch (e) {
        console.error('Failed to load audio offset:', e);
    }
}

async function setAudioOffset(offset) {
    try {
        const res = await fetch('/audio/offset', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ offset_ms: offset })
        });
        const data = await res.json();
        if (data.status === 'ok') {
            log(`Audio sync offset: ${data.offset_ms}ms`, 'info');
        }
    } catch (e) {
        log('Failed to set audio offset', 'error');
    }
}

async function uploadAudioFile(file) {
    // Validate file type
    const validTypes = ['audio/wav', 'audio/mpeg', 'audio/mp3', 'audio/ogg', 'audio/flac'];
    const validExts = ['.wav', '.mp3', '.ogg', '.flac'];
    const ext = file.name.toLowerCase().substring(file.name.lastIndexOf('.'));
    
    if (!validTypes.includes(file.type) && !validExts.includes(ext)) {
        log('Invalid audio file type', 'error');
        return;
    }
    
    log('Uploading audio...', 'info');
    
    const formData = new FormData();
    formData.append('file', file);
    
    try {
        const res = await fetch('/audio/upload', {
            method: 'POST',
            body: formData
        });
        
        const data = await res.json();
        
        if (data.status === 'ok') {
            audioFile = {
                filename: data.filename,
                duration_ms: data.duration_ms || 0,
                waveform: data.waveform || []
            };
            
            // Update timeline duration to match audio (only if valid)
            if (data.duration_ms && data.duration_ms > 0) {
                duration = data.duration_ms;
                document.getElementById('duration').value = duration;
            }
            
            // Create audio element for browser preview
            if (audioElement) {
                audioElement.pause();
                audioElement = null;
            }
            audioElement = new Audio(`/audio/file/${data.filename}`);
            
            updateAudioUI();
            render();
            
            log(`Audio loaded: ${formatTime(data.duration_ms)}`, 'success');
        } else {
            log(data.message || 'Upload failed', 'error');
        }
    } catch (e) {
        log('Failed to upload audio', 'error');
        console.error(e);
    }
}

async function clearAudio() {
    try {
        await fetch('/audio/clear', { method: 'POST' });
        
        audioFile = null;
        if (audioElement) {
            audioElement.pause();
            audioElement = null;
        }
        
        updateAudioUI();
        render();
        log('Audio removed', 'info');
    } catch (e) {
        log('Failed to clear audio', 'error');
    }
}

function updateAudioUI() {
    const placeholder = document.getElementById('audioPlaceholder');
    const container = document.getElementById('audioContainer');
    const clearBtn = document.getElementById('audioClearBtn');
    const syncControl = document.getElementById('audioSyncControl');
    
    // Guard against missing elements
    if (!placeholder || !container || !clearBtn) return;
    
    if (audioFile) {
        placeholder.classList.add('hidden');
        container.classList.add('has-audio');
        clearBtn.style.display = 'flex';
        if (syncControl) syncControl.style.display = 'flex';
    } else {
        placeholder.classList.remove('hidden');
        container.classList.remove('has-audio');
        clearBtn.style.display = 'none';
        if (syncControl) syncControl.style.display = 'none';
    }
}

function formatTime(ms) {
    const seconds = Math.floor(ms / 1000);
    const minutes = Math.floor(seconds / 60);
    const secs = seconds % 60;
    const millis = ms % 1000;
    
    if (minutes > 0) {
        return `${minutes}:${secs.toString().padStart(2, '0')}.${Math.floor(millis / 100)}`;
    }
    return `${secs}.${Math.floor(millis / 100)}s`;
}

function getServoConfig(channel) {
    const base = CONFIG.servos[channel] || {};
    return {
        name: base.name || `Servo ${channel}`,
        min_pulse: base.min_pulse || CONFIG.minPulse,
        max_pulse: base.max_pulse || CONFIG.maxPulse,
        center_pulse: base.center_pulse || CONFIG.centerPulse,
        color: base.color || SERVO_COLORS[channel % SERVO_COLORS.length]
    };
}

function getServoColor(channel) {
    const cfg = getServoConfig(channel);
    return cfg.color;
}

function setupCanvas() {
    rulerCanvas = document.getElementById('rulerCanvas');
    rulerCtx = rulerCanvas.getContext('2d');
    audioCanvas = document.getElementById('audioCanvas');
    audioCtx = audioCanvas ? audioCanvas.getContext('2d') : null;
    annotationCanvas = document.getElementById('annotationCanvas');
    annotationCtx = annotationCanvas.getContext('2d');
    tracksCanvas = document.getElementById('tracksCanvas');
    tracksCtx = tracksCanvas.getContext('2d');
    
    resizeCanvas();
    window.addEventListener('resize', () => {
        resizeCanvas();
        render();
    });
}

function resizeCanvas() {
    const dpr = window.devicePixelRatio || 1;
    
    // Ruler canvas
    const rulerContainer = rulerCanvas.parentElement;
    canvasWidth = rulerContainer.clientWidth;
    
    rulerCanvas.width = canvasWidth * dpr;
    rulerCanvas.height = rulerHeight * dpr;
    rulerCanvas.style.width = canvasWidth + 'px';
    rulerCanvas.style.height = rulerHeight + 'px';
    rulerCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    
    // Audio canvas (optional)
    if (audioCanvas && audioCtx) {
        audioCanvas.width = canvasWidth * dpr;
        audioCanvas.height = audioTrackHeight * dpr;
        audioCanvas.style.width = canvasWidth + 'px';
        audioCanvas.style.height = audioTrackHeight + 'px';
        audioCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    
    // Annotation canvas
    annotationCanvas.width = canvasWidth * dpr;
    annotationCanvas.height = annotationHeight * dpr;
    annotationCanvas.style.width = canvasWidth + 'px';
    annotationCanvas.style.height = annotationHeight + 'px';
    annotationCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    
    // Tracks canvas
    const tracksContainer = tracksCanvas.parentElement;
    tracksHeight = CONFIG.numServos * trackHeight;
    
    tracksCanvas.width = canvasWidth * dpr;
    tracksCanvas.height = tracksHeight * dpr;
    tracksCanvas.style.width = canvasWidth + 'px';
    tracksCanvas.style.height = tracksHeight + 'px';
    tracksCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function buildServoLabels() {
    const container = document.getElementById('servoLabels');
    container.innerHTML = '';
    
    for (let i = 0; i < CONFIG.numServos; i++) {
        const cfg = getServoConfig(i);
        const color = cfg.color;
        
        const label = document.createElement('div');
        label.className = `servo-label ${i === activeServo ? 'active' : ''}`;
        label.style.color = color;
        label.title = 'Click to configure';
        label.innerHTML = `
            <div class="servo-label-content">
                <span class="servo-label-text">${cfg.name}</span>
                <div class="servo-color" style="background: ${color}"></div>
            </div>
            <div class="servo-label-range">${cfg.min_pulse} - ${cfg.max_pulse}µs</div>
        `;
        
        // Click opens settings modal
        label.addEventListener('click', () => {
            selectServo(i);
            openServoSettings(i);
        });
        
        container.appendChild(label);
    }
}

function selectServo(index) {
    activeServo = index;
    document.querySelectorAll('.servo-label').forEach((el, i) => {
        el.classList.toggle('active', i === index);
    });
}

async function changeServoCount(delta) {
    const newCount = CONFIG.numServos + delta;
    if (newCount < 1 || newCount > 16) return;
    
    try {
        const res = await fetch('/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ numServos: newCount })
        });
        
        if (!res.ok) {
            const data = await res.json();
            log(data.message || 'Failed to change servo count', 'error');
            return;
        }
        
        const data = await res.json();
        CONFIG.numServos = data.numServos;
        CONFIG.servos = data.servos || {};
        
        // Initialize curves for new servos
        initializeCurves();
        
        // Rebuild UI
        buildServoLabels();
        resizeCanvas();
        render();
        updateServoCountDisplay();
        
        log(`Servo count changed to ${CONFIG.numServos}`, 'success');
    } catch (e) {
        log('Failed to change servo count', 'error');
    }
}

function updateServoCountDisplay() {
    const display = document.getElementById('servoCountDisplay');
    if (display) {
        display.textContent = CONFIG.numServos;
    }
}

function initializeCurves() {
    for (let i = 0; i < CONFIG.numServos; i++) {
        if (!curves[i]) {
            curves[i] = [];
        }
    }
}

function setupEventListeners() {
    tracksCanvas.addEventListener('mousedown', onMouseDown);
    tracksCanvas.addEventListener('mousemove', onMouseMove);
    tracksCanvas.addEventListener('mouseup', onMouseUp);
    tracksCanvas.addEventListener('mouseleave', onMouseUp);
    
    // Annotation canvas events
    annotationCanvas.addEventListener('click', onAnnotationClick);
    annotationCanvas.addEventListener('mousemove', onAnnotationMouseMove);
    annotationCanvas.addEventListener('mouseleave', onAnnotationMouseLeave);
    
    // Keyboard events for deleting selected point
    document.addEventListener('keydown', onKeyDown);
    
    document.getElementById('duration').addEventListener('change', (e) => {
        duration = parseInt(e.target.value);
        render();
    });
}

function onKeyDown(e) {
    // Don't handle keys when typing in an input field
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') {
        return;
    }
    
    if ((e.key === 'Delete' || e.key === 'Backspace')) {
        if (selectedPoint) {
            e.preventDefault();
            deleteSelectedPoint();
        } else if (selectedAnnotation !== null) {
            e.preventDefault();
            deleteSelectedAnnotation();
        }
    }
    if (e.key === 'Escape') {
        selectedPoint = null;
        selectedAnnotation = null;
        render();
    }
}

function deleteSelectedPoint() {
    if (!selectedPoint) return;
    
    const { servoIndex, pointIndex } = selectedPoint;
    if (curves[servoIndex] && curves[servoIndex][pointIndex]) {
        curves[servoIndex].splice(pointIndex, 1);
        selectedPoint = null;
        render();
        log('Point deleted', 'info');
    }
}

// Annotation functions
function onAnnotationClick(e) {
    const rect = annotationCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    let time = xToTime(x);
    
    // Apply grid snap
    const gridSnap = document.getElementById('gridSnap').checked;
    if (gridSnap) {
        time = Math.round(time / 100) * 100;
    }
    time = Math.round(time);
    
    // Check if clicking on existing annotation
    const hitIndex = findAnnotationAtX(x);
    
    if (hitIndex !== null) {
        // Select or edit existing annotation
        if (selectedAnnotation === hitIndex) {
            // Double-click behavior: edit
            editAnnotation(hitIndex, e.clientX, e.clientY);
        } else {
            selectedAnnotation = hitIndex;
            selectedPoint = null;
            render();
        }
    } else {
        // Clear selection before adding new annotation
        selectedAnnotation = null;
        // Show popover to add new annotation
        showAnnotationPopover(e.clientX, e.clientY, time);
    }
}

function showAnnotationPopover(clientX, clientY, time, existingText = '') {
    const popover = document.getElementById('annotationPopover');
    const overlay = document.getElementById('annotationOverlay');
    const input = document.getElementById('annotationInput');
    
    pendingAnnotationTime = time;
    input.value = existingText;
    
    // Keep preview marker visible at the pending position
    annotationHoverX = timeToX(time);
    render();
    
    // Position the popover
    const popoverWidth = 240;
    let left = clientX - popoverWidth / 2;
    
    // Keep within viewport
    if (left < 10) left = 10;
    if (left + popoverWidth > window.innerWidth - 10) {
        left = window.innerWidth - popoverWidth - 10;
    }
    
    popover.style.left = left + 'px';
    popover.style.top = (clientY + 15) + 'px';
    popover.classList.add('open');
    overlay.classList.add('open');
    
    // Focus input
    setTimeout(() => input.focus(), 50);
}

function confirmAnnotation() {
    const input = document.getElementById('annotationInput');
    const text = input.value.trim();
    
    // Check if editing existing annotation
    const isEditing = selectedAnnotation !== null && annotations[selectedAnnotation];
    
    if (text) {
        if (isEditing) {
            annotations[selectedAnnotation].text = text;
            log('Annotation updated', 'success');
        } else {
            // Add new annotation
            annotations.push({ time: pendingAnnotationTime, text });
            annotations.sort((a, b) => a.time - b.time);
            selectedAnnotation = annotations.findIndex(a => a.time === pendingAnnotationTime);
            log('Annotation added', 'success');
        }
    } else if (isEditing) {
        // Empty text while editing = delete
        annotations.splice(selectedAnnotation, 1);
        selectedAnnotation = null;
        log('Annotation deleted', 'info');
    }
    
    closeAnnotationPopover();
    annotationHoverX = null;
    render();
}

function cancelAnnotation() {
    closeAnnotationPopover();
}

function closeAnnotationPopover() {
    const popover = document.getElementById('annotationPopover');
    const overlay = document.getElementById('annotationOverlay');
    popover.classList.remove('open');
    overlay.classList.remove('open');
    pendingAnnotationTime = null;
}

function setupAnnotationPopoverEvents() {
    const input = document.getElementById('annotationInput');
    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            confirmAnnotation();
        } else if (e.key === 'Escape') {
            e.preventDefault();
            cancelAnnotation();
        }
    });
}

function onAnnotationMouseMove(e) {
    const rect = annotationCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const hitIndex = findAnnotationAtX(x);
    
    if (hitIndex !== null) {
        annotationCanvas.style.cursor = 'pointer';
        annotationHoverX = null;
    } else {
        annotationCanvas.style.cursor = 'crosshair';
        
        // Calculate snapped position for preview
        let time = xToTime(x);
        const gridSnap = document.getElementById('gridSnap').checked;
        if (gridSnap) {
            time = Math.round(time / 100) * 100;
        }
        annotationHoverX = timeToX(time);
    }
    
    render();
}

function onAnnotationMouseLeave(e) {
    // Don't clear preview if popover is open
    if (pendingAnnotationTime !== null) return;
    
    annotationHoverX = null;
    render();
}

function findAnnotationAtX(x) {
    for (let i = 0; i < annotations.length; i++) {
        const ax = timeToX(annotations[i].time);
        if (Math.abs(x - ax) <= ANNOTATION_HIT_RADIUS) {
            return i;
        }
    }
    return null;
}

function editAnnotation(index, clientX, clientY) {
    const annotation = annotations[index];
    selectedAnnotation = index;
    showAnnotationPopover(clientX, clientY, annotation.time, annotation.text);
}

function deleteSelectedAnnotation() {
    if (selectedAnnotation === null) return;
    annotations.splice(selectedAnnotation, 1);
    selectedAnnotation = null;
    render();
    log('Annotation deleted', 'info');
}

function findPointAtPos(pos) {
    // Check all servos for a point near the mouse position
    for (let servoIndex = 0; servoIndex < CONFIG.numServos; servoIndex++) {
        const points = curves[servoIndex];
        if (!points) continue;
        
        for (let pointIndex = 0; pointIndex < points.length; pointIndex++) {
            const p = points[pointIndex];
            const px = timeToX(p.time);
            const py = pulseToY(p.pulse, servoIndex);
            
            const dist = Math.sqrt((pos.x - px) ** 2 + (pos.y - py) ** 2);
            if (dist <= POINT_HIT_RADIUS) {
                return { servoIndex, pointIndex };
            }
        }
    }
    return null;
}

function getMousePos(e) {
    const rect = tracksCanvas.getBoundingClientRect();
    return {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top
    };
}

function getServoAtY(y) {
    // Tracks canvas starts at y=0, no ruler offset needed
    if (y < 0) return -1;
    return Math.floor(y / trackHeight);
}

function xToTime(x) {
    return (x / canvasWidth) * duration;
}

function timeToX(time) {
    return (time / duration) * canvasWidth;
}

function yToPulse(y, servoIndex) {
    const cfg = getServoConfig(servoIndex);
    const trackTop = servoIndex * trackHeight;
    const padding = 10;
    
    const normalizedY = (y - trackTop - padding) / (trackHeight - padding * 2);
    const pulse = cfg.max_pulse - normalizedY * (cfg.max_pulse - cfg.min_pulse);
    
    return Math.round(Math.max(cfg.min_pulse, Math.min(cfg.max_pulse, pulse)));
}

function pulseToY(pulse, servoIndex) {
    const cfg = getServoConfig(servoIndex);
    const trackTop = servoIndex * trackHeight;
    const padding = 10;
    
    const normalized = (cfg.max_pulse - pulse) / (cfg.max_pulse - cfg.min_pulse);
    return trackTop + padding + normalized * (trackHeight - padding * 2);
}

function onMouseDown(e) {
    const pos = getMousePos(e);
    
    // Deselect annotation when clicking on tracks
    selectedAnnotation = null;
    
    // First, check if clicking on an existing point
    const hitPoint = findPointAtPos(pos);
    
    if (hitPoint) {
        // Select and start dragging the point
        selectedPoint = hitPoint;
        isDragging = true;
        isDrawing = false;
        activeServo = hitPoint.servoIndex;
        selectServo(hitPoint.servoIndex);
        
        // Live preview selected point
        const point = curves[hitPoint.servoIndex][hitPoint.pointIndex];
        if (point) {
            sendLivePreview(hitPoint.servoIndex, point.pulse);
        }
        
        render();
        return;
    }
    
    // Clicking in empty space - deselect any selected point
    selectedPoint = null;
    
    const servoIndex = getServoAtY(pos.y);
    
    if (servoIndex >= 0 && servoIndex < CONFIG.numServos) {
        activeServo = servoIndex;
        selectServo(servoIndex);
        isDrawing = true;
        isDragging = false;
        
        // Add new point
        const time = xToTime(pos.x);
        const pulse = yToPulse(pos.y, servoIndex);
        
        const gridSnap = document.getElementById('gridSnap').checked;
        const snapTime = gridSnap ? Math.round(time / 100) * 100 : time;
        
        // Remove points that are close in time
        curves[servoIndex] = curves[servoIndex].filter(p => Math.abs(p.time - snapTime) > 50);
        curves[servoIndex].push({ time: snapTime, pulse });
        curves[servoIndex].sort((a, b) => a.time - b.time);
        
        // Select the newly added point
        const newPointIndex = curves[servoIndex].findIndex(p => p.time === snapTime);
        if (newPointIndex >= 0) {
            selectedPoint = { servoIndex, pointIndex: newPointIndex };
        }
        
        render();
    }
}

function onMouseMove(e) {
    const pos = getMousePos(e);
    const servoIndex = getServoAtY(pos.y);
    
    // Update cursor based on hover state
    const hitPoint = findPointAtPos(pos);
    tracksCanvas.style.cursor = hitPoint ? 'grab' : 'crosshair';
    if (isDragging) tracksCanvas.style.cursor = 'grabbing';
    
    // Update mouse info
    if (servoIndex >= 0 && servoIndex < CONFIG.numServos) {
        const time = Math.round(xToTime(pos.x));
        const pulse = yToPulse(pos.y, servoIndex);
        const cfg = getServoConfig(servoIndex);
        document.getElementById('mouseInfo').textContent = 
            `${cfg.name || `Servo ${servoIndex}`}: ${pulse}µs @ ${time}ms`;
    } else {
        document.getElementById('mouseInfo').textContent = '-';
    }
    
    // Handle dragging a selected point
    if (isDragging && selectedPoint) {
        const { servoIndex: dragServo, pointIndex } = selectedPoint;
        
        // Clamp to the servo's track (no ruler offset in tracks canvas)
        const trackTop = dragServo * trackHeight;
        const trackBottom = trackTop + trackHeight;
        const clampedY = Math.max(trackTop + 10, Math.min(trackBottom - 10, pos.y));
        
        let time = xToTime(Math.max(0, Math.min(canvasWidth, pos.x)));
        const pulse = yToPulse(clampedY, dragServo);
        
        const gridSnap = document.getElementById('gridSnap').checked;
        if (gridSnap) {
            time = Math.round(time / 100) * 100;
        }
        time = Math.max(0, Math.min(duration, time));
        
        // Update the point
        curves[dragServo][pointIndex] = { time, pulse };
        
        // Re-sort and update selected index
        curves[dragServo].sort((a, b) => a.time - b.time);
        const newIndex = curves[dragServo].findIndex(p => p.time === time && p.pulse === pulse);
        if (newIndex >= 0) {
            selectedPoint.pointIndex = newIndex;
        }
        
        // Live preview while dragging
        sendLivePreview(dragServo, pulse);
        
        render();
        return;
    }
    
    if (!isDrawing) return;
    
    // Drawing new points (no ruler offset in tracks canvas)
    const trackTop = activeServo * trackHeight;
    const trackBottom = trackTop + trackHeight;
    const clampedY = Math.max(trackTop + 10, Math.min(trackBottom - 10, pos.y));
    
    const time = xToTime(pos.x);
    const pulse = yToPulse(clampedY, activeServo);
    
    const gridSnap = document.getElementById('gridSnap').checked;
    const snapTime = gridSnap ? Math.round(time / 100) * 100 : time;
    
    // Remove nearby points and add new one
    curves[activeServo] = curves[activeServo].filter(p => Math.abs(p.time - snapTime) > 30);
    curves[activeServo].push({ time: snapTime, pulse });
    curves[activeServo].sort((a, b) => a.time - b.time);
    
    // Live preview while drawing
    sendLivePreview(activeServo, pulse);
    
    render();
}

function onMouseUp(e) {
    isDrawing = false;
    isDragging = false;
    tracksCanvas.style.cursor = 'crosshair';
}

function render() {
    // Clear all canvases
    rulerCtx.clearRect(0, 0, canvasWidth, rulerHeight);
    if (audioCtx) {
        audioCtx.clearRect(0, 0, canvasWidth, audioTrackHeight);
    }
    annotationCtx.clearRect(0, 0, canvasWidth, annotationHeight);
    tracksCtx.clearRect(0, 0, canvasWidth, tracksHeight);
    
    // Draw ruler on ruler canvas
    drawRuler();
    
    // Draw audio waveform (if audio track exists)
    if (audioCtx) {
        drawAudioWaveform();
    }
    
    // Draw annotation track
    drawAnnotations();
    
    // Draw tracks on tracks canvas
    for (let i = 0; i < CONFIG.numServos; i++) {
        drawTrack(i);
    }
    
    // Draw vertical time grid lines on tracks canvas
    drawTimeMarkers();
    
    // Draw annotation lines through tracks
    drawAnnotationLines();
    
    // Draw curves on tracks canvas
    for (let i = 0; i < CONFIG.numServos; i++) {
        drawCurve(i);
    }
    
    // Update selection hint
    updateSelectionHint();
}

function updateSelectionHint() {
    const hint = document.getElementById('selectionHint');
    if (selectedPoint) {
        hint.textContent = 'Press Delete to remove point, Esc to deselect';
    } else if (selectedAnnotation !== null) {
        hint.textContent = 'Click again to edit, Delete to remove, Esc to deselect';
    } else {
        hint.textContent = '';
    }
}

function drawRuler() {
    const ctx = rulerCtx;
    
    // Ruler background
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, canvasWidth, rulerHeight);
    
    // Bottom border
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.2)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, rulerHeight);
    ctx.lineTo(canvasWidth, rulerHeight);
    ctx.stroke();
    
    // Calculate appropriate tick intervals based on available space
    const pixelsPer100ms = (100 / duration) * canvasWidth;
    const pixelsPer500ms = (500 / duration) * canvasWidth;
    const pixelsPer1000ms = (1000 / duration) * canvasWidth;
    
    // Determine step sizes based on what fits
    let minorStep, majorStep, labelStep;
    
    if (pixelsPer100ms >= 8) {
        // Show 100ms ticks
        minorStep = 100;
        majorStep = 500;
        labelStep = 1000;
    } else if (pixelsPer500ms >= 15) {
        // Show half-second ticks
        minorStep = 500;
        majorStep = 1000;
        labelStep = 1000;
    } else if (pixelsPer1000ms >= 30) {
        // Show second ticks
        minorStep = 1000;
        majorStep = 1000;
        labelStep = 1000;
    } else {
        // Show 2-second ticks for long durations
        minorStep = 1000;
        majorStep = 2000;
        labelStep = 2000;
    }
    
    ctx.font = '11px "Inter"';
    ctx.textAlign = 'center';
    
    for (let t = 0; t <= duration; t += minorStep) {
        const x = timeToX(t);
        const isLabel = t % labelStep === 0;
        
        // Determine tick height: taller for labels, same height for all others
        const tickHeight = isLabel ? 12 : 6;
        
        // Tick mark color: brighter for labels
        ctx.strokeStyle = isLabel ? 'rgba(255, 255, 255, 0.5)' : 'rgba(255, 255, 255, 0.15)';
        
        ctx.beginPath();
        ctx.moveTo(x, rulerHeight);
        ctx.lineTo(x, rulerHeight - tickHeight);
        ctx.stroke();
        
        // Time label - only show for whole seconds and 0.5s intervals
        const isWholeSecond = t % 1000 === 0;
        const isHalfSecond = t % 500 === 0 && !isWholeSecond;
        
        if (isWholeSecond) {
            // Whole second labels - prominent
            ctx.fillStyle = 'rgba(255, 255, 255, 0.7)';
            ctx.font = '11px "Inter"';
            const label = (t / 1000).toFixed(0) + 's';
            
            // Adjust alignment for edge labels so they don't get cut off
            if (t === 0) {
                ctx.textAlign = 'left';
                ctx.fillText(label, x + 3, 22);
            } else if (t === duration) {
                ctx.textAlign = 'right';
                ctx.fillText(label, x - 3, 22);
            } else {
                ctx.textAlign = 'center';
                ctx.fillText(label, x, 22);
            }
        } else if (isHalfSecond && pixelsPer500ms >= 30) {
            // Half-second labels - dimmer
            ctx.fillStyle = 'rgba(255, 255, 255, 0.35)';
            ctx.font = '9px "Inter"';
            ctx.textAlign = 'center';
            
            const label = (t / 1000).toFixed(1);
            ctx.fillText(label, x, 22);
        }
    }
    
    // Reset text align and font
    ctx.textAlign = 'center';
    ctx.font = '11px "Inter"';
}

function drawAudioWaveform() {
    if (!audioCtx) return;
    
    const ctx = audioCtx;
    
    // Background
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, canvasWidth, audioTrackHeight);
    
    // Draw time grid lines (same as tracks)
    const pixelsPer100ms = (100 / duration) * canvasWidth;
    const pixelsPer500ms = (500 / duration) * canvasWidth;
    
    let step;
    if (pixelsPer100ms >= 10) {
        step = 100;
    } else if (pixelsPer500ms >= 20) {
        step = 500;
    } else {
        step = 1000;
    }
    
    for (let t = 0; t <= duration; t += step) {
        if (t === 0) continue;
        
        const x = timeToX(t);
        let opacity;
        if (t % 1000 === 0) {
            opacity = 0.18;
        } else if (t % 500 === 0) {
            opacity = 0.10;
        } else {
            opacity = 0.04;
        }
        
        ctx.strokeStyle = `rgba(255, 255, 255, ${opacity})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, audioTrackHeight);
        ctx.stroke();
    }
    
    // Draw waveform if we have audio
    if (audioFile && audioFile.waveform && audioFile.waveform.length > 0) {
        const waveform = audioFile.waveform;
        const centerY = audioTrackHeight / 2;
        const maxAmp = (audioTrackHeight / 2) - 4;  // Leave padding
        
        // Draw waveform bars
        const barWidth = canvasWidth / waveform.length;
        
        ctx.fillStyle = 'rgba(0, 171, 222, 0.6)';
        
        for (let i = 0; i < waveform.length; i++) {
            const x = i * barWidth;
            const amp = waveform[i] * maxAmp;
            
            // Draw symmetric bar
            ctx.fillRect(x, centerY - amp, Math.max(1, barWidth - 1), amp * 2);
        }
        
        // Draw center line
        ctx.strokeStyle = 'rgba(0, 171, 222, 0.3)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, centerY);
        ctx.lineTo(canvasWidth, centerY);
        ctx.stroke();
        
        // Draw audio filename
        ctx.fillStyle = 'rgba(0, 171, 222, 0.8)';
        ctx.font = '10px "Inter"';
        ctx.textAlign = 'left';
        ctx.fillText(audioFile.filename, 5, 12);
        
        // Draw duration
        ctx.textAlign = 'right';
        ctx.fillText(formatTime(audioFile.duration_ms), canvasWidth - 5, 12);
    }
    
    // Bottom border
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, audioTrackHeight - 0.5);
    ctx.lineTo(canvasWidth, audioTrackHeight - 0.5);
    ctx.stroke();
}

function drawAnnotations() {
    const ctx = annotationCtx;
    
    // Background
    ctx.fillStyle = '#0a0a0a';
    ctx.fillRect(0, 0, canvasWidth, annotationHeight);
    
    // Draw time grid lines (same as tracks)
    const pixelsPer100ms = (100 / duration) * canvasWidth;
    const pixelsPer500ms = (500 / duration) * canvasWidth;
    
    let step;
    if (pixelsPer100ms >= 10) {
        step = 100;
    } else if (pixelsPer500ms >= 20) {
        step = 500;
    } else {
        step = 1000;
    }
    
    for (let t = 0; t <= duration; t += step) {
        if (t === 0) continue;
        
        const x = timeToX(t);
        let opacity;
        if (t % 1000 === 0) {
            opacity = 0.18;
        } else if (t % 500 === 0) {
            opacity = 0.10;
        } else {
            opacity = 0.04;
        }
        
        ctx.strokeStyle = `rgba(255, 255, 255, ${opacity})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, annotationHeight);
        ctx.stroke();
    }
    
    // Bottom border
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, annotationHeight - 0.5);
    ctx.lineTo(canvasWidth, annotationHeight - 0.5);
    ctx.stroke();
    
    // Draw hover preview marker
    if (annotationHoverX !== null) {
        ctx.fillStyle = 'rgba(255, 107, 53, 0.4)';
        ctx.beginPath();
        ctx.moveTo(annotationHoverX, annotationHeight - 2);
        ctx.lineTo(annotationHoverX - 6, annotationHeight - 12);
        ctx.lineTo(annotationHoverX + 6, annotationHeight - 12);
        ctx.closePath();
        ctx.fill();
        
        // Preview line
        ctx.strokeStyle = 'rgba(255, 107, 53, 0.3)';
        ctx.setLineDash([2, 2]);
        ctx.beginPath();
        ctx.moveTo(annotationHoverX, annotationHeight - 12);
        ctx.lineTo(annotationHoverX, 0);
        ctx.stroke();
        ctx.setLineDash([]);
    }
    
    // Draw each annotation marker
    annotations.forEach((annotation, i) => {
        const x = timeToX(annotation.time);
        const isSelected = selectedAnnotation === i;
        
        // Marker triangle
        ctx.fillStyle = isSelected ? '#fbbf24' : '#ff6b35';
        ctx.beginPath();
        ctx.moveTo(x, annotationHeight - 2);
        ctx.lineTo(x - 6, annotationHeight - 12);
        ctx.lineTo(x + 6, annotationHeight - 12);
        ctx.closePath();
        ctx.fill();
        
        // Text label
        ctx.fillStyle = isSelected ? '#fbbf24' : 'rgba(255, 255, 255, 0.8)';
        ctx.font = '9px "Inter"';
        ctx.textAlign = 'center';
        
        // Truncate text if too long
        let displayText = annotation.text;
        if (displayText.length > 12) {
            displayText = displayText.substring(0, 11) + '…';
        }
        
        ctx.fillText(displayText, x, 10);
    });
}

function drawAnnotationLines() {
    const ctx = tracksCtx;
    
    // Draw hover preview line through tracks
    if (annotationHoverX !== null) {
        ctx.strokeStyle = 'rgba(255, 107, 53, 0.15)';
        ctx.lineWidth = 1;
        ctx.setLineDash([2, 2]);
        
        ctx.beginPath();
        ctx.moveTo(annotationHoverX, 0);
        ctx.lineTo(annotationHoverX, tracksHeight);
        ctx.stroke();
        
        ctx.setLineDash([]);
    }
    
    // Draw vertical lines through all tracks for each annotation
    annotations.forEach((annotation, i) => {
        const x = timeToX(annotation.time);
        const isSelected = selectedAnnotation === i;
        
        ctx.strokeStyle = isSelected ? 'rgba(251, 191, 36, 0.5)' : 'rgba(255, 107, 53, 0.3)';
        ctx.lineWidth = isSelected ? 2 : 1;
        ctx.setLineDash([4, 4]);
        
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, tracksHeight);
        ctx.stroke();
        
        ctx.setLineDash([]);
    });
}

function drawTrack(servoIndex) {
    const ctx = tracksCtx;
    const trackTop = servoIndex * trackHeight;
    const cfg = getServoConfig(servoIndex);
    const color = cfg.color;
    
    // Background
    ctx.fillStyle = servoIndex === activeServo ? 'rgba(255, 255, 255, 0.03)' : 'transparent';
    ctx.fillRect(0, trackTop, canvasWidth, trackHeight);
    
    // Horizontal grid lines (pulse values)
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.lineWidth = 1;
    
    const pulseSteps = [cfg.min_pulse, cfg.center_pulse, cfg.max_pulse];
    pulseSteps.forEach(pulse => {
        const y = pulseToY(pulse, servoIndex);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvasWidth, y);
        ctx.stroke();
    });
    
    // Center line (more visible)
    const centerY = pulseToY(cfg.center_pulse, servoIndex);
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(0, centerY);
    ctx.lineTo(canvasWidth, centerY);
    ctx.stroke();
    ctx.setLineDash([]);
    
    // Track separator
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.1)';
    ctx.beginPath();
    ctx.moveTo(0, trackTop + trackHeight);
    ctx.lineTo(canvasWidth, trackTop + trackHeight);
    ctx.stroke();
    ctx.lineWidth = 1;
    
    // Pulse labels
    ctx.fillStyle = 'rgba(255, 255, 255, 0.3)';
    ctx.font = '10px "Inter"';
    ctx.textAlign = 'left';
    ctx.fillText(cfg.max_pulse, 5, trackTop + 15);
    ctx.fillText(cfg.min_pulse, 5, trackTop + trackHeight - 5);
}

function drawCurve(servoIndex) {
    const ctx = tracksCtx;
    const points = curves[servoIndex];
    const cfg = getServoConfig(servoIndex);
    const color = getServoColor(servoIndex);
    const isActive = servoIndex === activeServo;
    
    // Draw default center line if no points
    if (!points || points.length === 0) {
        const centerY = pulseToY(cfg.center_pulse, servoIndex);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(0, centerY);
        ctx.lineTo(canvasWidth, centerY);
        ctx.stroke();
        return;
    }
    
    // Draw the curve
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    
    if (points.length === 1) {
        // Single point - draw horizontal line across entire timeline
        const y = pulseToY(points[0].pulse, servoIndex);
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvasWidth, y);
        ctx.stroke();
    } else {
        // Draw curve through points
        ctx.beginPath();
        
        // Start from the beginning
        const firstY = pulseToY(points[0].pulse, servoIndex);
        ctx.moveTo(0, firstY);
        
        for (let i = 0; i < points.length; i++) {
            const x = timeToX(points[i].time);
            const y = pulseToY(points[i].pulse, servoIndex);
            
            if (i === 0) {
                ctx.lineTo(x, y);
            } else {
                // Smooth curve using quadratic bezier
                const prevX = timeToX(points[i - 1].time);
                const prevY = pulseToY(points[i - 1].pulse, servoIndex);
                const cpX = (prevX + x) / 2;
                ctx.quadraticCurveTo(prevX, prevY, cpX, (prevY + y) / 2);
                ctx.quadraticCurveTo(cpX, (prevY + y) / 2, x, y);
            }
        }
        
        // Extend to end
        const lastY = pulseToY(points[points.length - 1].pulse, servoIndex);
        ctx.lineTo(canvasWidth, lastY);
        
        ctx.stroke();
    }
    
    // Draw points
    points.forEach((p, i) => {
        const x = timeToX(p.time);
        const y = pulseToY(p.pulse, servoIndex);
        
        // Check if this point is selected
        const isSelected = selectedPoint && 
                          selectedPoint.servoIndex === servoIndex && 
                          selectedPoint.pointIndex === i;
        
        if (isSelected) {
            // Draw selection ring
            ctx.strokeStyle = '#fff';
            ctx.lineWidth = 3;
            ctx.beginPath();
            ctx.arc(x, y, 10, 0, Math.PI * 2);
            ctx.stroke();
            
            // Inner fill
            ctx.fillStyle = color;
            ctx.beginPath();
            ctx.arc(x, y, 6, 0, Math.PI * 2);
            ctx.fill();
        } else {
            ctx.fillStyle = isActive ? '#fff' : color;
            ctx.beginPath();
            ctx.arc(x, y, isActive ? 5 : 3, 0, Math.PI * 2);
            ctx.fill();
            
            if (isActive) {
                ctx.strokeStyle = color;
                ctx.lineWidth = 2;
                ctx.stroke();
            }
        }
    });
}

function drawTimeMarkers() {
    const ctx = tracksCtx;
    
    // Calculate appropriate step based on available space
    const pixelsPer100ms = (100 / duration) * canvasWidth;
    const pixelsPer500ms = (500 / duration) * canvasWidth;
    
    let step;
    if (pixelsPer100ms >= 10) {
        step = 100;
    } else if (pixelsPer500ms >= 20) {
        step = 500;
    } else {
        step = 1000;
    }
    
    for (let t = 0; t <= duration; t += step) {
        // Skip the line at t=0 to avoid a "Y-axis" appearance
        if (t === 0) continue;
        
        const x = timeToX(t);
        
        // Determine line opacity based on time value
        let opacity;
        if (t % 1000 === 0) {
            opacity = 0.18;
        } else if (t % 500 === 0) {
            opacity = 0.10;
        } else {
            opacity = 0.04;
        }
        
        ctx.strokeStyle = `rgba(255, 255, 255, ${opacity})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, tracksHeight);
        ctx.stroke();
    }
}

function clearAllCurves() {
    for (let i = 0; i < CONFIG.numServos; i++) {
        curves[i] = [];
    }
    annotations = [];
    selectedAnnotation = null;
    render();
    log('All curves and annotations cleared', 'info');
}

function sendLivePreview(channel, pulse) {
    const livePreview = document.getElementById('livePreview').checked;
    if (!livePreview) return;
    
    // Throttle updates
    const now = Date.now();
    if (now - lastLivePreviewTime < LIVE_PREVIEW_THROTTLE) return;
    lastLivePreviewTime = now;
    
    // Send to servo (fire and forget)
    fetch('/servo', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channel, position: pulse })
    }).catch(() => {});
}

function smoothCurves() {
    // Apply simple smoothing to all curves
    for (let servoIndex = 0; servoIndex < CONFIG.numServos; servoIndex++) {
        const points = curves[servoIndex];
        if (points.length < 3) continue;
        
        const smoothed = points.map((p, i) => {
            if (i === 0 || i === points.length - 1) return p;
            
            const prev = points[i - 1];
            const next = points[i + 1];
            return {
                time: p.time,
                pulse: Math.round((prev.pulse + p.pulse + next.pulse) / 3)
            };
        });
        
        curves[servoIndex] = smoothed;
    }
    render();
    log('Curves smoothed', 'success');
}

function generateKeyframes() {
    // Sample the curves at regular intervals to create keyframes
    const keyframes = [];
    const sampleInterval = 50; // ms
    
    for (let t = 0; t <= duration; t += sampleInterval) {
        const servos = {};
        
        for (let i = 0; i < CONFIG.numServos; i++) {
            servos[i] = getValueAtTime(i, t);
        }
        
        keyframes.push({
            servos,
            duration: sampleInterval
        });
    }
    
    return keyframes;
}

function getValueAtTime(servoIndex, time) {
    const points = curves[servoIndex];
    const cfg = getServoConfig(servoIndex);
    
    if (!points || points.length === 0) {
        return cfg.center_pulse;
    }
    
    // Find surrounding points
    let before = null;
    let after = null;
    
    for (const p of points) {
        if (p.time <= time) {
            before = p;
        } else if (!after) {
            after = p;
        }
    }
    
    if (!before && !after) return cfg.center_pulse;
    if (!before) return after.pulse;
    if (!after) return before.pulse;
    
    // Linear interpolation
    const t = (time - before.time) / (after.time - before.time);
    return Math.round(before.pulse + (after.pulse - before.pulse) * t);
}

async function previewAnimation() {
    // If paused, resume
    if (isPaused) {
        resumeAnimation();
        return;
    }
    
    // If already playing, pause
    if (isPlaying) {
        pauseAnimation();
        return;
    }
    
    const keyframes = generateKeyframes();
    
    if (keyframes.length === 0) {
        log('No curves to preview', 'error');
        return;
    }
    
    try {
        const res = await fetch('/play', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyframes })
        });
        
        const data = await res.json();
        if (data.status === 'started') {
            log(audioFile ? 'Playing with audio...' : 'Playing animation...', 'success');
            isPlaying = true;
            isPaused = false;
            pausedElapsed = 0;
            updatePlayButton();
            startPlayhead();
            
            // Start browser audio playback for preview
            startBrowserAudio();
        } else {
            log(data.message || 'Failed to start', 'error');
        }
    } catch (e) {
        log('Failed to play animation', 'error');
    }
}

function startBrowserAudio() {
    if (!audioFile || !audioElement) return;
    
    audioElement.currentTime = 0;
    audioElement.play().catch(e => {
        console.log('Browser audio play failed (user interaction required):', e);
    });
}

function stopBrowserAudio() {
    if (audioElement) {
        audioElement.pause();
        audioElement.currentTime = 0;
    }
}

function pauseBrowserAudio() {
    if (audioElement) {
        audioElement.pause();
    }
}

function resumeBrowserAudio() {
    if (audioElement && audioFile) {
        audioElement.play().catch(() => {});
    }
}

function pauseAnimation() {
    if (!isPlaying || isPaused) return;
    
    // Store elapsed time
    pausedElapsed = performance.now() - playStartTime;
    
    // Stop playhead animation
    if (animationFrame) {
        cancelAnimationFrame(animationFrame);
        animationFrame = null;
    }
    
    isPaused = true;
    updatePlayButton();
    log('Animation paused', 'info');
    
    // Pause browser audio
    pauseBrowserAudio();
    
    // Stop servos on backend
    fetch('/stop', { method: 'POST' });
}

function resumeAnimation() {
    if (!isPaused) return;
    
    // Resume from paused position
    isPaused = false;
    updatePlayButton();
    log('Animation resumed', 'info');
    
    // Resume browser audio
    resumeBrowserAudio();
    
    // Restart playhead from paused position
    const playhead = document.getElementById('playhead');
    playStartTime = performance.now() - pausedElapsed;
    
    function animate() {
        if (isPaused) return;
        
        const elapsed = performance.now() - playStartTime;
        const x = timeToX(elapsed);
        
        if (elapsed >= duration) {
            playhead.style.display = 'none';
            isPlaying = false;
            isPaused = false;
            pausedElapsed = 0;
            updatePlayButton();
            stopBrowserAudio();
            return;
        }
        
        playhead.style.left = x + 'px';
        animationFrame = requestAnimationFrame(animate);
    }
    
    animate();
    
    // Resume backend animation (regenerate keyframes from current position)
    const keyframes = generateKeyframes();
    if (keyframes.length > 0) {
        fetch('/play', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keyframes })
        });
    }
}

function startPlayhead() {
    const playhead = document.getElementById('playhead');
    playhead.style.display = 'block';
    playhead.style.left = '0px';
    playStartTime = performance.now();
    
    function animate() {
        if (isPaused) return;
        
        const elapsed = performance.now() - playStartTime;
        const x = timeToX(elapsed);
        
        if (elapsed >= duration) {
            playhead.style.display = 'none';
            isPlaying = false;
            isPaused = false;
            pausedElapsed = 0;
            updatePlayButton();
            stopBrowserAudio();
            return;
        }
        
        playhead.style.left = x + 'px';
        animationFrame = requestAnimationFrame(animate);
    }
    
    animate();
}

function updatePlayButton() {
    const btn = document.getElementById('playPauseBtn');
    if (!btn) return;
    
    const icon = btn.querySelector('.material-icons');
    if (isPlaying && !isPaused) {
        icon.textContent = 'pause';
        btn.title = 'Pause';
    } else {
        icon.textContent = 'play_arrow';
        btn.title = 'Play';
    }
}

async function stopAnimation() {
    if (animationFrame) {
        cancelAnimationFrame(animationFrame);
        animationFrame = null;
    }
    document.getElementById('playhead').style.display = 'none';
    
    isPlaying = false;
    isPaused = false;
    pausedElapsed = 0;
    updatePlayButton();
    
    // Stop browser audio
    stopBrowserAudio();
    
    try {
        await fetch('/stop', { method: 'POST' });
        log('Animation stopped', 'info');
    } catch (e) {
        log('Failed to stop', 'error');
    }
}

async function saveConfig() {
    try {
        const res = await fetch('/config/save', { method: 'POST' });
        const data = await res.json();
        log(data.status === 'ok' ? 'Config saved' : data.message, data.status === 'ok' ? 'success' : 'error');
    } catch (e) {
        log('Failed to save config', 'error');
    }
}

// Servo settings modal
function openServoSettings(channel) {
    const cfg = getServoConfig(channel);
    
    document.getElementById('modalChannel').value = channel;
    document.getElementById('modalTitle').textContent = `SERVO ${channel} SETTINGS`;
    document.getElementById('servoName').value = cfg.name || '';
    document.getElementById('servoMin').value = cfg.min_pulse;
    document.getElementById('servoMax').value = cfg.max_pulse;
    document.getElementById('servoCenter').value = cfg.center_pulse;
    
    const colorInput = document.getElementById('servoColor');
    colorInput.value = cfg.color;
    updateColorHex(cfg.color);
    
    document.getElementById('servoModal').classList.add('open');
}

function updateColorHex(color) {
    document.getElementById('colorHex').textContent = color.toUpperCase();
}

// Set up color picker event listener
document.addEventListener('DOMContentLoaded', () => {
    const colorInput = document.getElementById('servoColor');
    if (colorInput) {
        colorInput.addEventListener('input', (e) => {
            updateColorHex(e.target.value);
        });
    }
});

function closeServoModal() {
    document.getElementById('servoModal').classList.remove('open');
}

async function saveServoSettings() {
    const channel = parseInt(document.getElementById('modalChannel').value);
    const settings = {
        name: document.getElementById('servoName').value,
        min_pulse: parseInt(document.getElementById('servoMin').value),
        max_pulse: parseInt(document.getElementById('servoMax').value),
        center_pulse: parseInt(document.getElementById('servoCenter').value),
        color: document.getElementById('servoColor').value
    };
    
    // Validate
    if (settings.min_pulse >= settings.max_pulse) {
        log('Min must be less than max', 'error');
        return;
    }
    if (settings.center_pulse < settings.min_pulse || settings.center_pulse > settings.max_pulse) {
        log('Center must be between min and max', 'error');
        return;
    }
    
    try {
        const res = await fetch(`/servo/${channel}/config`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(settings)
        });
        
        if (!res.ok) {
            const data = await res.json();
            log(data.message || 'Failed to save settings', 'error');
            return;
        }
        
        const data = await res.json();
        CONFIG.servos[channel] = {
            name: data.name,
            min_pulse: data.min_pulse,
            max_pulse: data.max_pulse,
            center_pulse: data.center_pulse,
            color: data.color
        };
        
        closeServoModal();
        buildServoLabels();
        resizeCanvas();
        render();
        log(`Servo ${channel} settings updated`, 'success');
    } catch (e) {
        log('Failed to save settings', 'error');
    }
}

async function updateStatus() {
    try {
        const res = await fetch('/status');
        const data = await res.json();
        const dot = document.getElementById('statusDot');
        const text = document.getElementById('statusText');
        
        if (data.animating) {
            dot.classList.add('busy');
            text.textContent = 'Playing...';
        } else {
            dot.classList.remove('busy');
            text.textContent = 'Ready';
            
            // Stop playhead if animation finished
            if (animationFrame || isPlaying) {
                if (animationFrame) {
                    cancelAnimationFrame(animationFrame);
                    animationFrame = null;
                }
                document.getElementById('playhead').style.display = 'none';
                isPlaying = false;
                isPaused = false;
                pausedElapsed = 0;
                updatePlayButton();
            }
        }
    } catch (e) {}
}

function log(message, type = 'info') {
    const logEl = document.getElementById('log');
    logEl.innerHTML = `<span class="log-entry ${type}">${message}</span>`;
}

// Animation save/load
let currentAnimationName = '';

function openSaveModal() {
    document.getElementById('animationName').value = currentAnimationName;
    document.getElementById('saveModal').classList.add('open');
    setTimeout(() => document.getElementById('animationName').focus(), 50);
}

function closeSaveModal() {
    document.getElementById('saveModal').classList.remove('open');
}

async function saveAnimation() {
    const name = document.getElementById('animationName').value.trim();
    
    if (!name) {
        log('Please enter a name', 'error');
        return;
    }
    
    // Convert curves to saveable format (string keys for JSON)
    const curvesData = {};
    for (const [key, value] of Object.entries(curves)) {
        curvesData[key] = value;
    }
    
    try {
        const res = await fetch('/animations/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name: name,
                duration_ms: duration,
                curves: curvesData,
                annotations: annotations,
            })
        });
        
        const data = await res.json();
        
        if (data.status === 'ok') {
            currentAnimationName = name;
            closeSaveModal();
            log(`Saved: ${name}`, 'success');
        } else {
            log(data.message || 'Failed to save', 'error');
        }
    } catch (e) {
        log('Failed to save animation', 'error');
        console.error(e);
    }
}

async function loadAnimationFromUrl() {
    // Check if URL has a load parameter
    const params = new URLSearchParams(window.location.search);
    const filename = params.get('load');
    
    if (!filename) return;
    
    try {
        const res = await fetch(`/animations/load/${encodeURIComponent(filename)}`);
        const data = await res.json();
        
        if (data.status !== 'ok') {
            log('Animation not found', 'error');
            return;
        }
        
        const anim = data.animation;
        
        // Load the animation data
        currentAnimationName = anim.name;
        duration = anim.duration_ms;
        document.getElementById('duration').value = duration;
        
        // Load curves (convert string keys to int)
        curves = {};
        for (const [key, value] of Object.entries(anim.curves || {})) {
            curves[parseInt(key)] = value;
        }
        
        // Load annotations
        annotations = anim.annotations || [];
        
        // If animation has audio, set it as current and load
        if (anim.audio_file) {
            try {
                // Set the animation's audio as current
                await fetch('/audio/select', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ filename: anim.audio_file })
                });
                
                // Now fetch the audio info
                const audioRes = await fetch('/audio/current');
                const audioData = await audioRes.json();
                if (audioData.has_audio) {
                    audioFile = {
                        filename: audioData.filename,
                        duration_ms: audioData.duration_ms || 0,
                        waveform: audioData.waveform || []
                    };
                    audioElement = new Audio(`/audio/file/${audioData.filename}`);
                    updateAudioUI();
                }
            } catch (e) {
                console.log('Could not load audio:', e);
            }
        }
        
        // Update UI
        resizeCanvas();
        render();
        log(`Loaded: ${anim.name}`, 'success');
        
        // Clean URL
        window.history.replaceState({}, '', '/editor');
        
    } catch (e) {
        log('Failed to load animation', 'error');
        console.error(e);
    }
}

// Handle Enter key in save modal
document.addEventListener('DOMContentLoaded', () => {
    const nameInput = document.getElementById('animationName');
    if (nameInput) {
        nameInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveAnimation();
            } else if (e.key === 'Escape') {
                closeSaveModal();
            }
        });
    }
});

// Start
init();

// Load animation from URL after init
loadAnimationFromUrl();

