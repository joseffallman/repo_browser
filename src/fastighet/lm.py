
import base64

import requests

# from tasks import celery
from config import (
    LM_consumer_key,
    LM_consumer_secret,
)

LANTMATERIET_TOKEN_URL = "https://apimanager.lantmateriet.se/oauth2/token"
LANTMATERIET_API_URL = "https://api.lantmateriet.se/ogc-features/v1/fastighetsindelning/collections/registerenhetsomradesytor/items"


def get_access_token():
    """ Hämtar OAuth2 access token från Lantmäteriets API """
    client_id = LM_consumer_key
    client_secret = LM_consumer_secret
    credentials = f"{client_id}:{client_secret}"
    encoded_credentials = base64.b64encode(credentials.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = "grant_type=client_credentials&scope=ogc-features:fastighetsindelning.read"

    response = requests.post(LANTMATERIET_TOKEN_URL,
                             headers=headers, data=data)
    response.raise_for_status()
    return response.json().get('access_token')


def fetch_property_data(bbox):
    """ Hämtar registerenhetsomradesytor från Lantmäteriets API baserat på bbox """
    token = get_access_token()
    headers = {"Authorization": f"Bearer {token}"}
    all_features = []  # För att lagra alla objekt

    offset = 0  # Börja från första sidan
    limit = 100  # Antal objekt per begäran (kan justeras om det behövs)

    while True:
        params = {
            "bbox": bbox,
            "crs": "http://www.opengis.net/def/crs/EPSG/0/3006",
            "offset": offset,
            "limit": limit
        }

        response = requests.get(LANTMATERIET_API_URL,
                                headers=headers, params=params)
        response.raise_for_status()

        data = response.json()
        features = data.get("features", [])

        all_features.extend(features)

        # Om antalet returnerade objekt är mindre än 'limit', har vi hämtat alla objekt
        if len(features) < limit:
            break

        offset += limit

    return all_features
