import os
import requests
from geopy.geocoders import Nominatim
import platform
import logging

logger = logging.getLogger(__name__)

class NavigationModule:
    def __init__(self):
        self.geolocator = Nominatim(user_agent="Jarvis_Mark7_Project")
        self.osrm_url = "http://router.project-osrm.org/route/v1/driving/"
        self._gmaps_key = os.getenv("GOOGLE_MAPS_API_KEY")
        # Дефолтні координати — Вінниця
        self.current_coords = (49.2331, 28.4682)

    def update_my_location(self) -> bool:
        """
        Оновлює координати через WiFi або IP.
        Повертає True якщо вдалось, False якщо ні.
        """
        # Спочатку пробуємо WiFi (точніше)
        # потім fallback на IP (менш точно але завжди працює)
        if self._try_wifi_location():
            return True
        return self._fallback_to_ip()

    def _try_wifi_location(self) -> bool:
        """Визначає локацію через WiFi мережі поблизу."""
        # access_points працює тільки на Linux/Raspberry Pi
        # на Windows просто пропускаємо цей метод
        if platform.system() != "Linux":
            logger.debug("WiFi location: пропускаємо (не Linux)")
            return False

        try:
            from access_points import get_scanner
            scanner = get_scanner()
            aps = scanner.get_access_points()

            # Беремо перші 5 мереж (було [:8] але в коментарі писалось 5)
            wifi_data = [{"macAddress": ap.bssid} for ap in aps[:5]]

            if not wifi_data:
                logger.debug("WiFi location: мереж не знайдено")
                return False

            url = "https://location.services.mozilla.com/v1/geolocate?key=test"
            response = requests.post(
                url,
                json={"wifiAccessPoints": wifi_data},
                timeout=5
            ).json()

            if 'location' in response:
                self.current_coords = (
                    response['location']['lat'],
                    response['location']['lng']
                )
                logger.debug(f"WiFi location: {self.current_coords}")
                return True

            return False

        except Exception as e:
            # Логуємо але не крашимо — просто спробуємо fallback
            logger.debug(f"WiFi location error: {e}")
            return False

    def _fallback_to_ip(self) -> bool:
        """Запасний варіант — визначення локації через IP адресу."""
        try:
            response = requests.get(
                'http://ip-api.com/json/',
                timeout=5
            ).json()

            # Перевіряємо що відповідь містить потрібні поля
            if response.get('status') == 'success':  # ip-api повертає 'status' а не 'latitude' напряму
                self.current_coords = (
                    response['lat'],  # ← 'lat' замість 'latitude'
                    response['lon']   # ← 'lon' замість 'longitude'
                )
                logger.debug(f"IP location: {self.current_coords}")
                return True

            logger.warning("IP location: помилка відповіді")
            return False

        except Exception as e:
            logger.warning(f"IP location error: {e}")
            return False

    def get_current_address(self) -> str:
        """Повертає поточну адресу у текстовому форматі."""
        self.update_my_location()

        try:
            location = self.geolocator.reverse(
                self.current_coords,
                language='en'
            )

            if not location:
                return "I'm having trouble triangulating your position, Sir."

            addr = location.raw.get('address', {})
            street = addr.get('road', 'an unnamed street')
            house = addr.get('house_number', '')
            city = addr.get('city') or addr.get('town') or 'your city'
            # .get('city') or .get('town') — бо деякі міста повертаються як 'town'

            location_str = f"{street} {house}".strip()
            return f"Sir, you are currently near {location_str} in {city}."

        except Exception as e:
            logger.error(f"Reverse geocoding error: {e}")
            return "I'm having trouble triangulating your position, Sir."

    def get_route_to(self, destination_name: str) -> str:
        """Прокладає маршрут. Google Directions якщо є API ключ, інакше OSRM."""
        self.update_my_location()

        if self._gmaps_key:
            return self._route_google(destination_name)
        return self._route_osrm(destination_name)

    def _route_google(self, destination_name: str) -> str:
        """Маршрут через Google Directions API."""
        try:
            from api_guard import guard
            if not guard.check("directions"):
                return self._route_osrm(destination_name)
            origin = str(self.current_coords[0]) + "," + str(self.current_coords[1])
            url = "https://maps.googleapis.com/maps/api/directions/json"
            params = {
                "origin":      origin,
                "destination": destination_name,
                "mode":        "driving",
                "key":         self._gmaps_key,
                "language":    "en",
            }
            r = requests.get(url, params=params, timeout=10).json()

            if r.get("status") != "OK":
                logger.warning(f"[MAPS] status: {r.get('status')}")
                return self._route_osrm(destination_name)

            leg = r["routes"][0]["legs"][0]
            dist     = leg["distance"]["text"]
            duration = leg["duration"]["text"]
            end_addr = leg["end_address"]

            guard.increment("directions")
            return (
                f"Route calculated, Sir. "
                f"{destination_name} is {dist} away, "
                f"approximately {duration} by car. "
                f"Destination: {end_addr}."
            )
        except Exception as e:
            logger.error(f"[MAPS] Google route error: {e}")
            return self._route_osrm(destination_name)

    def _route_osrm(self, destination_name: str) -> str:
        """Fallback маршрут через OSRM."""
        try:
            location = self.geolocator.geocode(destination_name)
            if not location:
                return f"Sir, I couldn't find {destination_name} on the maps."

            dest = (location.latitude, location.longitude)
            query = (
                str(self.current_coords[1]) + "," + str(self.current_coords[0]) + ";"
                + str(dest[1]) + "," + str(dest[0])
            )
            response = requests.get(
                self.osrm_url + query + "?overview=false",
                timeout=10
            ).json()

            if response.get("code") == "Ok":
                route = response["routes"][0]
                dist = round(route["distance"] / 1000, 1)
                time_min = round(route["duration"] / 60)
                return (
                    f"Route calculated, Sir. "
                    f"Distance to {destination_name} is {dist} kilometres, "
                    f"approximately {time_min} minutes by car. "
                    f"Destination: {location.address}."
                )
            return "Sir, there was an error calculating the route."

        except Exception as e:
            logger.error(f"Route error: {e}")
            return f"Navigation system error, Sir: {str(e)}"