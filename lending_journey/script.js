document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('loanApplication');
    const steps = Array.from(document.getElementsByClassName('step'));
    const nextBtn = document.getElementById('nextBtn');
    const prevBtn = document.getElementById('prevBtn');
    const submitBtn = document.getElementById('submitBtn');
    const progressFill = document.querySelector('.progress-fill');
    const progressText = document.querySelector('.progress-text');
    let currentStep = 0;

    // Update progress bar and navigation
    const updateProgress = () => {
        const progress = ((currentStep + 1) / steps.length) * 100;
        progressFill.style.width = `${progress}%`;
        progressText.textContent = `Step ${currentStep + 1} of ${steps.length}`;

        // Update button visibility
        prevBtn.style.display = currentStep === 0 ? 'none' : 'block';
        nextBtn.style.display = currentStep === steps.length - 1 ? 'none' : 'block';
        submitBtn.style.display = currentStep === steps.length - 1 ? 'block' : 'none';
    };

    // Show current step
    const showStep = (step) => {
        steps.forEach((s, index) => {
            s.classList.toggle('active-step', index === step);
        });
        updateProgress();
    };

    // Validation patterns
    const patterns = {
        email: /^[^\s@]+@[^\s@]+\.[^\s@]+$/,
        phone: /^\d{10}$/,
        pan: /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/,
        aadhaar: /^\d{12}$/,
    };

    // Validation messages
    const errorMessages = {
        required: 'This field is required',
        email: 'Please enter a valid email address',
        phone: 'Please enter a valid 10-digit phone number',
        pan: 'Please enter a valid PAN number (e.g., ABCDE1234F)',
        aadhaar: 'Please enter a valid 12-digit Aadhaar number',
        loanAmount: 'Amount must be between ₹1,00,000 and ₹10,00,000',
        loanTerm: 'Term must be between 12 and 60 months'
    };

    // Show error message
    const showError = (input, message) => {
        const errorDiv = input.nextElementSibling;
        input.classList.add('error');
        errorDiv.textContent = message;
        errorDiv.classList.add('visible');
        return false;
    };

    // Clear error message
    const clearError = (input) => {
        const errorDiv = input.nextElementSibling;
        input.classList.remove('error');
        errorDiv.classList.remove('visible');
        errorDiv.textContent = '';
    };

    // Validate a single field
    const validateField = (input) => {
        if (input.hasAttribute('required') && !input.value) {
            return showError(input, errorMessages.required);
        }

        if (input.type === 'email' && !patterns.email.test(input.value)) {
            return showError(input, errorMessages.email);
        }

        if (input.id === 'phone' && !patterns.phone.test(input.value)) {
            return showError(input, errorMessages.phone);
        }

        if (input.id === 'pan' && !patterns.pan.test(input.value)) {
            return showError(input, errorMessages.pan);
        }

        if (input.id === 'aadhaar' && !patterns.aadhaar.test(input.value)) {
            return showError(input, errorMessages.aadhaar);
        }

        if (input.id === 'loanAmount') {
            const amount = parseInt(input.value);
            if (amount < 100000 || amount > 1000000) {
                return showError(input, errorMessages.loanAmount);
            }
        }

        if (input.id === 'loanTerm') {
            const term = parseInt(input.value);
            if (term < 12 || term > 60) {
                return showError(input, errorMessages.loanTerm);
            }
        }

        clearError(input);
        return true;
    };

    // Validate current step
    const validateStep = () => {
        const currentFields = steps[currentStep].querySelectorAll('input, select, textarea');
        let isValid = true;

        currentFields.forEach(field => {
            if (!validateField(field)) {
                isValid = false;
            }
        });

        return isValid;
    };

    // Add input event listeners for real-time validation
    form.querySelectorAll('input, select, textarea').forEach(input => {
        input.addEventListener('input', () => validateField(input));
        input.addEventListener('blur', () => validateField(input));
    });

    // Populate review step
    const populateReview = () => {
        const reviewContent = document.getElementById('reviewContent');
        const dl = document.createElement('dl');
        const formData = new FormData(form);

        for (let [key, value] of formData.entries()) {
            if (key !== 'panCard' && key !== 'aadhaarCard') {
                const dt = document.createElement('dt');
                const dd = document.createElement('dd');
                
                // Format the key for display
                const formattedKey = key.replace(/([A-Z])/g, ' $1')
                    .split(/(?=[A-Z])/)
                    .join(' ')
                    .replace(/^./, str => str.toUpperCase());

                dt.textContent = formattedKey;
                dd.textContent = value;
                dl.appendChild(dt);
                dl.appendChild(dd);
            }
        }

        reviewContent.innerHTML = '';
        reviewContent.appendChild(dl);
    };

    // Navigation event listeners
    nextBtn.addEventListener('click', () => {
        if (validateStep()) {
            currentStep++;
            if (currentStep === steps.length - 1) {
                populateReview();
            }
            showStep(currentStep);
        }
    });

    prevBtn.addEventListener('click', () => {
        currentStep--;
        showStep(currentStep);
    });

    // Form submission
    form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (validateStep()) {
            form.style.display = 'none';
            document.querySelector('.progress-bar').style.display = 'none';
            document.getElementById('confirmationPage').style.display = 'block';
        }
    });

    // Initialize form
    showStep(currentStep);
});