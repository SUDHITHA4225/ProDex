import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, session, jsonify, redirect, url_for, flash, g
from prodex_search import search_products, search_by_image
from google.cloud import storage
from flask_cors import CORS 
import requests
import uuid
import time
import datetime
import sys
import boto3
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from werkzeug.security import generate_password_hash, check_password_hash
from botocore.exceptions import ClientError



# Connect to DynamoDB
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_KEY")
AWS_REGION = "us-east-1"

dynamodb = boto3.resource(
    'dynamodb',
    region_name=AWS_REGION,
    aws_access_key_id=AWS_ACCESS_KEY,
    aws_secret_access_key=AWS_SECRET_KEY
)

users_table = dynamodb.Table('prodex')

# --- Load .env first ---
load_dotenv()

# --- Check critical environment variables ---
required_env_vars = ["PROJECT_ID", "LOCATION", "BUCKET_NAME", "GOOGLE_APPLICATION_CREDENTIALS", "SERP_API_KEY"]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

# Configuration: CORRECTED to use environment variables
PROJECT_ID = os.getenv("PROJECT_ID")
LOCATION = os.getenv("LOCATION")
# FIX: Use the BUCKET_NAME from your .env (prodexxx_try_on)
BUCKET_NAME = os.getenv("BUCKET_NAME") 
SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = SERVICE_ACCOUNT_PATH

# Initialize GCS client
try:
    storage_client = storage.Client.from_service_account_json(SERVICE_ACCOUNT_PATH)
    print("GCS client initialized successfully.")
except Exception as e:
    print(f"FATAL ERROR: Failed to initialize GCS client: {e}")
    sys.exit(1)

app = Flask(__name__) 
CORS(app)
app.secret_key = 'your_very_secret_key_here_for_prodex_wishlist'

MASTER_SITES = [
    "amazon.in", "etsy.com", "myntra.com", "flipkart.com", "limeroad.com", "ajio.com", "zalando.com","meesho.com",
]
DEDICATED_CHECKBOX_SITES = ["amazon.in", "etsy.com", "flipkart.com", "limeroad.com", "myntra.com", "ajio.com", "zalando.com","meesho.com"]
OTHER_SITES = [site for site in MASTER_SITES if site not in DEDICATED_CHECKBOX_SITES]


# --- Chatbot Logic: Replaces the mock function ---
def chatbot_response(user_input):
    user_input = user_input.lower().strip() # Normalize input

    responses = {
        # Greetings
        "hi": "Hello! Welcome to ProDex 👋 How can I assist you today?",
        "hello": "Hi there! Welcome to ProDex – your smart product search assistant!",
        "hey": "Hey! 😊 How can I help you with your shopping today?",

        # About ProDex
        "what is prodex": "ProDex is an AI-powered shopping assistant that helps you find products across multiple e-commerce sites quickly.",
        "about prodex": "ProDex combines smart search, price tracking, and virtual try-on to make online shopping smarter and easier.",
        "who created prodex": "ProDex was created by a passionate team of developers to simplify the way people discover and compare products online.",

        # Features
        "features": "ProDex features include: 🛍 Smart product search, 🧠 AI recommendations, 📉 Price drop alerts, 🎭 Virtual Try-On, and 🔍 Image-based search!",
        "what can i do here": "You can search for products by text, image, or even voice. You can also try clothes virtually and get notified about price drops.",
        "does prodex use ai": "Yes! ProDex uses AI for visual search, product matching, and personalized recommendations.",

        # Virtual Try-On
        "what is virtual try on": "Virtual Try-On lets you see how a dress or outfit would look on you using AI-based image processing.",
        "how does try on work": "You can upload your photo or use your webcam, and ProDex will overlay the selected outfit using AI vision models.",
        "can i use virtual try on for free": "Yes, Virtual Try-On is free to use for all users right now! 🎉",

        # Product Search
        "how to search products": "You can type your query, use voice search, or upload an image. ProDex will find matching products instantly.",
        "can i search by image": "Absolutely! Just upload a product image and ProDex will find visually similar items from multiple stores.",
        "what sites does prodex search": "ProDex searches across popular e-commerce platforms like Amazon, Flipkart, and Myntra.",

        # Price Tracker
        "what is price drop alert": "ProDex monitors your saved products and sends you a notification when the price drops!",
        "how can i track price": "Save your favorite product and enable price alerts – we’ll notify you when it’s cheaper!",
        "is price tracking automatic": "Yes, once you save a product, ProDex automatically tracks its price changes for you.",

        # Account & Support
        "do i need an account": "You can explore without an account, but signing up lets you save products, get alerts, and use try-on.",
        "how to create account": "Just click on the ‘Sign Up’ button at the top right and enter your details – it takes only a minute!",
        "i need help": "No problem! You can visit our Help Center or type your question here – I’ll try to assist you 😊",
        "contact support": "You can contact our support team via the ‘Contact Us’ page or email support@prodex.ai.",

        # Farewell
        "bye": "Goodbye! 👋 Hope you find the perfect product today!",
        "thank you": "You’re welcome! 😊 Happy shopping with ProDex!",
    }

    # Extract keywords from complex inputs (e.g., "how is the virtual try on working")
    # This loop is added to find a keyword match for multi-word phrases.
    for key, response in responses.items():
        if key in user_input and len(key) > 3: # Prioritize longer, more specific keywords
             return response

    # Final keyword check for exact match
    return responses.get(
        user_input,
        "Hmm 🤔 I’m not sure I understand that. Could you please rephrase or try asking about a ProDex feature?"
    )

@app.route("/", methods=["GET", "POST"])
def index():
    products = []
    prodDes = ""
    uploaded_file = None
    sites_to_search = []
    sort_by = "relevance" 
    
    if 'wishlist' not in session:
        session['wishlist'] = {}
    
    if request.method == "POST":
        
        uploaded_file = request.files.get('image_upload')
        
        if uploaded_file and uploaded_file.filename != '':
            products, visual_query = search_by_image(uploaded_file.stream, uploaded_file.filename)
            prodDes = visual_query 
        else:
            prodDes = request.form.get("product", "")


        raw_selected_platforms = request.form.getlist("platforms")
        sites_to_search = []
        
        if "others" in raw_selected_platforms:
            sites_to_search.extend(OTHER_SITES)
            
        sites_to_search.extend([p for p in raw_selected_platforms if p != 'others'])
        sites_to_search = list(set(sites_to_search))
        
        if not sites_to_search and (prodDes or uploaded_file): 
             sites_to_search = MASTER_SITES


        final_selected_platforms_for_template = raw_selected_platforms


        if not uploaded_file and prodDes:
            products = search_products(prodDes, sites_to_search)
            
        # PRICE FILTERING LOGIC
        max_price_str = request.form.get("max_price")
        max_price_filter = None
        try:
            if max_price_str:
                max_price_filter = float(max_price_str)
        except ValueError:
            max_price_filter = None
        
        if max_price_filter is not None and max_price_filter > 0:
            filtered_products = []
            for p in products:
                if p.get('numeric_price') is not None and p['numeric_price'] <= max_price_filter:
                    filtered_products.append(p)
            products = filtered_products 


        # SORTING LOGIC
        sort_by = request.form.get("sort_by", "relevance") 
        if sort_by.startswith('price'):
            reverse_sort = (sort_by == 'price_desc')
            
            products.sort(
                key=lambda p: (
                    p.get('numeric_price') is None,
                    p.get('numeric_price') or 0
                ),
                reverse=reverse_sort
            )
        
    else:
        final_selected_platforms_for_template = []
        max_price_filter = 1000 # Default range value for GET
        sort_by = "relevance" 
    
    print("-" * 50)
    print(f"FLASK DEBUG: Current Product Query: '{prodDes}'")
    print(f"FLASK DEBUG: Number of Products Found: {len(products)}")
    print("-" * 50)

    return render_template(
        "index.html",
        products=products,
        current_search_query=prodDes,
        selected_platforms=final_selected_platforms_for_template,
        sort_by=sort_by,
        max_price_filter=max_price_filter,
        wishlist_count=len(session.get('wishlist', {}))
    )

# --- Virtual Try-On Route: CORRECTED Implementation ---
@app.route("/try-on/<string:product_id>", methods=["POST"])
def try_on(product_id):
    if 'user_image' not in request.files or not request.files['user_image'].filename:
        return "No user image uploaded", 400

    user_file = request.files['user_image']
    product_image_url = request.form.get('product_image_url')
    if not product_image_url:
        return "No product image URL provided", 400

    session_prefix = f"try-on-sessions/{uuid.uuid4()}/"
    person_filename = f"{session_prefix}person.jpg"
    item_filename = f"{session_prefix}item.jpg"

    bucket = storage_client.bucket(BUCKET_NAME)

    # 1. Upload User Image
    person_blob = bucket.blob(person_filename)
    user_file.stream.seek(0)
    person_blob.upload_from_file(user_file.stream, content_type=user_file.content_type or 'image/jpeg') 
    
    # 2. Download and Upload Product Image
    try:
        item_response = requests.get(product_image_url, stream=True)
        item_response.raise_for_status()
        item_blob = bucket.blob(item_filename)
        content_type = item_response.headers.get('content-type', 'image/jpeg') 
        item_blob.upload_from_file(item_response.raw, content_type=content_type)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not fetch product image URL: {e}")
        person_blob.delete()
        return "Failed to download product image for try-on.", 500

    print(f"🟢 Uploaded session files to: gs://{BUCKET_NAME}/{session_prefix}")

    # 3. VTO API Call Setup
    VTO_MODEL_ENDPOINT = f"https://{LOCATION}-aiplatform.googleapis.com/v1/projects/{PROJECT_ID}/locations/{LOCATION}/publishers/google/models/virtual-try-on-preview-08-04:predict"
    payload = {
        "instances": [
            {
                "personImage": {"image": {"gcsUri": f"gs://{BUCKET_NAME}/{person_filename}"}},
                "productImages": [{"image": {"gcsUri": f"gs://{BUCKET_NAME}/{item_filename}"}}]
            }
        ],
        "parameters": {
            "sampleCount": 1,
            "storageUri": f"gs://{BUCKET_NAME}/{session_prefix}output/"
        }
    }
    
    # 4. Get Auth Token
    credentials = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_PATH, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    credentials.refresh(Request())
    access_token = credentials.token
    headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

    # 5. Send Prediction Request
    response = requests.post(VTO_MODEL_ENDPOINT, headers=headers, json=payload)

    if response.status_code != 200:
        print(f"VTO API FAILED: {response.text}")
        person_blob.delete()
        item_blob.delete()
        return f"Virtual Try-On API call failed: {response.status_code} - {response.text[:100]}", 500

    # 6. Polling for Output File (FIX: Increased Timeout to 60s and robust file search)
    output_prefix = f"{session_prefix}output/"
    max_wait_time = 60 # Increased timeout
    wait_time = 0
    output_image_blob_name = None
    
    while wait_time < max_wait_time: 
        # List blobs with the specific output prefix
        blobs = storage_client.list_blobs(BUCKET_NAME, prefix=output_prefix)
        
        # Check for any generated image (usually 0.png or sample_0.png in the folder)
        for blob in blobs:
            if blob.name.endswith('.png'):
                output_image_blob_name = blob.name
                break
        
        if output_image_blob_name:
            break
            
        time.sleep(2)
        wait_time += 2

    # 7. Final Check and Cleanup
    if not output_image_blob_name:
        print(f"Try-On generation timed out after {max_wait_time} seconds.")
        person_blob.delete()
        item_blob.delete()
        return "Try-On generation timed out", 500

    generated_image_url = f"https://storage.googleapis.com/{BUCKET_NAME}/{output_image_blob_name}"

    return render_template("try_on_result.html", generated_image_url=generated_image_url)


# --- NEW CHATBOT API ROUTE ---
@app.route("/api/chat", methods=["POST"])
def chat_api():
    """Endpoint for the chatbot. Uses the actual chatbot_response function."""
    data = request.json
    user_message = data.get("message", "")
    
    if not user_message:
        return jsonify({"status": "error", "reply": "No message received"}), 400
    
    try:
        # Use the actual chatbot function
        bot_reply = chatbot_response(user_message)
    except Exception as e:
        bot_reply = "Sorry, the support system failed to process your request."
        print(f"Chatbot error: {e}")
        
    return jsonify({"status": "success", "reply": bot_reply})
# -----------------------------


# --- Wishlist Routes (Unchanged) ---
@app.route("/wishlist/add/<int:product_id>", methods=["POST"])
def add_to_wishlist(product_id):
    product_title = request.json.get('title', f'Product {product_id}')
    product_link = request.json.get('link', '#') 
    product_price = request.json.get('price', 'N/A') 
    wishlist = session.get('wishlist', {})
    product_id_str = str(product_id)
    if product_id_str not in wishlist:
        wishlist[product_id_str] = {'title': product_title, 'link': product_link, 'price': product_price, 'added_time': time.time()}
        session['wishlist'] = wishlist 
        return jsonify({"status": "success", "message": "Product added.", "count": len(session['wishlist'])})
    else:
        return jsonify({"status": "warning", "message": "Product is already in your wishlist."})

@app.route("/wishlist/remove/<string:product_id>", methods=["POST"])
def remove_from_wishlist(product_id):
    wishlist = session.get('wishlist', {})
    if product_id in wishlist:
        del wishlist[product_id]  
        session['wishlist'] = wishlist 
        return jsonify({"status": "success", "message": "Item removed from wishlist.", "count": len(session['wishlist'])})
    else:
        return jsonify({"status": "error", "message": "Item not found in wishlist."})
    
@app.route("/wishlist")
def view_wishlist():
    def timestamp_to_datetime(timestamp):
        return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    items = session.get('wishlist', {})
    display_items = []
    for id, item in items.items():
        display_items.append({'id': id, 'title': item['title'], 'link': item['link'], 'price': item['price'], 'added_time': timestamp_to_datetime(item['added_time'])})
    return render_template('wishlist.html', items=display_items)

@app.route("/login-choice")
def login_choice():
    return render_template("login_choice.html")  # or whatever login template you use


@app.route('/profile')
def profile():
    if 'user_name' not in session:
        flash("Please log in first.", "warning")
        return redirect(url_for('login'))
    return render_template('profile.html', user_name=session['user_name'])


# ---------------------- LOGIN ----------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        try:
            # Fetch user from DynamoDB
            response = users_table.get_item(Key={'email': email})
            user = response.get('Item')

            if user and check_password_hash(user['password'], password):
                # Successful login
                session['user_email'] = user['email']
                session['user_name'] = user['email']  # Use email as display name
                flash("Login successful!", "success")
                return redirect(url_for('index'))
            else:
                # Invalid credentials
                error = "Invalid email or password. Please try again."

        except ClientError as e:
            error = f"Database error: {e.response['Error']['Message']}"

    return render_template('login.html', error=error)


# ---------------------- SIGNUP ----------------------
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    error = None

    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']
        hashed_password = generate_password_hash(password)

        try:
            # Check if user already exists
            existing_user = users_table.get_item(Key={'email': email})
            if 'Item' in existing_user:
                flash("User already exists. Please log in instead.", "warning")
                return redirect(url_for('login'))

            # Create a new user record in DynamoDB
            users_table.put_item(
                Item={
                    'email': email,
                    'password': hashed_password
                }
            )

            # Auto-login after signup
            session['user_email'] = email
            session['user_name'] = email  # Use email as display name
            flash("Account created successfully! You are now logged in.", "success")

            return redirect(url_for('index'))

        except ClientError as e:
            error = f"Error creating user: {e.response['Error']['Message']}"

    return render_template('signup.html', error=error)


# ---------------------- LOGOUT ----------------------
@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out successfully.", "success")
    return redirect(url_for('index'))

@app.route('/about')
def about():
    return render_template('about.html')


# --- RUN BLOCK ---

#if __name__ == "__main__":
 #   app.run(
  #      host="0.0.0.0",
   #     port=443,
    #    ssl_context=(
     #       '/etc/letsencrypt/live/bharghav.tech/fullchain.pem',
      #      '/etc/letsencrypt/live/bharghav.tech/privkey.pem'
       # )
    #)

