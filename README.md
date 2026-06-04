# ProDex -- Smart Product Aggregator

ProDex is a web application that helps users search for products from
multiple e-commerce platforms in one place.\
Users can search using **text, voice, or images**, making product
discovery faster and easier.

------------------------------------------------------------------------

## Features

-   **Text Search**
    -   Users can type a product name and search across platforms like
        Amazon, Flipkart, Myntra, etc.
    -   Uses SERP API to fetch real-time product results.
-   **Voice Search**
    -   Users can speak the product name using the microphone.
    -   Implemented using the WebKit Speech Recognition API.
-   **Image Search**
    -   Users can upload a product image.
    -   The system processes the image and finds visually similar
        products.
-   **Virtual Try-On**
    -   Users can upload their photo and preview how apparel items look
        on them.
    -   Implemented using Google Vertex AI and Google Cloud Storage.
-   **Wishlist**
    -   Users can save products to a wishlist for later viewing.
-   **Chatbot Support**
    -   A simple chatbot helps users with product search and queries.

------------------------------------------------------------------------

## Tech Stack

**Frontend** - HTML - Tailwind CSS - JavaScript

**Backend** - Python - Flask

**APIs & Cloud Services** - SERP API (Product search) - Google Cloud
Storage (Image storage) - Google Vertex AI (Virtual try-on)

------------------------------------------------------------------------

## Project Workflow

### 1. User Search Input
The user searches for a product using **text, voice, or an image upload**.

### 2. Input Processing
- **Text input:** Sent directly to the backend.
- **Voice input:** Converted into text using **WebKit Speech Recognition**, then processed as a normal search query.
- **Image input:** The uploaded image is analyzed and converted into a **textual product description**, which is then used as a search query.

### 3. Backend Request Handling
The processed search query is sent to the **Flask backend**, which prepares the search parameters.

### 4. Product Retrieval
The backend calls **SERP API** to fetch product results from multiple e-commerce platforms such as **Amazon, Flipkart, Myntra, Ajio, Etsy**, and others.

### 5. Filtering and Sorting
The retrieved products are refined based on user-selected filters, including:

- **Maximum price range**
- **Preferred shopping platforms** (Amazon, Myntra, Ajio, Etsy, etc.)
- **Sorting options** such as price or relevance

### 6. Displaying Results
The filtered products are returned to the frontend and displayed to the user.

### 7. Virtual Try-On Feature
If the user wants to see how an apparel item looks on them, they can select the **Virtual Try-On** option.

- The user uploads their photo.
- The system processes the user's image and the selected product image.
- Using **Google Vertex AI**, a new image is generated showing the user wearing the selected dress.

------------------------------------------------------------------------
