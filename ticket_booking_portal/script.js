// Movie data
const movies = [
    {
        title: "Man of Steel",
        description: "Superman after years of protecting earth faces its biggest challenge.",
        poster: "superman.jpg",
        price: 800,
        showtimes: ["10:00 AM", "1:00 PM", "4:00 PM"]
    },
    {
        title: "RoboCop",
        description: "In a futuristic city, a detective hunts a rogue AI that threatens humanity.",
        poster: "robocop.jpg",
        price: 750,
        showtimes: ["11:30 AM", "2:45 PM", "6:00 PM", "9:15 PM"]
    }
];

// State management
let selectedMovie = null;
let selectedShowtime = null;
let selectedSeats = new Set();

// DOM Elements
const movieListContainer = document.getElementById('movie-list-container');
const bookingContainer = document.getElementById('booking-container');
const moviesGrid = document.querySelector('.movies-grid');
const backButton = document.getElementById('back-to-movies');
const selectedMoviePoster = document.getElementById('selected-movie-poster');
const selectedMovieTitle = document.getElementById('selected-movie-title');
const selectedMovieDescription = document.getElementById('selected-movie-description');
const showtimeButtons = document.getElementById('showtime-buttons');
const seatSelection = document.getElementById('seat-selection');
const seatMap = document.getElementById('seat-map');
const priceSummary = document.getElementById('price-summary');
const bookNowButton = document.getElementById('book-now');

// Initialize page
function initializeMovieList() {
    moviesGrid.innerHTML = movies.map((movie, index) => `
        <div class="movie-card">
            <img src="${movie.poster}" alt="${movie.title}">
            <div class="movie-card-content">
                <h3>${movie.title}</h3>
                <p>${movie.description}</p>
                <button class="button primary" onclick="showBookingView(${index})">
                    View Showtimes
                </button>
            </div>
        </div>
    `).join('');
}

// Show booking view for selected movie
function showBookingView(movieIndex) {
    selectedMovie = movies[movieIndex];
    selectedShowtime = null;
    selectedSeats.clear();
    
    movieListContainer.classList.add('hidden');
    bookingContainer.classList.remove('hidden');
    seatSelection.classList.add('hidden');
    
    // Update movie details
    selectedMoviePoster.src = selectedMovie.poster;
    selectedMovieTitle.textContent = selectedMovie.title;
    selectedMovieDescription.textContent = selectedMovie.description;
    
    // Generate showtime buttons
    showtimeButtons.innerHTML = selectedMovie.showtimes.map(time => `
        <button class="button primary" onclick="selectShowtime('${time}')">
            ${time}
        </button>
    `).join('');
    
    updatePriceSummary();
}

// Handle showtime selection
function selectShowtime(time) {
    selectedShowtime = time;
    selectedSeats.clear();
    
    // Show seat selection
    seatSelection.classList.remove('hidden');
    
    // Generate seat map
    generateSeatMap();
    updatePriceSummary();
}

// Generate seat map with random occupied seats
function generateSeatMap() {
    seatMap.innerHTML = '';
    
    for (let i = 0; i < 8; i++) {
        for (let j = 0; j < 10; j++) {
            const seatNumber = i * 10 + j;
            const isOccupied = Math.random() < 0.3; // 30% chance of being occupied
            
            const seat = document.createElement('div');
            seat.className = `seat ${isOccupied ? 'occupied' : 'available'}`;
            seat.dataset.seatNumber = seatNumber;
            
            seat.addEventListener('click', () => toggleSeat(seat, isOccupied));
            seatMap.appendChild(seat);
        }
    }
}

// Handle seat selection/deselection
function toggleSeat(seat, isOccupied) {
    if (isOccupied) return;
    
    const seatNumber = seat.dataset.seatNumber;
    
    if (selectedSeats.has(seatNumber)) {
        selectedSeats.delete(seatNumber);
        seat.classList.remove('selected');
    } else {
        selectedSeats.add(seatNumber);
        seat.classList.add('selected');
    }
    
    updatePriceSummary();
}

// Update price summary and book now button
function updatePriceSummary() {
    const seatCount = selectedSeats.size;
    const total = seatCount * selectedMovie?.price || 0;
    
    priceSummary.textContent = `${seatCount} Seats | Total: ₹${total}`;
    bookNowButton.disabled = seatCount === 0;
    
    // Add event listener for booking
    bookNowButton.onclick = seatCount > 0 ? handleBooking : null;
}

// Handle the booking process
function handleBooking() {
    const bookingDetails = {
        movieTitle: selectedMovie.title,
        showtime: selectedShowtime,
        seatCount: selectedSeats.size,
        totalPrice: selectedSeats.size * selectedMovie.price
    };
    
    // Save booking details to localStorage
    localStorage.setItem('bookingDetails', JSON.stringify(bookingDetails));
    
    // Redirect to payment page
    window.location.href = 'payment.html';
}

// Handle back button
backButton.addEventListener('click', () => {
    movieListContainer.classList.remove('hidden');
    bookingContainer.classList.add('hidden');
    selectedMovie = null;
    selectedShowtime = null;
    selectedSeats.clear();
});

// Initialize the page
initializeMovieList();