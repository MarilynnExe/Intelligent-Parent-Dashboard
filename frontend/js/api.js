const API_BASE_URL = "http://127.0.0.1:8000/api";


const Auth = {

    // Save login token and user information
    saveSession(token, user) {

        localStorage.setItem(
            "authToken",
            token
        );

        localStorage.setItem(
            "userProfile",
            JSON.stringify(user)
        );
    },


    // Get stored authentication token
    getToken() {

        return localStorage.getItem(
            "authToken"
        );
    },


    // Get stored user information
    getUser() {

        const userStr =
            localStorage.getItem("userProfile");

        return userStr
            ? JSON.parse(userStr)
            : null;
    },


    // Log the user out
    logout() {

        localStorage.removeItem(
            "authToken"
        );

        localStorage.removeItem(
            "userProfile"
        );

        window.location.href =
            "login.html";
    },


    // Check whether the user has the correct role
    requireRole(expectedRole) {

        const token =
            this.getToken();

        const user =
            this.getUser();


        // No login information
        if (!token || !user) {

            window.location.href =
                "login.html";

            return false;
        }


        // Wrong role
        if (user.role !== expectedRole) {

            alert(
                `Access denied. This portal is for ${expectedRole} users only.`
            );

            this.logout();

            return false;
        }


        return true;
    }

};


// API helper
// Automatically attaches the JWT to requests
async function apiFetch(
    endpoint,
    options = {}
) {

    const token =
        Auth.getToken();


    const headers = {

        "Content-Type":
            "application/json",

        ...(options.headers || {})
    };


    if (token) {

        headers["Authorization"] =
            `Bearer ${token}`;
    }


    const response = await fetch(
        `${API_BASE_URL}${endpoint}`,
        {
            ...options,
            headers
        }
    );


    // If the backend says the token is invalid
    if (response.status === 401) {

        Auth.logout();
    }


    return response;
}