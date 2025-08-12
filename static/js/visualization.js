// Visualization for Satellite Tracking
document.addEventListener('DOMContentLoaded', function() {
    // Scene constants
    const SKY_RADIUS = 100;
    const GROUND_RADIUS = 50;
    const OBSERVER_HEIGHT = 0.5;
    
    // Scene variables
    let scene, camera, renderer, controls;
    let skyDome, groundPlane, observerMarker;
    let satelliteObject, satelliteTrail, currentTrailPoint = 0;
    let satellite = {
        name: null,
        trajectory: [],
        currentIndex: 0
    };
    
    // Create the visualization
    initVisualization();
    animateVisualization();
    
    // Initialize the 3D visualization
    function initVisualization() {
        const container = document.getElementById('visualization-canvas');
        
        // Create scene
        scene = new THREE.Scene();
        scene.background = new THREE.Color(0x000000);
        
        // Create camera
        camera = new THREE.PerspectiveCamera(60, container.clientWidth / container.clientHeight, 0.1, 1000);
        camera.position.set(0, 20, 50);
        camera.lookAt(0, 0, 0);
        
        // Create renderer
        renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        renderer.setSize(container.clientWidth, container.clientHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        container.appendChild(renderer.domElement);
        
        // Create controls
        controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.minDistance = 5;
        controls.maxDistance = 100;
        controls.maxPolarAngle = Math.PI / 2;
        
        // Create lighting
        const ambientLight = new THREE.AmbientLight(0x404040, 1);
        scene.add(ambientLight);
        
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.5);
        directionalLight.position.set(1, 1, 1);
        scene.add(directionalLight);
        
        // Create sky dome
        createSkyDome();
        
        // Create ground plane
        createGround();
        
        // Create cardinal directions
        createCardinalDirections();
        
        // Create observer marker (telescope position)
        createObserver();
        
        // Create satellite object and trail
        createSatellite();
        
        // Handle window resize
        window.addEventListener('resize', onWindowResize);
    }
    
    // Create the sky dome with stars
    function createSkyDome() {
        // Create the dome geometry
        const skyGeometry = new THREE.SphereGeometry(SKY_RADIUS, 32, 32);
        // Invert the geometry so we can see it from inside
        skyGeometry.scale(-1, 1, 1);
        
        // Create material with star field
        const skyMaterial = new THREE.MeshBasicMaterial({
            color: 0x000010,
            side: THREE.BackSide,
            transparent: true,
            opacity: 0.8
        });
        
        skyDome = new THREE.Mesh(skyGeometry, skyMaterial);
        scene.add(skyDome);
        
        // Add stars
        addStars();
        
        // Add azimuth markings
        addAzimuthMarkings();
        
        // Add elevation markings
        addElevationMarkings();
    }
    
    // Add random stars to the scene
    function addStars() {
        const starsGeometry = new THREE.BufferGeometry();
        const starsMaterial = new THREE.PointsMaterial({
            color: 0xffffff,
            size: 0.5,
            transparent: true,
            opacity: 0.8,
            sizeAttenuation: false
        });
        
        const starsVertices = [];
        const starsCount = 1000;
        
        for (let i = 0; i < starsCount; i++) {
            // Generate random positions on the sphere
            const theta = Math.random() * Math.PI * 2;
            const phi = Math.acos(2 * Math.random() - 1);
            const radius = SKY_RADIUS * 0.99; // Slightly inside the dome
            
            const x = radius * Math.sin(phi) * Math.cos(theta);
            const y = radius * Math.sin(phi) * Math.sin(theta);
            const z = radius * Math.cos(phi);
            
            starsVertices.push(x, y, z);
        }
        
        starsGeometry.setAttribute('position', new THREE.Float32BufferAttribute(starsVertices, 3));
        const stars = new THREE.Points(starsGeometry, starsMaterial);
        scene.add(stars);
    }
    
    // Add azimuth markings (compass directions)
    function addAzimuthMarkings() {
        // Create a circle to mark the horizon
        const horizonGeometry = new THREE.RingGeometry(GROUND_RADIUS - 0.2, GROUND_RADIUS, 64);
        const horizonMaterial = new THREE.MeshBasicMaterial({
            color: 0x3498db,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.3
        });
        const horizon = new THREE.Mesh(horizonGeometry, horizonMaterial);
        horizon.rotation.x = Math.PI / 2;
        horizon.position.y = 0.01; // Slightly above ground to avoid z-fighting
        scene.add(horizon);
        
        // Add cardinal direction markers
        const directions = [
            { angle: 0, label: 'N' },
            { angle: Math.PI / 2, label: 'E' },
            { angle: Math.PI, label: 'S' },
            { angle: Math.PI * 3 / 2, label: 'W' }
        ];
        
        // Create a group for all markers
        const markersGroup = new THREE.Group();
        scene.add(markersGroup);
        
        directions.forEach(dir => {
            // Position on the horizon circle
            const x = Math.sin(dir.angle) * GROUND_RADIUS;
            const z = Math.cos(dir.angle) * GROUND_RADIUS;
            
            // Create a cylinder as the marker
            const markerGeometry = new THREE.CylinderGeometry(0.2, 0.2, 2, 8);
            const markerMaterial = new THREE.MeshBasicMaterial({ color: 0x3498db });
            const marker = new THREE.Mesh(markerGeometry, markerMaterial);
            marker.position.set(x, 1, z);
            markersGroup.add(marker);
        });
    }
    
    // Add elevation marking rings
    function addElevationMarkings() {
        // Create elevation circles at 30° and 60°
        const elevations = [30, 60];
        
        elevations.forEach(elevation => {
            const angle = (90 - elevation) * Math.PI / 180;
            const radius = Math.sin(angle) * GROUND_RADIUS;
            const height = Math.cos(angle) * GROUND_RADIUS;
            
            const elevCircleGeometry = new THREE.RingGeometry(radius - 0.1, radius, 64);
            const elevCircleMaterial = new THREE.MeshBasicMaterial({
                color: 0x3498db,
                side: THREE.DoubleSide,
                transparent: true,
                opacity: 0.2
            });
            const elevCircle = new THREE.Mesh(elevCircleGeometry, elevCircleMaterial);
            elevCircle.rotation.x = Math.PI / 2;
            elevCircle.position.y = height;
            scene.add(elevCircle);
            
            // Add text label
            const textDiv = document.createElement('div');
            textDiv.className = 'elevation-label';
            textDiv.textContent = `${elevation}°`;
            textDiv.style.position = 'absolute';
            textDiv.style.display = 'none'; // Initially hidden
            document.body.appendChild(textDiv);
        });
    }
    
    // Create the ground plane
    function createGround() {
        const groundGeometry = new THREE.CircleGeometry(GROUND_RADIUS, 64);
        const groundMaterial = new THREE.MeshBasicMaterial({
            color: 0x2c3e50,
            side: THREE.DoubleSide
        });
        groundPlane = new THREE.Mesh(groundGeometry, groundMaterial);
        groundPlane.rotation.x = -Math.PI / 2;
        groundPlane.position.y = 0;
        scene.add(groundPlane);
    }
    
    // Create cardinal direction markers
    function createCardinalDirections() {
        const cardinalDirections = [
            { direction: 'N', angle: 0, color: 0xff0000 },
            { direction: 'E', angle: Math.PI / 2, color: 0x00ff00 },
            { direction: 'S', angle: Math.PI, color: 0xffff00 },
            { direction: 'W', angle: Math.PI * 3 / 2, color: 0x00ffff }
        ];
        
        cardinalDirections.forEach(dir => {
            const x = Math.sin(dir.angle) * (GROUND_RADIUS - 2);
            const z = Math.cos(dir.angle) * (GROUND_RADIUS - 2);
            
            // Create a simple cube marker for each cardinal direction
            const markerGeometry = new THREE.BoxGeometry(1.5, 0.2, 1.5);
            const markerMaterial = new THREE.MeshBasicMaterial({ color: dir.color });
            const marker = new THREE.Mesh(markerGeometry, markerMaterial);
            marker.position.set(x, 0.1, z);
            
            // Add text as HTML overlay instead
            const cardinalLabel = document.createElement('div');
            cardinalLabel.className = 'cardinal-label';
            cardinalLabel.textContent = dir.direction;
            cardinalLabel.style.position = 'absolute';
            cardinalLabel.style.color = '#' + dir.color.toString(16).padStart(6, '0');
            cardinalLabel.style.fontWeight = 'bold';
            cardinalLabel.style.fontSize = '16px';
            document.getElementById('visualization-canvas').appendChild(cardinalLabel);
            
            scene.add(marker);
        });
    }
    
    // Create observer (telescope) marker
    function createObserver() {
        // Create a group for the observer
        observerMarker = new THREE.Group();
        
        // Base pillar
        const baseGeometry = new THREE.CylinderGeometry(0.5, 0.7, 1, 8);
        const baseMaterial = new THREE.MeshBasicMaterial({ color: 0x7f8c8d });
        const base = new THREE.Mesh(baseGeometry, baseMaterial);
        base.position.y = 0.5;
        observerMarker.add(base);
        
        // Telescope body
        const bodyGeometry = new THREE.CylinderGeometry(0.3, 0.3, 1.5, 8);
        const bodyMaterial = new THREE.MeshBasicMaterial({ color: 0x34495e });
        const body = new THREE.Mesh(bodyGeometry, bodyMaterial);
        body.position.y = 1.75;
        body.rotation.x = Math.PI / 4; // Tilted
        observerMarker.add(body);
        
        // Telescope tube
        const tubeGeometry = new THREE.CylinderGeometry(0.2, 0.2, 2, 8);
        const tubeMaterial = new THREE.MeshBasicMaterial({ color: 0x2c3e50 });
        const tube = new THREE.Mesh(tubeGeometry, tubeMaterial);
        tube.position.y = 2.5;
        tube.position.x = 0.5;
        tube.rotation.z = Math.PI / 2; // Horizontal
        observerMarker.add(tube);
        
        observerMarker.position.y = OBSERVER_HEIGHT;
        scene.add(observerMarker);
    }
    
    // Create satellite object and trail
    function createSatellite() {
        // Satellite object
        const satelliteGeometry = new THREE.SphereGeometry(0.5, 16, 16);
        const satelliteMaterial = new THREE.MeshBasicMaterial({
            color: 0xe74c3c,
            emissive: 0xe74c3c,
            emissiveIntensity: 0.5
        });
        satelliteObject = new THREE.Mesh(satelliteGeometry, satelliteMaterial);
        satelliteObject.visible = false; // Hide initially
        scene.add(satelliteObject);
        
        // Satellite trail
        const trailMaterial = new THREE.LineBasicMaterial({
            color: 0xe74c3c,
            linewidth: 2,
            transparent: true,
            opacity: 0.7
        });
        
        const trailGeometry = new THREE.BufferGeometry();
        satelliteTrail = new THREE.Line(trailGeometry, trailMaterial);
        scene.add(satelliteTrail);
    }
    
    // Update satellite position based on trajectory
    function updateSatellite() {
        // Check if we have next satellite pass data from dashboard.js
        if (window.nextSatellitePass) {
            // Only update if satellite has changed or no trajectory exists
            if (satellite.name !== window.nextSatellitePass.satname || !satellite.trajectory.length) {
                // We need to generate a path for visualization
                satellite.name = window.nextSatellitePass.satname;
                satellite.currentIndex = 0;
                
                // Generate mock trajectory points for visualization
                // In a real implementation, you would use the actual trajectory data
                generateMockTrajectory();
                
                // Update satellite info display
                document.getElementById('satellite-name').innerText = satellite.name;
            }
            
            // Update the satellite position and info display if we have trajectory
            if (satellite.trajectory.length > 0) {
                const point = satellite.trajectory[satellite.currentIndex];
                
                // Convert spherical coordinates (azimuth/elevation) to Cartesian
                const position = azElToCartesian(point.azimuth, point.elevation);
                satelliteObject.position.copy(position);
                satelliteObject.visible = true;
                
                // Update info display
                document.getElementById('satellite-azimuth').innerText = point.azimuth.toFixed(1) + '°';
                document.getElementById('satellite-elevation').innerText = point.elevation.toFixed(1) + '°';
                
                // Add point to trail
                updateSatelliteTrail(position);
                
                // Increment index for animation, loop if at end
                satellite.currentIndex = (satellite.currentIndex + 1) % satellite.trajectory.length;
            }
        }
    }
    
    // Generate a mock trajectory for visualization
    function generateMockTrajectory() {
        satellite.trajectory = [];
        
        // Create a mock pass that goes from East to West
        const pathLength = 100;
        const azimuthStart = 90; // Start at East
        const azimuthEnd = 270; // End at West
        const maxElevation = 60; // Maximum elevation in degrees
        
        for (let i = 0; i < pathLength; i++) {
            const progress = i / (pathLength - 1);
            const azimuth = azimuthStart + progress * (azimuthEnd - azimuthStart);
            
            // Elevation increases then decreases (parabolic)
            const elevation = maxElevation * Math.sin(progress * Math.PI);
            
            satellite.trajectory.push({
                azimuth: azimuth,
                elevation: elevation
            });
        }
    }
    
    // Update satellite trail visualization
    function updateSatelliteTrail(newPosition) {
        // Get the current positions
        const positions = satelliteTrail.geometry.attributes.position;
        
        // If positions array doesn't exist yet or is too short, create/resize it
        if (!positions || positions.count < currentTrailPoint + 1) {
            const newPositions = new Float32Array((currentTrailPoint + 1) * 3);
            
            // Copy existing positions if any
            if (positions) {
                for (let i = 0; i < positions.count * 3; i++) {
                    newPositions[i] = positions.array[i];
                }
            }
            
            satelliteTrail.geometry.setAttribute('position', 
                new THREE.BufferAttribute(newPositions, 3));
        }
        
        // Add new position
        positions.array[currentTrailPoint * 3] = newPosition.x;
        positions.array[currentTrailPoint * 3 + 1] = newPosition.y;
        positions.array[currentTrailPoint * 3 + 2] = newPosition.z;
        
        positions.needsUpdate = true;
        satelliteTrail.geometry.setDrawRange(0, currentTrailPoint + 1);
        
        // Increment trail point counter
        currentTrailPoint++;
        
        // Reset trail if it gets too long
        if (currentTrailPoint > 200) {
            currentTrailPoint = 0;
        }
    }
    
    // Convert azimuth and elevation to Cartesian coordinates
    function azElToCartesian(azimuthDeg, elevationDeg) {
        // Convert to radians
        const azimuth = (azimuthDeg * Math.PI) / 180;
        const elevation = (elevationDeg * Math.PI) / 180;
        
        // Calculate position on our dome
        const radius = SKY_RADIUS * 0.9; // Slightly inside the dome
        
        const x = radius * Math.sin(azimuth) * Math.cos(elevation);
        const y = radius * Math.sin(elevation);
        const z = radius * Math.cos(azimuth) * Math.cos(elevation);
        
        return new THREE.Vector3(x, y, z);
    }
    
    // Handle window resize
    function onWindowResize() {
        const container = document.getElementById('visualization-canvas');
        camera.aspect = container.clientWidth / container.clientHeight;
        camera.updateProjectionMatrix();
        renderer.setSize(container.clientWidth, container.clientHeight);
    }
    
    // Animation loop
    function animateVisualization() {
        requestAnimationFrame(animateVisualization);
        
        // Update controls
        controls.update();
        
        // Update satellite position
        updateSatellite();
        
        // Update cardinal direction labels
        updateCardinalLabels();
        
        // Render scene
        renderer.render(scene, camera);
    }
    
    // Update cardinal direction label positions
    function updateCardinalLabels() {
        const cardinalLabels = document.getElementsByClassName('cardinal-label');
        const cardinalDirections = [
            { direction: 'N', angle: 0 },
            { direction: 'E', angle: Math.PI / 2 },
            { direction: 'S', angle: Math.PI },
            { direction: 'W', angle: Math.PI * 3 / 2 }
        ];
        
        for (let i = 0; i < cardinalLabels.length; i++) {
            const dir = cardinalDirections[i];
            const x = Math.sin(dir.angle) * (GROUND_RADIUS - 2);
            const y = 0.1;
            const z = Math.cos(dir.angle) * (GROUND_RADIUS - 2);
            
            // Convert 3D position to screen position
            const position = new THREE.Vector3(x, y, z);
            const vector = position.clone().project(camera);
            
            // Convert to screen coordinates
            const widthHalf = renderer.domElement.width / 2;
            const heightHalf = renderer.domElement.height / 2;
            const screenX = (vector.x * widthHalf) + widthHalf;
            const screenY = -(vector.y * heightHalf) + heightHalf;
            
            // Set position of HTML element
            const label = cardinalLabels[i];
            label.style.left = screenX + 'px';
            label.style.top = screenY + 'px';
            
            // Hide label if behind camera
            label.style.display = vector.z > 1 ? 'none' : 'block';
        }
    }
}); 