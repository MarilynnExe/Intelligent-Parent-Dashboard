document.addEventListener("DOMContentLoaded", () => {

    // Make sure only TEACHER users can access this page
    if (!Auth.requireRole("TEACHER")) {
        return;
    }

    // Get logged-in user
    const user = Auth.getUser();

    // Display teacher name
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