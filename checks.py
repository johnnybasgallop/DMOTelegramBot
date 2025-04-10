import reverse_geocoder as rg


def check_if_in_usa(latitude, longitude):
    # Reverse geocode the coordinates; returns a list of dictionaries.
    result = rg.search((latitude, longitude))[0]
    # The 'cc' key contains the country code, e.g., "US" for United States.
    return result.get("cc") != "US"
