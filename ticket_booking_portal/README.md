# Movie Ticket Booking Portal

A browser-based movie ticket booking app built with vanilla HTML, CSS, and JavaScript. Users can browse movies, select a showtime, pick seats from an interactive seat map, and confirm payment.

---

## Features

- **Movie listing** — grid of available movies with posters and descriptions
- **Showtime selection** — multiple time slots per movie
- **Interactive seat map** — visual seat grid with available, selected, and occupied states
- **Payment confirmation** — booking summary and payment page
- **Seat pricing** — dynamic total calculated as seats are selected

---

## Flow

1. Browse the movie grid and select a film
2. Choose a showtime
3. Select seats from the seat map
4. Click **Book Now** — redirects to the payment confirmation page
5. Confirm payment

---

## How to Use

No build step or dependencies required — it's plain HTML/CSS/JS.

1. Open `index.html` directly in any modern browser:
   ```
   open index.html
   ```
   Or serve locally:
   ```bash
   npx serve .
   # then open http://localhost:3000
   ```

2. Select a movie, pick a showtime and seats, then proceed to payment.

---

## Files

```
ticket_booking_portal/
├── index.html      # Movie listing and seat selection UI
├── script.js       # Movie data, seat map logic, booking flow
├── payment.html    # Payment confirmation page
├── payment.js      # Reads booking details from session/URL and confirms
├── style.css       # Styling and layout
├── robocop.jpg     # Movie poster asset
└── superman.jpg    # Movie poster asset
```
