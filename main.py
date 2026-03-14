import datetime
import pytz
import markdown
import requests

# Function to extract travel information using Claude API
def extract_travel_info(input_text):
    # Placeholder for API call to Claude
    # In actual implementation, replace this with the API call logic to extract details
    return {
        'dates': ['2026-04-09', '2026-05-13'],
        'locations': ['Tallinn', 'Istanbul', 'Dallas', 'El Paso', 'Dallas', 'Bogotá', 'Prague', 'Děčín', 'Prague', 'Riga', 'Tallinn'],
        'activities': ['Sightseeing', 'Cultural Experiences', 'Local Cuisine', 'Shopping']
    }

# Function to convert timezones
def convert_timezone(local_time_str, from_tz_str, to_tz_str):
    from_zone = pytz.timezone(from_tz_str)
    to_zone = pytz.timezone(to_tz_str)
    local_time = from_zone.localize(datetime.datetime.strptime(local_time_str, '%Y-%m-%d %H:%M:%S'))
    return local_time.astimezone(to_zone)

# Function to build the itinerary
def build_itinerary(travel_info):
    itinerary = "# Travel Itinerary\n\n"
    for date in travel_info['dates']:
        itinerary += f'## Date: {date}\n'
        for location in travel_info['locations']:
            itinerary += f'- Location: {location} \n'
            itinerary += '  - Activities: '+ ', '.join(travel_info['activities']) + '\n'
    return itinerary

if __name__ == '__main__':
    input_text = "Travel from April 9 to May 13 visiting: Tallinn → Istanbul → Dallas → El Paso → Dallas → Bogotá → Prague → Děčín → Prague → Riga → Tallinn"
    travel_info = extract_travel_info(input_text)
    itinerary = build_itinerary(travel_info)
    with open('itinerary.md', 'w') as file:
        file.write(itinerary)
    print("Itinerary created successfully!")
