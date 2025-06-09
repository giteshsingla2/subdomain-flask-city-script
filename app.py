import random
from flask import Flask, render_template, request, abort, jsonify, Response
from flask_caching import Cache
import os
import json
import sqlite3
from datetime import datetime
from markupsafe import Markup
import urllib.parse

app = Flask(__name__,
                template_folder="templates")

# Configure Flask-Caching
cache = Cache(app, config={
        'CACHE_TYPE': 'SimpleCache',
        'CACHE_DEFAULT_TIMEOUT': 0  # Never expire cache
    })

# Database cache initialization
class DatabaseCache:
    def __init__(self):
        self.states = {}
        self.cities = {}
        self.zip_codes = {}
        self._load_data()
    def _load_data(self):
        with sqlite3.connect('newcities.db') as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Initialize database structure
            cursor.execute("DROP TABLE IF EXISTS Cities")
            
            cursor.execute("""
                CREATE TABLE Cities (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  city_name TEXT NOT NULL,
                  state_code TEXT NOT NULL,
                  state_name TEXT NOT NULL,
                  main_zip_code TEXT NOT NULL,
                  zip_codes TEXT NOT NULL
                )
            """)
            # Prepare statement for inserting cities
            insert_stmt = "INSERT INTO Cities (city_name, state_code, state_name, main_zip_code, zip_codes) VALUES (?, ?, ?, ?, ?)"

            # Load cities with their states
            cursor.execute("SELECT city_name, state_code, state_name, main_zip_code, zip_codes FROM Cities")
            for row in cursor.fetchall():
                if row['state_code'] not in self.cities:
                    self.cities[row['state_code']] = []
                self.cities[row['state_code']].append(row['city_name'])
                # Load zip codes
                city_name = row['city_name'].lower()
                if city_name not in self.zip_codes:
                    self.zip_codes[city_name] = []
                zip_codes_list = row['zip_codes'].split(',')
                for zip_code in zip_codes_list:
                    self.zip_codes[city_name].append(zip_code.strip())

    # Initialize database cache at startup
db_cache = DatabaseCache()

@cache.memoize(timeout=300)
def load_json(filename):
    with open(filename, 'r') as f:
        return json.load(f)

def get_main_domain():
    host = request.host
    main_domain = ".".join(host.split('.')[-2:])
    return main_domain

def load_json_for_request():
    main_domain = get_main_domain()
    domain_path = f"domains/{main_domain}/"
    json_paths = {
        "maincontent": os.path.join(domain_path, "maincontent.json"),
        "required": os.path.join(domain_path, "required.json"),
        "services": os.path.join(domain_path, "services.json"),
        }

    json_data = {}

    for key, path in json_paths.items():
        try:
            json_data[key] = load_json(path)
        except Exception as e:
                print(f"Error loading {key} data from {path}: {e}")
                json_data[key] = {}  # Set to empty dict on error

    return json_data

def replace_placeholders(text, service_name, city_name, state_abbreviation, state_full_name, required_data, zip_codes=[], city_zip_code=""):
    import re
    pattern = r'\{([^}]*)\}'
    def random_replacer(match):
        options = match.group(1).split('|')
        return random.choice(options)
        
    # Step 1: Replace random choice patterns
    text = re.sub(pattern, random_replacer, text)

    # Step 2: Replace placeholders

    text = text.replace("[Service]", service_name)\
                .replace("[service]", service_name.lower())\
                .replace("[City-State]", f"{city_name}, {state_abbreviation}")\
                .replace("[city-state]", f"{city_name.lower()}, {state_abbreviation.lower()}")\
                .replace("[City]", city_name)\
                .replace("[city]", city_name.lower())\
                .replace("[CITY]", city_name.upper())\
                .replace("[State]", state_abbreviation)\
                .replace("[state]", state_abbreviation.lower())\
                .replace("[STATE]", state_abbreviation.upper())\
                .replace("[State Full]", state_full_name)\
                .replace("[Phone No.]", required_data.get("Phone No. Placeholder", "N/A"))\
                .replace("[Company Name]", required_data.get("Company Name", "N/A"))\
                .replace("[City Zip Code]", city_zip_code)\
                .replace("[Zip Codes]", ", ".join(str(z) for z in zip_codes if z))
    return text

def get_db_connection():
    conn = sqlite3.connect('newcities.db')
    conn.row_factory = sqlite3.Row
    return conn

@cache.memoize(timeout=86400)  # Cache for 1 day
def get_state_full_name(state_abbr):
    return db_cache.states.get(state_abbr)

@cache.memoize(timeout=86400)  # Cache for 1 day
def state_exists(state_abbr):
    return state_abbr in db_cache.states

@cache.memoize(timeout=86400)  # Cache for 1 day
def get_cities_in_state(state_abbr):
    return db_cache.cities.get(state_abbr, [])

def get_city_info(city_subdomain, state_abbr):
    conn = get_db_connection()
    cursor = conn.cursor()
    city_subdomain_normalized = city_subdomain.replace('-', ' ').lower()
    cursor.execute(
        "SELECT * FROM Cities WHERE city_name = ? AND state_code = ?",
        (state_abbr, city_subdomain_normalized)
    )
    city_row = cursor.fetchone()
    conn.close()
    if city_row:
        return {'city_name': city_row['city_name'], 'zip_code': city_row['zip_code']}
    else:
        return None

def get_states():
    return list(db_cache.states.keys())

def get_service_content(service_url, city_name, state_abbreviation, state_full_name, json_data, zip_codes, city_zip_code):
    # Find the service by its slug from the new services.json structure
        current_service_data = next((s for s in json_data.get("services", {}).get("Services", []) if s.get("slug") == service_url), None)

        if current_service_data:
            required_data = json_data.get("required", {})
            service_name_for_placeholders = current_service_data.get("Service Name", "")

            # Prepare FAQ for the specific service
            service_faqs = []
            if current_service_data.get("FAQ"):
                for faq_item in current_service_data["FAQ"]:
                    service_faqs.append({
                        "Question": replace_placeholders(faq_item.get("Question", ""), service_name_for_placeholders, city_name, state_abbreviation, state_full_name, required_data, zip_codes, city_zip_code),
                        "Answer": Markup(replace_placeholders(faq_item.get("Answer", ""), service_name_for_placeholders, city_name, state_abbreviation, state_full_name, required_data, zip_codes, city_zip_code))
                    })

            # Prepare Reviews for the specific service
            service_reviews = []
            if current_service_data.get("Reviews"):
                for review_item in current_service_data["Reviews"]:
                    service_reviews.append({
                        "name": review_item.get("name"),
                        "review": Markup(replace_placeholders(review_item.get("review", ""), service_name_for_placeholders, city_name, state_abbreviation, state_full_name, required_data, zip_codes, city_zip_code))
                    })
            
            # Process other text fields with placeholders
            processed_service_data = {}
            for key, value in current_service_data.items():
                if isinstance(value, str):
                    processed_service_data[key] = Markup(replace_placeholders(value, service_name_for_placeholders, city_name, state_abbreviation, state_full_name, required_data, zip_codes, city_zip_code))
                elif key not in ["FAQ", "Reviews"]: # Avoid re-processing FAQ and Reviews
                    processed_service_data[key] = value

            # Ensure essential keys are present, even if empty, and add processed FAQs and Reviews
            service_content = {
                "Title": processed_service_data.get("Title", ""),
                "Service Name": processed_service_data.get("Service Name", ""),
                "slug": current_service_data.get("slug", ""), # slug doesn't need placeholder replacement
                "Meta Description": processed_service_data.get("Meta Description", ""),
                "Blog Content": processed_service_data.get("Blog Content", ""), # Assuming Blog Content is a string that needs replacement
                "CTA": processed_service_data.get("CTA", ""), # Assuming CTA is a string that needs replacement
                "FAQ": service_faqs, # Use already processed FAQs
                "Reviews": service_reviews, # Use already processed Reviews
                # Add any other fields from services.json that service.html might need
                # For example, if there are specific images, etc.
            }
            return service_content
        return None

def get_random_faqs(city_name, state_abbreviation, json_data, zip_codes, city_zip_code):
    required_data = json_data["required"]
    selected_faqs = random.sample(json_data["faq"]["faqs"], 5)
    for faq in selected_faqs:
        faq["question"] = Markup(replace_placeholders(
            faq["question"],
                "",
                city_name,
                state_abbreviation,
                "",
                required_data,
                zip_codes,
                city_zip_code
            ))
        faq["answer"] = Markup(replace_placeholders(
                faq["answer"],
                "",
                city_name,
                state_abbreviation,
                "",
                required_data,
                zip_codes,
                city_zip_code
            ))
    return selected_faqs

def get_zip_codes_from_db(city_name):
    return db_cache.zip_codes.get(city_name.lower(), [])

def get_canonical_url():
    return f"https://{request.host}{request.path}"

def get_current_month_year():
    now = datetime.now()
    return {
        "month": now.strftime("%B"),
        "year": now.strftime("%Y")
    }

@app.before_request
def before_request():
    request.json_data = load_json_for_request()

@app.context_processor
def inject_date():
    return get_current_month_year()

def get_other_cities_in_state(state_abbr, current_city_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT city_name FROM Cities
        WHERE state_abbr = ? AND LOWER(city_name) != LOWER(?)
            ORDER BY city_name ASC
        """, (state_abbr, current_city_name.lower()))
    cities = [row['city_name'] for row in cursor.fetchall()]
    conn.close()
    return cities

@app.route('/')
def handle_home():
    host = request.host
    json_data = request.json_data
    required_data = json_data["required"]
    if host in [get_main_domain(), f"www.{get_main_domain()}"]:
        states = get_states()
        state_links = {state: f"https://{state}.{get_main_domain()}" for state in states}
        return render_template(
            'home.html',
            state_links=state_links,
            required=required_data,
            favicon=required_data.get("favicon"),
            main_service=required_data.get("Main Service"),
            company_name=required_data.get("Company Name")
        )    
    else:
        subdomains = host.split('.')[0].split('-')
        if len(subdomains) == 1:
            state_subdomain = subdomains[0]
            if state_exists(state_subdomain):
                state_name = get_state_full_name(state_subdomain)
                cities = get_cities_in_state(state_subdomain)
                city_links = {
                        city.replace(' ', '-'): f"https://{city.replace(' ', '-')}-{state_subdomain}.{get_main_domain()}"
                        for city in cities
                    }
                return render_template(
                        'state.html',
                        state_name=state_name,
                        city_links=city_links,
                        required=required_data,
                        favicon=required_data.get("favicon"),
                        main_service=required_data.get("Main Service"),
                        company_name=required_data.get("Company Name")
                    )
            else:
                abort(404)
        elif len(subdomains) >= 2:
            city_subdomain = '-'.join(subdomains[:-1])
            state_subdomain = subdomains[-1]
            city_info = get_city_info(city_subdomain, state_subdomain)
            if city_info:
                city_name = city_info['city_name'].title()
                city_zip_code = city_info['zip_code']
                state_name = get_state_full_name(state_subdomain)
                state_abbreviation = state_subdomain.upper()
                zip_codes = get_zip_codes_from_db(city_name)

                # Load maincontent data
                main_content_data = json_data.get("maincontent", {})

                meta_title = replace_placeholders(
                        main_content_data.get("Title", required_data.get("Meta Title", "")) or f"{required_data.get('Main Service', '')} in {city_name}, {state_abbreviation}",
                        "",
                        city_name,
                        state_abbreviation,
                        state_name,
                        required_data,
                        zip_codes,
                        city_zip_code
                    )

                meta_description = replace_placeholders(
                        main_content_data.get("Meta Description", required_data.get("Meta Description", "")) or f"Get the best {required_data.get('Main Service', '')} in {city_name}, {state_abbreviation}. Contact us today!",
                        "",
                        city_name,
                        state_abbreviation,
                        state_name,
                        required_data,
                        zip_codes,
                        city_zip_code
                    )

                # Prepare services data for the template
                services_list_for_template = []
                if json_data.get("services") and json_data["services"].get("Services"):
                    for service_item in json_data["services"]["Services"]:
                        services_list_for_template.append({
                            "name": service_item.get("Service Name"),
                                "url": f"https://{city_subdomain}-{state_subdomain}.{get_main_domain()}/{service_item.get('slug')}",
                                # Add other service details if needed by city.html, like a short description
                            })

                # Prepare FAQ from maincontent
                faqs_from_maincontent = []
                if main_content_data.get("FAQ"):
                    for faq_item in main_content_data["FAQ"]:
                        faqs_from_maincontent.append({
                            "Question": replace_placeholders(faq_item.get("Question", ""), "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code),
                                "Answer": Markup(replace_placeholders(faq_item.get("Answer", ""), "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code))
                            })

                # Prepare Reviews from maincontent
                reviews_from_maincontent = []
                if main_content_data.get("Reviews"):
                    for review_item in main_content_data["Reviews"]:
                        reviews_from_maincontent.append({
                            "name": review_item.get("name"),
                                "review": Markup(replace_placeholders(review_item.get("review", ""), "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code))
                            })
                    
                # Placeholder replacements for main_content_data fields
                processed_main_content = {}
                for key, value in main_content_data.items():
                    if isinstance(value, str):
                        processed_main_content[key] = Markup(replace_placeholders(value, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code))
                    else:
                            processed_main_content[key] = value # Keep lists/dicts as is (e.g. FAQ, Reviews already processed)

                # Fetch other cities in the same state
                all_other_cities = get_other_cities_in_state(state_subdomain, city_info['city_name'])
                other_city_links = []
                if len(all_other_cities) > 0:
                        city_index = sum(ord(char) for char in city_info['city_name']) % len(all_other_cities)
                        rotated_cities = all_other_cities[city_index:] + all_other_cities[:city_index]
                        other_cities_to_display = rotated_cities[:10]
                        for city in other_cities_to_display:
                            city_subdomain_format = urllib.parse.quote(city.replace(' ', '-').lower())
                            city_link = f"https://{city_subdomain_format}-{state_subdomain}.{get_main_domain()}"
                            other_city_links.append({
                                'name': city,
                                'link': city_link
                            })

                return render_template(
                    'city.html',
                    state_name=state_name,
                    city_name=city_name,
                    city_zip_code=city_zip_code,
                    required=required_data,
                    main_content=processed_main_content, # Pass processed main_content_data
                    services_list=services_list_for_template, # Pass the list of services
                    faqs=faqs_from_maincontent, # Pass FAQs from maincontent
                    reviews=reviews_from_maincontent, # Pass Reviews from maincontent
                    meta_title=meta_title,
                    meta_description=meta_description,
                    canonical_url=get_canonical_url(),
                    favicon=required_data.get("Favicon"),
                    company_name=required_data.get("Business Name"),
                    zip_codes=zip_codes,
                    other_city_links=other_city_links
                )
                
            else:
                abort(404)
        abort(404)

@app.route('/<service_url>')
def service_page(service_url):
    host = request.host
    json_data = request.json_data
    required_data = json_data.get("required", {}) # Use .get for safety
    subdomains = host.split('.')[0].split('-')
    if len(subdomains) >= 2:
        city_subdomain = '-'.join(subdomains[:-1])
        state_subdomain = subdomains[-1]
        city_info = get_city_info(city_subdomain, state_subdomain)
        if city_info and state_exists(state_subdomain):
            city_name = city_info['city_name'].title()
            city_zip_code = city_info['zip_code']
            state_name = get_state_full_name(state_subdomain)
            state_abbreviation = state_subdomain.upper()
            zip_codes = get_zip_codes_from_db(city_name)
            
            # Call the refactored get_service_content
            service_content = get_service_content(
                service_url,
                city_name,
                state_abbreviation,
                state_name,
                json_data,
                zip_codes,
                city_zip_code
            )

            if service_content:
                service_name_for_placeholders = service_content.get("Service Name", "")

                # Use Title from service_content if available, otherwise construct a default
                meta_title_template = service_content.get("Title") or f"{service_name_for_placeholders} in {{city_name}}, {{state_abbreviation}}"
                meta_title = replace_placeholders(
                        meta_title_template,
                        service_name_for_placeholders,
                        city_name,
                        state_abbreviation,
                        state_name,
                        required_data,
                        zip_codes,
                        city_zip_code
                    )

                # Use Meta Description from service_content if available, otherwise construct a default
                meta_description_template = service_content.get("Meta Description") or f"Get the best {service_name_for_placeholders} in {{city_name}}, {{state_abbreviation}}. Contact us today!"
                meta_description = replace_placeholders(
                    meta_description_template,
                    service_name_for_placeholders,
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    city_zip_code
                )

                return render_template(
                    'service.html',
                    state_name=state_name,
                    city_name=city_name,
                    city_zip_code=city_zip_code,
                    service=service_content,  # Pass the whole processed service_content dictionary
                    meta_title=meta_title,
                    meta_description=meta_description,
                    required=required_data,
                    canonical_url=get_canonical_url(),
                    favicon=required_data.get("Favicon"), # Updated key
                    main_service=required_data.get("Main Service"), 
                    company_name=required_data.get("Business Name"), # Updated key
                    zip_codes=zip_codes
                    )
        abort(404)

@app.route('/about')
def about_page():
    host = request.host
    json_data = request.json_data
    required_data = json_data.get("required", {})
    main_content_data = json_data.get("maincontent", {})
    subdomains = host.split('.')[0].split('-')

    if len(subdomains) >= 2: # City-State specific page
        city_subdomain = '-'.join(subdomains[:-1])
        state_subdomain = subdomains[-1]
        city_info = get_city_info(city_subdomain, state_subdomain)

        if city_info and state_exists(state_subdomain):
            city_name = city_info['city_name'].title()
            city_zip_code = city_info['zip_code']
            state_name = get_state_full_name(state_subdomain)
            state_abbreviation = state_subdomain.upper()
            zip_codes = get_zip_codes_from_db(city_name)

            about_us_content_template = main_content_data.get("About Content", "")
            why_choose_us_content_template = main_content_data.get("Why Choose Us Content", "")

            about_us_content = Markup(replace_placeholders(
                about_us_content_template, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
            ))
            why_choose_us_content = Markup(replace_placeholders(
                why_choose_us_content_template, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
            ))

            meta_title_template = main_content_data.get("About Page Title", main_content_data.get("Title", "About Us - {company_name} in {city_name}, {state_abbreviation}"))
            meta_title = replace_placeholders(
                meta_title_template, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
            )

            meta_description_template = main_content_data.get("About Page Meta Description", main_content_data.get("Meta Description", "Learn more about {company_name} and why we are the best choice in {city_name}."))
            meta_description = replace_placeholders(
                meta_description_template, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
                )

            return render_template(
                'about.html', 
                state_name=state_name,
                city_name=city_name,
                city_zip_code=city_zip_code,
                required=required_data,
                about_us_content=about_us_content,
                why_choose_us_content=why_choose_us_content,
                meta_title=meta_title,
                meta_description=meta_description,
                canonical_url=get_canonical_url(),
                favicon=required_data.get("Favicon"),
                company_name=required_data.get("Business Name"),
                zip_codes=zip_codes
                )
        abort(404)

@app.route('/contact')
def contact_page():
    host = request.host
    json_data = request.json_data
    required_data = json_data.get("required", {})
    main_content_data = json_data.get("maincontent", {})
    subdomains = host.split('.')[0].split('-')

    if len(subdomains) >= 2: # City-State specific page
        city_subdomain = '-'.join(subdomains[:-1])
        state_subdomain = subdomains[-1]
        city_info = get_city_info(city_subdomain, state_subdomain)

        if city_info and state_exists(state_subdomain): # Added state_exists check for consistency
            city_name = city_info['city_name'].title()
            city_zip_code = city_info['zip_code']
            state_name = get_state_full_name(state_subdomain)
            state_abbreviation = state_subdomain.upper()
            zip_codes = get_zip_codes_from_db(city_name)

            # Use Address from required.json directly if available, otherwise use template
            # Assuming 'Address' in required.json is a pre-formatted string or a structured object
            # For this example, let's assume 'Address' in required.json is the string to use.
            # If it's a template like before, the old logic can be adapted.
            address = replace_placeholders(
                required_data.get('Address', f"{{company_name}}\n{{city_name}}, {{state_abbreviation}} {{zip_code}}"),
                "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
                )

            meta_title_template = main_content_data.get("Contact Page Title", main_content_data.get("Title", "Contact {company_name} in {city_name}, {state_abbreviation}"))
            meta_title = replace_placeholders(
                meta_title_template, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
                )
                
            meta_description_template = main_content_data.get("Contact Page Meta Description", main_content_data.get("Meta Description", "Contact {company_name} for {main_service} services in {city_name}. Get a free quote today!"))
            meta_description = replace_placeholders(
                meta_description_template, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
                )

            contact_cta_template = main_content_data.get("CTA", {}).get("Text", "Reach out to us for expert advice and service.")
            contact_cta = Markup(replace_placeholders(
                contact_cta_template, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
                ))

            return render_template(
                'contact.html',
                state_name=state_name,
                city_name=city_name,
                city_zip_code=city_zip_code,
                required=required_data, # Contains Phone, Email, Business Name, etc.
                    address=Markup(address.replace('\n', '<br>')) if address else None, # Pass formatted address
                    contact_cta=contact_cta,
                meta_title=meta_title,
                meta_description=meta_description,
                canonical_url=get_canonical_url(),
                favicon=required_data.get("Favicon"),
                company_name=required_data.get("Business Name"),
                zip_codes=zip_codes
                )
        abort(404)

@app.route('/services')
def services_page():
        host = request.host
        json_data = request.json_data
        required_data = json_data.get("required", {})
        main_content_data = json_data.get("maincontent", {})
        services_data = json_data.get("services", []) # services.json is a list of services
        subdomains = host.split('.')[0].split('-')

        if len(subdomains) >= 2: # City-State specific page
            city_subdomain = '-'.join(subdomains[:-1])
            state_subdomain = subdomains[-1]
            city_info = get_city_info(city_subdomain, state_subdomain)

            if city_info and state_exists(state_subdomain):
                city_name = city_info['city_name'].title()
                city_zip_code = city_info['zip_code']
                state_name = get_state_full_name(state_subdomain)
                state_abbreviation = state_subdomain.upper()
                zip_codes = get_zip_codes_from_db(city_name)

                services_list = []
                for service_item in services_data:
                    service_name = service_item.get("Service Name")
                    service_slug = service_item.get("slug")
                    if service_name and service_slug:
                        # Apply placeholder replacement to service name if needed, though typically not for a listing
                        # For this example, we'll assume the Service Name in services.json is final
                        services_list.append({
                            "name": service_name,
                            "url": f"/{service_slug}" # Construct URL from slug
                        })

                meta_title_template = main_content_data.get("Services Page Title", main_content_data.get("Title", "Our Services in {city_name}, {state_abbreviation} - {company_name}"))
                meta_title = replace_placeholders(
                    meta_title_template, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
                )
                
                meta_description_template = main_content_data.get("Services Page Meta Description", main_content_data.get("Meta Description", "Explore the range of services offered by {company_name} in {city_name}. Contact us for more information."))
                meta_description = replace_placeholders(
                    meta_description_template, "", city_name, state_abbreviation, state_name, required_data, zip_codes, city_zip_code
                )

                return render_template(
                    'services.html',
                    state_name=state_name,
                    city_name=city_name,
                    city_zip_code=city_zip_code,
                    services_list=services_list,
                    meta_title=meta_title,
                    meta_description=meta_description,
                    required=required_data,
                    canonical_url=get_canonical_url(),
                    favicon=required_data.get("Favicon"), # Corrected key
                    company_name=required_data.get("Business Name"), # Corrected key
                    zip_codes=zip_codes
                )
        abort(404)

@app.route('/update-json/<filename>', methods=['POST'])
def update_json(filename):
    try:
        main_domain = get_main_domain()
        data = request.get_json()
        filepath = f"/var/www/yourapp/domains/{main_domain}/{filename}"
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=4)
        return jsonify({"status": "success", "message": f"{filename} updated successfully!"}), 200
    except Exception as e:
        return jsonify({"status": "failure", "message": str(e)}), 500

@app.errorhandler(404)
def page_not_found(e):
    required_data = request.json_data.get("required", {})
    return render_template(
        '404.html',
        required=required_data,
        favicon=required_data.get("favicon"),
        main_service=required_data.get("Main Service"),
        company_name=required_data.get("Company Name")
    ), 404

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8000)