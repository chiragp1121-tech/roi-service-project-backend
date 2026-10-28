import axios from 'axios';

// Get base URL from environment variables
const baseURL =
  import.meta.env.VITE_API_BASE_URL;

const axiosClient = axios.create({
  baseURL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
    // Required to bypass ngrok free tier browser intercept warning
    'ngrok-skip-browser-warning': 'true',
  },
});

// Request Interceptor: Attach auth tokens & log requests
axiosClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    if (import.meta.env.DEV) {
      console.log(
        `[API Request] ${config.method?.toUpperCase()} -> ${config.url}`,
        config.params || config.data
      );
    }
    return config;
  },
  (error) => {
    console.error('[API Request Error]', error);
    return Promise.reject(error);
  }
);

// Response Interceptor: Extract data and handle errors cleanly
axiosClient.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    let message = 'An error occurred while fetching data.';
    if (error.response) {
      message =
        error.response.data?.message ||
        `Server responded with status ${error.response.status}`;
    } else if (error.request) {
      message =
        'No response from server. Check if ngrok tunnel or API server is running.';
    } else {
      message = error.message;
    }

    console.error('[API Response Error]', message, error);
    return Promise.reject({
      message,
      status: error.response?.status,
      data: error.response?.data,
      raw: error,
    });
  }
);

export default axiosClient;
