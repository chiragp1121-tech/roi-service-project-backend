<<<<<<< HEAD
# React + Vite + Tailwind CSS + Axios Starter

A complete, production-ready React application starter configured with **Axios** (with interceptors & standardized error handling), **Tailwind CSS v3**, **Prettier** (auto formatting + tailwind class sorting), and **ESLint 9** (flat config with react hooks rules).

---

## 🚀 Features

- ⚡ **React 19 + Vite**: Ultra-fast hot module replacement (HMR) and lightweight builds.
- 🎨 **Tailwind CSS v3**: Pre-configured with `postcss` and `autoprefixer`, plus dark theme base styles.
- 🌐 **Axios Client**: Centralized API instance in [`src/api/axiosClient.js`](file:///c:/Users/Vinayak/Desktop/Pratik/Service%20Project%20ROI/src/api/axiosClient.js) with:
  - Base URL configuration from environment variables (`.env`)
  - Request Interceptors (automatic auth token injection & dev logging)
  - Response Interceptors (automatic unwrapping and standardized error messages)
- ✨ **Prettier**: Pre-configured in [`.prettierrc`](file:///c:/Users/Vinayak/Desktop/Pratik/Service%20Project%20ROI/.prettierrc) with `prettier-plugin-tailwindcss` for class sorting.
- 🔍 **ESLint 9**: Flat configuration in [`eslint.config.js`](file:///c:/Users/Vinayak/Desktop/Pratik/Service%20Project%20ROI/eslint.config.js) integrated with `eslint-config-prettier`.

---

## 📂 Project Structure

```
├── .env                    # Environment variables (API Base URL)
├── .env.example            # Environment template
├── .prettierrc             # Prettier configuration
├── .prettierignore         # Prettier ignore patterns
├── eslint.config.js        # ESLint 9 configuration
├── index.html              # HTML Entry
├── package.json            # Project dependencies & scripts
├── postcss.config.js       # PostCSS config for Tailwind
├── tailwind.config.js      # Tailwind CSS configuration
├── vite.config.js          # Vite configuration
└── src/
    ├── api/
    │   ├── axiosClient.js  # Configured Axios instance & interceptors
    │   └── postService.js  # Sample API service layer
    ├── assets/             # Static assets
    ├── App.jsx             # Interactive UI demo with Axios & Tailwind
    ├── index.css           # Tailwind directives & base styles
    └── main.jsx            # React root mount
```

---

## 🛠️ Available Scripts

| Script               | Command                | Description                                               |
| :------------------- | :--------------------- | :-------------------------------------------------------- |
| **Development**      | `npm run dev`          | Starts Vite dev server (usually at http://localhost:5173) |
| **Production Build** | `npm run build`        | Builds optimized bundle to `dist/`                        |
| **Preview Build**    | `npm run preview`      | Previews production build locally                         |
| **ESLint Check**     | `npm run lint`         | Runs ESLint on the project                                |
| **ESLint Fix**       | `npm run lint:fix`     | Automatically fixes auto-fixable lint issues              |
| **Prettier Format**  | `npm run format`       | Auto-formats all files with Prettier                      |
| **Prettier Check**   | `npm run format:check` | Checks formatting without modifying files                 |

---

## 🌐 How to Use Axios for API Calls

### 1. Import `axiosClient`

```javascript
import axiosClient from './api/axiosClient';

// Direct request
const data = await axiosClient.get('/users');
const newRecord = await axiosClient.post('/users', { name: 'John Doe' });
```

### 2. Service Pattern (Recommended)

Create modular service files inside `src/api/` (see [`src/api/postService.js`](file:///c:/Users/Vinayak/Desktop/Pratik/Service%20Project%20ROI/src/api/postService.js)):

```javascript
import axiosClient from './axiosClient';

export const userService = {
  getAll: () => axiosClient.get('/users'),
  getById: (id) => axiosClient.get(`/users/${id}`),
  create: (data) => axiosClient.post('/users', data),
  delete: (id) => axiosClient.delete(`/users/${id}`),
};
```
=======
# roi-service-project-frontend
>>>>>>> 2bd6b93a23e2eea7ca0ebd4112ae29857fd2be6a
