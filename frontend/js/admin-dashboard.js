document.addEventListener("DOMContentLoaded", () => {

    // Make sure only ADMIN users can access this page
    if (!Auth.requireRole("ADMIN")) {
        return;
    }

    // Get logged-in user
    const user = Auth.getUser();

    // Display their name
    document.getElementById(
        "user-display-name"
    ).textContent = user.full_name;

    // Logout
    document.getElementById(
        "logout-btn"
    ).addEventListener("click", () => {
        Auth.logout();
    });

});