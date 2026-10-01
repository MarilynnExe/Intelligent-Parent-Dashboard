document.addEventListener("DOMContentLoaded", () => {

    const loginForm = document.getElementById("login-form");
    const errorBox = document.getElementById("error-message");
    const submitBtn = document.getElementById("submit-btn");

    loginForm.addEventListener("submit", async (e) => {

        e.preventDefault();

        errorBox.style.display = "none";

        submitBtn.disabled = true;
        submitBtn.textContent = "Verifying...";

        const email_or_username =
            document.getElementById("username").value.trim();

        const password =
            document.getElementById("password").value;

        try {

            const response = await fetch(
                `${API_BASE_URL}/auth/login`,
                {
                    method: "POST",

                    headers: {
                        "Content-Type": "application/json"
                    },

                    body: JSON.stringify({
                        email_or_username,
                        password
                    })
                }
            );

            const data = await response.json();

            if (!response.ok) {
                throw new Error(
                    data.detail || "Authentication failed"
                );
            }

            // Save JWT and user profile
            Auth.saveSession(
                data.access_token,
                data.user
            );

            // Send user to the correct dashboard
            switch (data.user.role) {

                case "ADMIN":
                    window.location.href =
                        "admin-dashboard.html";
                    break;

                case "TEACHER":
                    window.location.href =
                        "teacher-dashboard.html";
                    break;

                case "PARENT":
                    window.location.href =
                        "parent-dashboard.html";
                    break;

                default:
                    throw new Error(
                        "Unrecognized user role"
                    );
            }

        } catch (err) {

            errorBox.textContent = err.message;
            errorBox.style.display = "block";

            submitBtn.disabled = false;
            submitBtn.textContent = "Sign In";
        }

    });

});