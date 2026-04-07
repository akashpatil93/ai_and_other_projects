# Lending Journey — Personal Loan Application

A multi-step personal loan application form built with vanilla HTML, CSS, and JavaScript. Guides applicants through a 5-step wizard collecting personal details, employment info, loan requirements, document uploads, and a final review before submission.

---

## Features

- **5-step wizard** — progress bar tracks completion across steps
- **Client-side validation** — inline error messages for each field
- **Document upload** — PAN card and Aadhaar card photo upload
- **Review step** — applicant can review all entered data before submitting
- **Confirmation screen** — success page shown after submission

---

## Steps

| Step | What it collects |
|------|-----------------|
| 1 | Personal info (name, DOB, address, email, phone, PAN, Aadhaar) |
| 2 | Employment & income details |
| 3 | Loan amount, purpose, and term |
| 4 | PAN card and Aadhaar card photo uploads |
| 5 | Review and submit |

---

## How to Use

No build step or dependencies required — it's plain HTML/CSS/JS.

1. Open `index.html` directly in any modern browser:
   ```
   open index.html
   ```
   Or serve it locally with any static server:
   ```bash
   npx serve .
   # then open http://localhost:3000
   ```

2. Fill out each step and click **Next** to advance.
3. On the final step, review your details and click **Submit Application**.

---

## Files

```
lending_journey/
├── index.html    # Main application UI and form structure
├── script.js     # Step navigation, validation, review population
└── style.css     # Styling and layout
```
