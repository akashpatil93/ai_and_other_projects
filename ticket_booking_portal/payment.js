// DOM Elements
const bookingSummary = document.getElementById('booking-summary');
const confirmPaymentButton = document.getElementById('confirm-payment');

// Load and display booking details
function loadBookingDetails() {
    const bookingDetails = JSON.parse(localStorage.getItem('bookingDetails'));
    
    if (!bookingDetails) {
        window.location.href = 'index.html';
        return;
    }
    
    bookingSummary.innerHTML = `
        <h3>Booking Summary</h3>
        <p><strong>Movie:</strong> ${bookingDetails.movieTitle}</p>
        <p><strong>Showtime:</strong> ${bookingDetails.showtime}</p>
        <p><strong>Number of Seats:</strong> ${bookingDetails.seatCount}</p>
        <p><strong>Total Amount:</strong> ₹${bookingDetails.totalPrice}</p>
    `;
}

// Handle payment confirmation
function handlePaymentConfirmation() {
    alert('Payment successful! Your tickets are confirmed.');
    localStorage.removeItem('bookingDetails');
    window.location.href = 'index.html';
}

// Add event listener for payment confirmation
confirmPaymentButton.addEventListener('click', handlePaymentConfirmation);

// Initialize the page
loadBookingDetails();