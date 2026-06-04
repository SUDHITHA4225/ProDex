# prodex_search.py
# This version includes enhanced query simplification to handle social media/noise words
# that Google Lens often returns (like hashtags and emojis).
import requests
import random
import time 
import os
import re 
from google.cloud import storage 
from werkzeug.utils import secure_filename 

# --- Google Cloud Configuration ---
# NOTE: This bucket is used ONLY for image search uploads.
GCS_BUCKET_NAME = 'prodex-image-storage'
GCS_BASE_URL = f"https://storage.googleapis.com/{GCS_BUCKET_NAME}/"
# ------------------------------------

# --- SerpApi Configuration (Using your latest key) ---
SERP_API_KEY = 'e3117cf82e0306444bea73193bd2954407091f7bff1b71151de40b08bdab1cbc'
SEARCH_URL = 'https://serpapi.com/search.json'
RESULTS_LIMIT_PER_SITE = 2
MOCK_MODE = False 
IMAGE_SEARCH_MASTER_SITES = [
    "amazon.in",
    "etsy.com",
    "myntra.com",
    "flipkart.com",
    "limeroad.com",
    "ajio.com",
    "zalando.com",
    "meesho.com"
]
MOCK_IMAGE_QUERIES = []
# -----------------------------

# --- NEW HELPER FUNCTION: Clean and Convert Price String ---
def _get_numeric_price(price_str):
    """Converts a price string (e.g., '₹ 1,999.00') into a comparable float."""
    if not isinstance(price_str, str):
        return None 
        
    # Remove all currency symbols, commas, and spaces
    cleaned = re.sub(r'[\$,₹a-zA-Z\s]', '', price_str)
    
    try:
        # Convert to float
        return float(cleaned)
    except ValueError:
        # Return None if conversion fails (e.g., price was 'N/A')
        return None
# ------------------------------------------------------------

def simplify_query(long_query):
    """
    Strips down an overly specific product title to core keywords,
    aggressively removing social media noise, domains, and metadata.
    """
    
    # --- STEP 1: REMOVE E-COMMERCE NOISE PREFIXES (FIX for unwanted titles) ---
    prefix_patterns = [
        r'^\s*Amazon\.com\s*:\s*',      # Matches 'Amazon.com: '
        r'^\s*Etsy\s*:\s*',             
        r'^\s*Shop\s*online\s*:\s*',    
        r'^\s*[\w\s]+\.(com|in|net|org|co)\s*:\s*', # Matches any domain + colon
        r'^\s*Official Site\s*:\s*',
        r'^\s*Product Title\s*:\s*',
    ]

    simplified = long_query
    for pattern in prefix_patterns:
        simplified = re.sub(pattern, '', simplified, flags=re.IGNORECASE)


    # --- STEP 2: REMOVE SOCIAL MEDIA NOISE (FIX for khushi_dance #reels) ---
    # Regex for Emojis
    emoji_pattern = re.compile(r'[\U00010000-\U0010ffff]', flags=re.UNICODE)
    simplified = emoji_pattern.sub(r'', simplified)
    # Remove hashtags (#reels) and social media handles (@user)
    simplified = re.sub(r'#\w+|@\w+', ' ', simplified)


    # --- STEP 3: CLEANING METADATA (Original logic maintained) ---
    simplified = re.sub(
        r'\s*\(.*?\)\s*|,\s*\|.*| at [A-Za-z\s]+ store|,\s*Bridesmaid Dress', 
        ' ', 
        simplified, 
        flags=re.IGNORECASE
    )
    
    simplified = simplified.replace('"', '').replace("'", '').replace('|', ' ').replace(',', ' ').strip()

    # Aggressively remove generic size/color codes if they are left over
    removal_patterns = [
        r'\s*(US|UK|EU)\s*\d+M?\s*', 
        r'\s*(Numeric|Regular|Teen|Girlism|MOD)\s*',
        r'SKU:\s*\w+',
        r'\s*model\s*\w*\s*', 
    ]
    for pattern in removal_patterns:
        simplified = re.sub(pattern, ' ', simplified, flags=re.IGNORECASE).strip()

    # Clean up excessive spaces and ensure a tight query
    simplified = re.sub(r'\s+', ' ', simplified).strip()

    # Keep up to the first 10 high-value words
    keywords = simplified.split()[:10]
    
    # FINAL FALLBACK
    if not keywords:
        return "clothing item"

    return " ".join(keywords)


def upload_to_gcs(file_stream, original_filename):
    """Uploads a file stream to Google Cloud Storage and returns the public URL."""
    try:
        storage_client = storage.Client() 
        bucket = storage_client.bucket(GCS_BUCKET_NAME)
        
        timestamp = int(time.time())
        filename = f"{timestamp}_{secure_filename(original_filename)}"
        
        blob = bucket.blob(filename)
        
        file_stream.seek(0)
        
        blob.upload_from_file(file_stream, content_type=None) 
        
        print(f"GCS SUCCESS: Uploaded {filename}. Public URL generated.")
        return GCS_BASE_URL + filename
    
    except Exception as e:
        print("-" * 35)
        print("GCS UPLOAD ATTEMPT FAILED!")
        print(f"FATAL ERROR UPLOADING TO GCS: {e}")
        print("-" * 35)
        return None


def _format_results(data, site, product_id_start):
    """Helper function to process and format search results, with maximum price extraction attempts."""
    all_results = []
    product_id = product_id_start
    
    # Define a universal regex pattern to find currency and number strings ($, ₹, USD, INR)
    PRICE_PATTERN = r'(\$|\₹|INR|USD)\s*\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?'

    if "organic_results" in data and data["organic_results"]:
        for result in data["organic_results"]:
            price = None
            image = None

            # 1. Check direct 'price' field
            price = result.get("price") 
            
            # 2. Check Shopping Results (If price is still None)
            if not price and "shopping_results" in data:
                for shopping_item in data["shopping_results"]:
                    if (shopping_item.get("link") == result.get("link") or 
                        shopping_item.get("source", "").lower() == site.lower()):
                        
                        price = shopping_item.get("price")
                        if price:
                            break
            
            # --- Attempt 3: Aggressive Unstructured Field Search ---
            
            # 3. Look for price in the Snippet/Description
            if not price:
                snippet = result.get("snippet", "")
                price_match = re.search(PRICE_PATTERN, snippet)
                if price_match:
                    price = price_match.group(0).strip()
            
            # 4. Look for price in the Title
            if not price:
                title = result.get("title", "")
                price_match = re.search(PRICE_PATTERN, title)
                if price_match:
                    price = price_match.group(0).strip()

            # --- Image Extraction (Unchanged) ---
            if not image:
                image = result.get("thumbnail")

            # 5. FINAL FALLBACK DEFAULTS
            image = image or "https://via.placeholder.com/300x200?text=No+Image"
            price = price or "N/A" # Price is defaulted to 'N/A' if not found

            all_results.append({
                "id": product_id,
                "site": site,
                "title": result.get("title", "No title available"),
                "link": result.get("link", "#"),
                "snippet": result.get("snippet", "No description available"),
                "price": price,
                "numeric_price": _get_numeric_price(price),
                "image": image
            })
            product_id += 1
    return all_results, product_id


def search_products(prodDes, websites):
    all_results = []
    product_id = 1
    
    if MOCK_MODE:
        return all_results
        
    if not isinstance(websites, list):
        websites = [w.strip() for w in websites.split(',') if w.strip()]

    for site in websites:
        site = site.strip()
        if not site:
            continue

        params = {
            "engine": "google",
            "q": f"{prodDes} site:{site}", 
            "api_key": SERP_API_KEY, 
            "num": RESULTS_LIMIT_PER_SITE
        }

        print(f"SEARCHING: Query: {params['q']} (Limit: {params['num']})")

        try:
            response = requests.get(SEARCH_URL, params=params, timeout=10)
            response.raise_for_status() 
            data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Request error for {site}: {e}")
            continue

        if "organic_results" in data and data["organic_results"]:
            print(f"SUCCESS: Found {len(data['organic_results'])} results for {site}.")
            results, product_id = _format_results(data, site, product_id)
            all_results.extend(results)
        else:
            print(f"NO RESULTS: API returned no organic_results for {site}. Query: {params['q']}")


    return all_results


def search_by_image(file_stream, filename):
    """
    Handles image upload to GCS, calls Google Lens, simplifies the query,
    and then aggregates the results.
    """
    
    # 1. UPLOAD IMAGE TO GOOGLE CLOUD STORAGE
    image_url_for_api = upload_to_gcs(file_stream, filename)
    
    if not image_url_for_api:
        return search_products("image upload failed, please try again", IMAGE_SEARCH_MASTER_SITES), "Image Upload Failed"

    print(f"LENS SEARCH: Using public GCS URL: {image_url_for_api}")
    
    # 2. CALL GOOGLE LENS API TO GET A SEARCH QUERY
    lens_params = {
        "engine": "google_lens", 
        "url": image_url_for_api, 
        "api_key": SERP_API_KEY,
    }

    try:
        response = requests.get(SEARCH_URL, params=lens_params, timeout=15)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Google Lens API request failed: {e}")
        extracted_query = "clothing item search error" 
        return search_products(extracted_query, IMAGE_SEARCH_MASTER_SITES), "Lens Error"
    
    # 3. EXTRACT AND SIMPLIFY QUERY
    extracted_query = "dress" # Default fallback
    if 'search_parameters' in data and 'q' in data['search_parameters']:
        extracted_query = data['search_parameters']['q']
    elif 'visual_matches' in data and data['visual_matches']:
        extracted_query = data['visual_matches'][0].get('title', extracted_query)
        
    final_query = simplify_query(extracted_query)

    print(f"LIVE LENS RESULT: Extracted Query: '{extracted_query}'")
    print(f"CLEANED QUERY USED: '{final_query}'")
    
    # 4. EXECUTE PRODUCT AGGREGATION SEARCH
    all_results = search_products(final_query, IMAGE_SEARCH_MASTER_SITES)
    
    return all_results, final_query
