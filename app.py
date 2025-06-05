import random
from flask import Flask, render_template, request, abort, jsonify
import os
import json
import sqlite3
from datetime import datetime
from markupsafe import Markup  # Import Markup from markupsafe
import urllib.parse

app = Flask(__name__,
            template_folder="/var/www/yourapp/shared/templates",
            static_folder="/var/www/yourapp/shared/static")

def load_json(filename):
    with open(filename, 'r') as f:
        return json.load(f)

def get_main_domain():
    host = request.host
    main_domain = ".".join(host.split('.')[-2:])
    return main_domain

def load_json_for_request():
    main_domain = get_main_domain()
    domain_path = f"/var/www/yourapp/domains/{main_domain}/"
    json_paths = {
        "services": os.path.join(domain_path, "services.json"),
        "about": os.path.join(domain_path, "about.json"),
        "faq": os.path.join(domain_path, "faq.json"),
        "reviews": os.path.join(domain_path, "reviews.json"),
        "required": os.path.join(domain_path, "required.json"),
        "citycontent": os.path.join(domain_path, "citycontent.json")
    }

    json_data = {}

    for key, path in json_paths.items():
        try:
            json_data[key] = load_json(path)
        except Exception as e:
            print(f"Error loading {key} data from {path}: {e}")
            json_data[key] = {}  # Set to empty dict on error

    return json_data

def replace_placeholders(text, service_name, city_name, state_abbreviation, state_full_name, required_data, zip_codes=[], neighborhoods=[], city_zip_code=""):
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
               .replace("[Zip Codes]", ", ".join(zip_codes))\
               .replace("[Neighborhoods]", ", ".join([n['name'] for n in neighborhoods]))\
               .replace("[zipcode]", city_zip_code)
    return text

def get_db_connection():
    conn = sqlite3.connect('/var/www/yourapp/locations.db')
    conn.row_factory = sqlite3.Row
    return conn
def get_state_full_name(state_abbr):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT state_name FROM States WHERE state_abbr = ?", (state_abbr,))
    state_row = cursor.fetchone()
    conn.close()
    if state_row:
        return state_row['state_name']
    else:
        return None

def state_exists(state_abbr):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM States WHERE state_abbr = ?", (state_abbr,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists

def get_cities_in_state(state_abbr):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT city_name FROM Cities WHERE state_abbr = ?", (state_abbr,))
    cities = [row['city_name'] for row in cursor.fetchall()]
    conn.close()
    return cities

def get_city_info(city_subdomain, state_abbr):
    conn = get_db_connection()
    cursor = conn.cursor()
    city_subdomain_normalized = city_subdomain.replace('-', ' ').lower()
    cursor.execute(
        "SELECT city_name, zip_code FROM Cities WHERE state_abbr = ? AND LOWER(city_name) = ?",
        (state_abbr, city_subdomain_normalized)
    )
    city_row = cursor.fetchone()
    conn.close()
    if city_row:
        return {'city_name': city_row['city_name'], 'zip_code': city_row['zip_code']}
    else:
        return None

def get_states():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT state_abbr, state_name FROM States")
    states = cursor.fetchall()
    conn.close()
    return states

def get_zip_codes_from_db(city_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT zip_code FROM CityZipCodes WHERE LOWER(city_name) = LOWER(?)", (city_name.lower(),))
    zip_codes = [row['zip_code'] for row in cursor.fetchall()]
    conn.close()
    return zip_codes

def get_neighborhoods_from_db(city_name):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT neighborhood FROM Neighborhoods WHERE LOWER(city_name) = LOWER(?)", (city_name.lower(),))
    neighborhoods = [row['neighborhood'] for row in cursor.fetchall()]
    conn.close()
    return neighborhoods
def generate_map_embed(city_name, state_name):
    location = f"{city_name.replace(' ', '+')},{state_name.replace(' ', '+')},US"
    map_url = f"https://www.google.com/maps?q={location}&output=embed"
    return map_url

def get_service_content(service_url, city_name, state_abbreviation, state_full_name, json_data, zip_codes, neighborhoods, city_zip_code):
    service = next((service for service in json_data["services"]["services"] if service["url"] == service_url), None)
    if service:
        required_data = json_data["required"]
        service_content = {
            "name": service["name"],
            "description": Markup(replace_placeholders(
                service["description"],
                service["name"],
                city_name,
                state_abbreviation,
                state_full_name,
                required_data,
                zip_codes,
                neighborhoods,
                city_zip_code
            )),
            "why_choose_us": Markup(replace_placeholders(
                service["why_choose_us"],
                service["name"],
                city_name,
                state_abbreviation,
                state_full_name,
                required_data,
                zip_codes,
                neighborhoods,
                city_zip_code
            )),
            "why_you_need": Markup(replace_placeholders(
                service["why_you_need"],
                service["name"],
                city_name,
                state_abbreviation,
                state_full_name,
                required_data,
                zip_codes,
                neighborhoods,
                city_zip_code
            )),
            "image_url": service["image_url"],
            "image_alt": service["image_alt"],
            "reviews": [
                {
                    "name": review["name"],
                    "review": Markup(replace_placeholders(
                        review["review"],
                        service["name"],
                        city_name,
                        state_abbreviation,
                        state_full_name,
                        required_data,
                        zip_codes,
                        neighborhoods,
                        city_zip_code
                    ))
                }
                for review in service["reviews"]
            ],
            "faqs": [
                {
                    "question": Markup(replace_placeholders(
                        faq["question"],
                        service["name"],
                        city_name,
                        state_abbreviation,
                        state_full_name,
                        required_data,
                        zip_codes,
                        neighborhoods,
                        city_zip_code
                    )),
                    "answer": Markup(replace_placeholders(
                        faq["answer"],
                        service["name"],
                        city_name,
                        state_abbreviation,
                        state_full_name,
                        required_data,
                        zip_codes,
                        neighborhoods,
                        city_zip_code
                    ))
                }
                for faq in service["faqs"]
            ]
        }
        return service_content
    return None

def get_random_faqs(city_name, state_abbreviation, json_data, zip_codes, neighborhoods, city_zip_code):
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
            neighborhoods,
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
            neighborhoods,
            city_zip_code
        ))
    return selected_faqs

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
        state_links = {state['state_abbr']: f"https://{state['state_abbr']}.{get_main_domain()}" for state in states}
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
                # Get neighborhoods from DB
                neighborhoods = get_neighborhoods_from_db(city_name)
                # Generate neighborhood links
                neighborhoods_with_links = []
                for neighborhood in neighborhoods:
                    formatted_neighborhood = '+'.join(neighborhood.split())
                    formatted_city_name = '+'.join(city_name.split())
                    formatted_state_name = '+'.join(state_name.split())
                    map_link = f"https://www.google.com/maps/place/{formatted_neighborhood}+{formatted_city_name}+{formatted_state_name}"
                    neighborhoods_with_links.append({
                        'name': neighborhood,
                        'map_link': map_link
                    })
                # Now pass neighborhoods_with_links to the template
                meta_title = replace_placeholders(
                    required_data.get("Meta Title", ""),
                    "",
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    neighborhoods_with_links,
                    city_zip_code
                )

                meta_description = replace_placeholders(
                    required_data.get("Meta Description", ""),
                    "",
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    neighborhoods_with_links,
                    city_zip_code
                )
                service_links = {}
                services_descriptions = {}
                for service in json_data["services"]["services"]:
                    service_name = service["name"]
                    service_links[service_name] = f"https://{city_subdomain}-{state_subdomain}.{get_main_domain()}/{service['url']}"
                    services_descriptions[service_name] = Markup(replace_placeholders(
                        service.get("description", ""),
                        service_name,
                        city_name,
                        state_abbreviation,
                        state_name,
                        required_data,
                        zip_codes,
                        neighborhoods_with_links,
                        city_zip_code
                    ))
                map_embed_url = generate_map_embed(city_name, state_name)
                faqs = get_random_faqs(city_name, state_abbreviation, json_data, zip_codes, neighborhoods_with_links, city_zip_code)
                reviews = [
                    {
                        "name": review["name"],
                        "review": Markup(replace_placeholders(
                            review["review"],
                            "",
                            city_name,
                            state_abbreviation,
                            state_name,
                            required_data,
                            zip_codes,
                            neighborhoods_with_links,
                            city_zip_code
                        ))
                    }
                    for review in json_data["reviews"].get(state_subdomain, {}).get("reviews", [])
                ]
                city_content = json_data["citycontent"].get(state_subdomain, {})
                why_choose_us = Markup(replace_placeholders(
                    city_content.get("why_choose_us", ""),
                    "",
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    neighborhoods_with_links,
                    city_zip_code
                ))
                signs_you_need = Markup(replace_placeholders(
                    city_content.get("signs_you_need", ""),
                    "",
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    neighborhoods_with_links,
                    city_zip_code
                ))
                heading1 = Markup(replace_placeholders(
                    city_content.get("heading1", ""),
                    "",
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    neighborhoods_with_links,
                    city_zip_code
                ))
                heading2 = Markup(replace_placeholders(
                    city_content.get("heading2", ""),
                    "",
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    neighborhoods_with_links,
                    city_zip_code
                ))
                who_we_are = Markup(replace_placeholders(
                    json_data["about"].get(state_subdomain, {}).get("who_we_are", ""),
                    "",
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    neighborhoods_with_links,
                    city_zip_code
                ))

                # Fetch other cities in the same state
                all_other_cities = get_other_cities_in_state(state_subdomain, city_info['city_name'])
                if len(all_other_cities) > 0:
                    # Calculate index based on current city name
                    city_index = sum(ord(char) for char in city_info['city_name']) % len(all_other_cities)
                    # Rotate the list starting from city_index
                    rotated_cities = all_other_cities[city_index:] + all_other_cities[:city_index]
                    # Limit the number of cities to display, e.g., top 10
                    other_cities = rotated_cities[:10]
                    # Generate links for other cities
                    other_city_links = []
                    for city in other_cities:
                        city_subdomain_format = urllib.parse.quote(city.replace(' ', '-').lower())
                        city_link = f"https://{city_subdomain_format}-{state_subdomain}.{get_main_domain()}"
                        other_city_links.append({
                            'name': city,
                            'link': city_link
                        })
                else:
                    other_city_links = []

                return render_template(
                    'city.html',
                    state_name=state_name,
                    city_name=city_name,
                    city_zip_code=city_zip_code,
                    service_links=service_links,
                    services_descriptions=services_descriptions,
                    map_embed_url=map_embed_url,
                    faqs=faqs,
                    reviews=reviews,
                    meta_title=meta_title,
                    meta_description=meta_description,
                    required=required_data,
                    why_choose_us=why_choose_us,
                    signs_you_need=signs_you_need,
                    heading1=heading1,
                    heading2=heading2,
                    who_we_are=who_we_are,
                    canonical_url=get_canonical_url(),
                    favicon=required_data.get("favicon"),
                    main_service=required_data.get("Main Service"),
                    company_name=required_data.get("Company Name"),
                    zip_codes=zip_codes,
                    neighborhoods=neighborhoods_with_links,  # Pass neighborhoods with links
                    other_city_links=other_city_links  # Pass other cities to template
                )
            else:
                abort(404)
        else:
            abort(404)
    abort(404)

@app.route('/<service_url>')
def service_page(service_url):
    host = request.host
    json_data = request.json_data
    required_data = json_data["required"]
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
            # Get neighborhoods from DB
            neighborhoods = get_neighborhoods_from_db(city_name)
            # Generate neighborhood links
            neighborhoods_with_links = []
            for neighborhood in neighborhoods:
                formatted_neighborhood = '+'.join(neighborhood.split())
                formatted_city_name = '+'.join(city_name.split())
                formatted_state_name = '+'.join(state_name.split())
                map_link = f"https://www.google.com/maps/place/{formatted_neighborhood}+{formatted_city_name}+{formatted_state_name}"
                neighborhoods_with_links.append({
                    'name': neighborhood,
                    'map_link': map_link
                })
            service_content = get_service_content(
                service_url,
                city_name,
                state_abbreviation,
                state_name,
                json_data,
                zip_codes,
                neighborhoods_with_links,
                city_zip_code
            )
            if service_content:
                meta_title = replace_placeholders(
                    required_data.get("Meta Title", ""),
                    service_content["name"],
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    neighborhoods_with_links,
                    city_zip_code
                )
                meta_description = replace_placeholders(
                    required_data.get("Meta Description", ""),
                    service_content["name"],
                    city_name,
                    state_abbreviation,
                    state_name,
                    required_data,
                    zip_codes,
                    neighborhoods_with_links,
                    city_zip_code
                )
                map_embed_url = generate_map_embed(city_name, state_name)
                return render_template(
                    'service.html',
                    state_name=state_name,
                    city_name=city_name,
                    city_zip_code=city_zip_code,
                    service=service_content,
                    map_embed_url=map_embed_url,
                    meta_title=meta_title,
                    meta_description=meta_description,
                    required=required_data,
                    canonical_url=get_canonical_url(),
                    favicon=required_data.get("favicon"),
                    main_service=required_data.get("Main Service"),
                    company_name=required_data.get("Company Name"),
                    zip_codes=zip_codes,
                    neighborhoods=neighborhoods_with_links  # Pass neighborhoods with links
                )
    abort(404)

@app.route('/about')
def about_page():
    host = request.host
    json_data = request.json_data
    required_data = json_data["required"]
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
            # Get neighborhoods from DB
            neighborhoods = get_neighborhoods_from_db(city_name)
            # Generate neighborhood links
            neighborhoods_with_links = []
            for neighborhood in neighborhoods:
                formatted_neighborhood = '+'.join(neighborhood.split())
                formatted_city_name = '+'.join(city_name.split())
                formatted_state_name = '+'.join(state_name.split())
                map_link = f"https://www.google.com/maps/place/{formatted_neighborhood}+{formatted_city_name}+{formatted_state_name}"
                neighborhoods_with_links.append({
                    'name': neighborhood,
                    'map_link': map_link
                })
            about_content = json_data["about"].get(state_subdomain, {})
            who_we_are_content = about_content.get("who_we_are", "")
            why_choose_us_content = about_content.get("why_choose_us", "")
            who_we_are = Markup(replace_placeholders(
                who_we_are_content,
                "",
                city_name,
                state_abbreviation,
                state_name,
                required_data,
                zip_codes,
                neighborhoods_with_links,
                city_zip_code
            ))
            why_choose_us = Markup(replace_placeholders(
                why_choose_us_content,
                "",
                city_name,
                state_abbreviation,
                state_name,
                required_data,
                zip_codes,
                neighborhoods_with_links,
                city_zip_code
            ))
            return render_template(
                'about.html',
                state_name=state_name,
                city_name=city_name,
                city_zip_code=city_zip_code,
                who_we_are=who_we_are,
                why_choose_us=why_choose_us,
                required=required_data,
                canonical_url=get_canonical_url(),
                favicon=required_data.get("favicon"),
                main_service=required_data.get("Main Service"),
                company_name=required_data.get("Company Name"),
                zip_codes=zip_codes,
                neighborhoods=neighborhoods_with_links  # Pass neighborhoods with links
            )
    abort(404)

@app.route('/contact')
def contact_page():
    host = request.host
    json_data = request.json_data
    required_data = json_data["required"]
    subdomains = host.split('.')[0].split('-')
    if len(subdomains) >= 2:
        city_subdomain = '-'.join(subdomains[:-1])
        state_subdomain = subdomains[-1]
        city_info = get_city_info(city_subdomain, state_subdomain)
        if city_info:
            city_name = city_info['city_name'].title()
            city_zip_code = city_info['zip_code']
            state_name = get_state_full_name(state_subdomain)
            state_abbreviation = state_subdomain.upper()
            zip_codes = get_zip_codes_from_db(city_name)
            # Get neighborhoods from DB
            neighborhoods = get_neighborhoods_from_db(city_name)
            # Generate neighborhood links
            neighborhoods_with_links = []
            for neighborhood in neighborhoods:
                formatted_neighborhood = '+'.join(neighborhood.split())
                formatted_city_name = '+'.join(city_name.split())
                formatted_state_name = '+'.join(state_name.split())
                map_link = f"https://www.google.com/maps/place/{formatted_neighborhood}+{formatted_city_name}+{formatted_state_name}"
                neighborhoods_with_links.append({
                    'name': neighborhood,
                    'map_link': map_link
                })
            map_embed_url = generate_map_embed(city_name, state_name)
            address_template = required_data.get('Address Template', "[Company Name], [City], [State] [zipcode]")
            address = replace_placeholders(
                address_template,
                "",
                city_name,
                state_abbreviation,
                state_name,
                required_data,
                zip_codes,
                neighborhoods_with_links,
                city_zip_code
            )
            return render_template(
                'contact.html',
                state_name=state_name,
                city_name=city_name,
                city_zip_code=city_zip_code,
                map_embed_url=map_embed_url,
                address=address,
                required=required_data,
                canonical_url=get_canonical_url(),
                favicon=required_data.get("favicon"),
                main_service=required_data.get("Main Service"),
                company_name=required_data.get("Company Name"),
                zip_codes=zip_codes,
                neighborhoods=neighborhoods_with_links  # Pass neighborhoods with links
            )
    abort(404)

@app.route('/services')
def services_page():
    host = request.host
    json_data = request.json_data
    required_data = json_data["required"]
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
            # Get neighborhoods from DB
            neighborhoods = get_neighborhoods_from_db(city_name)
            # Generate neighborhood links
            neighborhoods_with_links = []
            for neighborhood in neighborhoods:
                formatted_neighborhood = '+'.join(neighborhood.split())
                formatted_city_name = '+'.join(city_name.split())
                formatted_state_name = '+'.join(state_name.split())
                map_link = f"https://www.google.com/maps/place/{formatted_neighborhood}+{formatted_city_name}+{formatted_state_name}"
                neighborhoods_with_links.append({
                    'name': neighborhood,
                    'map_link': map_link
                })
            services_list = [
                {
                    "name": service["name"],
                    "url": service["url"],
                    "description": Markup(replace_placeholders(
                        service.get("description", ""),
                        service["name"],
                        city_name,
                        state_abbreviation,
                        state_name,
                        required_data,
                        zip_codes,
                        neighborhoods_with_links,
                        city_zip_code
                    ))
                }
                for service in json_data["services"]["services"]
            ]
            meta_title = replace_placeholders(
                "Services in [City], [State]",
                "",
                city_name,
                state_abbreviation,
                state_name,
                required_data,
                zip_codes,
                neighborhoods_with_links,
                city_zip_code
            )
            meta_description = replace_placeholders(
                "Explore all services offered in [City], [State].",
                "",
                city_name,
                state_abbreviation,
                state_name,
                required_data,
                zip_codes,
                neighborhoods_with_links,
                city_zip_code
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
                favicon=required_data.get("favicon"),
                main_service=required_data.get("Main Service"),
                company_name=required_data.get("Company Name"),
                zip_codes=zip_codes,
                neighborhoods=neighborhoods_with_links  # Pass neighborhoods with links
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
