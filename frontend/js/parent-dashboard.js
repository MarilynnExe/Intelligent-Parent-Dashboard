document.addEventListener("DOMContentLoaded", () => {

    // Make sure only PARENT users can access this page
    if (!Auth.requireRole("PARENT")) {
        return;
    }

    // Get logged-in user
    const user = Auth.getUser();

    // Display parent name
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